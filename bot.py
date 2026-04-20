import discord, asyncio, os, json, asyncpg, traceback, random
import string as _string
import io
import yaml
from tabulate import tabulate
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

TOKEN                 = os.getenv("BOT_TOKEN")
NOTIFY_CHANNEL        = 'looking-for-group'
CHEST_INFO_CHANNEL_ID = int(os.getenv("CHEST_INFO_CHANNEL_ID"))
CHEST_INFO_MESSAGE_ID = int(os.getenv("CHEST_INFO_MESSAGE_ID"))
GUILD_MEMBER_ROLE_ID  = int(os.getenv("GUILD_MEMBER_ROLE_ID"))
CHEST_EVENTS_FILE     = os.getenv("CHEST_EVENTS_FILE")
DATABASE_URL          = os.getenv("DATABASE_URL")
GOOGLE_API_KEY        = os.getenv("GOOGLE_API_KEY")
CHATBOT_CONTEXT_FILE  = os.getenv("CHATBOT_CONTEXT_FILE", "chatbot_context.txt")

db_pool = None

# ── Chatbot state ─────────────────────────────────────────────────────────────
genai.configure(api_key=GOOGLE_API_KEY)
_MODELS    = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-2.5-pro']
_model_idx = 0

with open(CHATBOT_CONTEXT_FILE, 'r') as f:
    _context = f.read()

_chat = genai.GenerativeModel(_MODELS[_model_idx]).start_chat(history=[])
print(_chat.send_message(_context))

# ── 8-ball cache ──────────────────────────────────────────────────────────────
_8BALL_CACHE = {}
_8BALL_TTL   = timedelta(hours=1)

# ── Shared helpers ────────────────────────────────────────────────────────────

def parse_discord_timestamp(ts):
    try:
        if ts.startswith('<t:') and ts.endswith('>'):
            parts = ts[3:-1].split(':')
            if parts:
                return datetime.fromtimestamp(int(parts[0]), tz=timezone.utc)
    except (ValueError, IndexError):
        pass
    return None

_QUOTE_ID_CHARS = _string.ascii_lowercase + _string.digits

async def _generate_quote_id():
    while True:
        nid = ''.join(random.choices(_QUOTE_ID_CHARS, k=5))
        if not await db_pool.fetchrow("SELECT 1 FROM quotes WHERE nadeko_id = $1", nid):
            return nid

async def _is_admin(discord_id):
    row = await db_pool.fetchrow("SELECT role FROM users WHERE discord_id = $1", discord_id)
    return row is not None and row['role'] == 'admin'

_ALLOWED_GEAR_COLS = {'gear_ap', 'gear_aap', 'gear_dp', 'gear_image_url'}

async def db_upsert_gear(discord_id, discord_username, **fields):
    fields = {k: v for k, v in fields.items() if k in _ALLOWED_GEAR_COLS}
    if not fields:
        return
    field_keys  = list(fields.keys())
    set_clause  = ', '.join(f'{k} = ${i+3}' for i, k in enumerate(field_keys))
    base_params = [discord_id, discord_username] + list(fields.values())

    result = await db_pool.execute(
        f"UPDATE users SET discord_username = $2, {set_clause}, updated_at = NOW() WHERE discord_id = $1",
        *base_params
    )
    if result != "UPDATE 0":
        return

    result = await db_pool.execute(
        f"UPDATE users SET discord_id = $1, discord_username = $2, {set_clause}, updated_at = NOW() "
        f"WHERE username = $2 AND discord_id IS NULL",
        *base_params
    )
    if result != "UPDATE 0":
        return

    col_list        = ', '.join(field_keys)
    placeholders    = ', '.join(f'${i+4}' for i in range(len(field_keys)))
    set_clause_excl = ', '.join(f'{k} = EXCLUDED.{k}' for k in field_keys)
    await db_pool.execute(
        f"""INSERT INTO users (discord_id, discord_username, username, password_hash, role, {col_list})
            VALUES ($1, $2, $3, '', 'member', {placeholders})
            ON CONFLICT (discord_id) DO UPDATE SET
                discord_username = EXCLUDED.discord_username,
                {set_clause_excl},
                updated_at = NOW()""",
        discord_id, discord_username, discord_username, *list(fields.values())
    )

async def db_get_user_gear(discord_id):
    return await db_pool.fetchrow(
        "SELECT gear_ap, gear_aap, gear_dp, gear_image_url FROM users WHERE discord_id = $1",
        discord_id
    )

async def db_get_all_with_gs():
    return await db_pool.fetch(
        """SELECT discord_id, discord_username, gear_ap, gear_aap, gear_dp FROM users
           WHERE gear_ap IS NOT NULL AND gear_aap IS NOT NULL AND gear_dp IS NOT NULL
             AND discord_id IS NOT NULL"""
    )

def calculate_gs(ap, aap, dp):
    return (ap + aap) / 2 + dp

INVALID_STAT_RESPONSES = [
    "Bro really said {value}. Be serious.",
    "There is no way you actually typed that with a straight face.",
    "I don't know what game you think you're playing, but it's not this one.",
    "Cute number. Put in a real one.",
    "lmaooo no.",
    "I've seen better numbers from a keyboard smash.",
    "Sir/Ma'am this is a Wendy's.",
]

def splitReplyToLessThan2000(reply):
    for i in range(1999, 0, -1):
        if reply[i] == '\n':
            return reply[:i], reply[i:]
    for i in range(1999, 0, -1):
        if reply[i] == ' ':
            return reply[:i], reply[i:]
    return reply[:1999], reply[1999:]

# ── Views ─────────────────────────────────────────────────────────────────────

class LeaderboardPagination(discord.ui.View):
    def __init__(self, data, title, author_id):
        super().__init__(timeout=60)
        self.data         = data
        self.title        = title
        self.author_id    = author_id
        self.per_page     = 20
        self.current_page = 0
        self.total_pages  = (len(data) - 1) // self.per_page + 1

    def create_embed(self):
        start      = self.current_page * self.per_page
        page_slice = self.data[start:start + self.per_page]
        table      = tabulate(page_slice, headers=["User", "AP", "AAP", "DP", "GS"], tablefmt="pretty")
        embed      = discord.Embed(title=self.title, description=f"```\n{table}\n```", color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your leaderboard!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction, button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)


class QuoteListView(discord.ui.View):
    def __init__(self, rows, title, per_page=15):
        super().__init__(timeout=120)
        self.rows         = rows
        self.title        = title
        self.per_page     = per_page
        self.current_page = 0
        self.total_pages  = max(1, (len(rows) + per_page - 1) // per_page)
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def create_embed(self):
        start = self.current_page * self.per_page
        lines = [
            f"`{r['nadeko_id']}` :  {r['keyword']} by {r['author_name'] or 'unknown'}"
            for r in self.rows[start:start + self.per_page]
        ]
        embed = discord.Embed(title=self.title, description='\n'.join(lines), color=discord.Color.blurple())
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} · {len(self.rows)} quotes total")
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.gray)
    async def prev_button(self, interaction, button):
        self.current_page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction, button):
        self.current_page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class ConfirmView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.send_message("Cancelled.", ephemeral=True)


# ── Custom Help Command ───────────────────────────────────────────────────────

_FIELD_LIMIT = 1000   # field value limit (Discord max 1024, keep buffer)
_EMBED_LIMIT = 5800   # total embed char limit (Discord max 6000, keep buffer)


class BoopHelpCommand(commands.HelpCommand):

    def _label(self, cmd):
        if cmd.aliases:
            return f'{cmd.name} [{", ".join(cmd.aliases)}]'
        return cmd.name

    def _brief(self, cmd):
        """Short description with Usage: stripped — full detail is in !help <command>."""
        doc = cmd.short_doc or ''
        if 'Usage:' in doc:
            doc = doc[:doc.index('Usage:')].strip('. ')
        return doc

    def _cmd_entries(self, cmds):
        """Return markdown lines: **name** [aliases] — brief desc."""
        return [f'**{cmd.name}** {f"[{chr(44).join(cmd.aliases)}] " if cmd.aliases else ""}— {self._brief(cmd)}'
                for cmd in cmds]

    def _split_entries(self, entries):
        """Split entry lines into field-value chunks at line boundaries."""
        chunks, current, cur_len = [], [], 0
        for entry in entries:
            cost = len(entry) + 1
            if current and cur_len + cost > _FIELD_LIMIT:
                chunks.append('\n'.join(current))
                current, cur_len = [entry], cost
            else:
                current.append(entry)
                cur_len += cost
        if current:
            chunks.append('\n'.join(current))
        return chunks or ['—']

    async def _send_fields(self, dest, title, fields):
        """Send (field_name, field_value) pairs across as many embeds as needed."""
        embed       = discord.Embed(title=title, color=discord.Color.blurple())
        embed_chars = len(title)

        for name, value in fields:
            cost = len(name) + len(value)
            if embed.fields and embed_chars + cost > _EMBED_LIMIT:
                await dest.send(embed=embed)
                embed       = discord.Embed(color=discord.Color.blurple())
                embed_chars = 0
            embed.add_field(name=name, value=value, inline=False)
            embed_chars += cost

        if embed.fields:
            await dest.send(embed=embed)

    async def send_bot_help(self, mapping):
        dest   = self.get_destination()
        fields = []

        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            if not filtered:
                continue
            cog_name = getattr(cog, 'qualified_name', 'Other')
            chunks   = self._split_entries(self._cmd_entries(filtered))
            for i, chunk in enumerate(chunks):
                fields.append((cog_name if i == 0 else '\u200b', chunk))

        footer_field = ('\u200b', '*Use `!help <command>` for full usage details.*')
        fields.append(footer_field)
        await self._send_fields(dest, 'BoopBot Commands', fields)

    async def send_cog_help(self, cog):
        dest     = self.get_destination()
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        entries  = self._cmd_entries(filtered) if filtered else ['—']
        chunks   = self._split_entries(entries)
        fields   = [(cog.qualified_name if i == 0 else '\u200b', c) for i, c in enumerate(chunks)]
        fields.append(('\u200b', '*Use `!help <command>` for full usage details.*'))
        await self._send_fields(dest, f'{cog.qualified_name} Commands', fields)

    async def send_command_help(self, cmd):
        embed = discord.Embed(
            title=self._label(cmd),
            description=cmd.help or cmd.short_doc or '—',
            color=discord.Color.blurple()
        )
        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        await self.get_destination().send(f'❌ {error}')


# ── Bot ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.guilds         = True
intents.message_content = True
intents.members        = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    activity=discord.Game(name="!help"),
    help_command=BoopHelpCommand()
)


# ── Cogs ──────────────────────────────────────────────────────────────────────

class EventsCog(commands.Cog, name="Events"):

    def __init__(self, bot):
        self.bot = bot
        self.event_reminder.start()

    def cog_unload(self):
        self.event_reminder.cancel()

    @tasks.loop(minutes=1)
    async def event_reminder(self):
        try:
            now = datetime.now(timezone.utc)
            for guild in self.bot.guilds:
                remind_channel = discord.utils.get(guild.text_channels, name=NOTIFY_CHANNEL)

                if remind_channel:
                    for event in await guild.fetch_scheduled_events():
                        try:
                            if event.status != discord.EventStatus.scheduled:
                                continue
                            interested = [u async for u in event.users()]
                            mentions   = " ".join(u.mention for u in interested)
                            thirty = event.start_time - timedelta(minutes=30)
                            five   = event.start_time - timedelta(minutes=5)
                            if thirty <= now < thirty + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 30 minutes! {event.url}\n{mentions}")
                            elif five <= now < five + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 5 minutes! {event.url}\n{mentions}")
                        except Exception as e:
                            print(f"Error processing event {event.id}: {e}")

                try:
                    for minutes_ahead in [30, 5]:
                        window_start = now + timedelta(minutes=minutes_ahead)
                        window_end   = window_start + timedelta(minutes=1)
                        cal_events   = await db_pool.fetch("""
                            SELECT ce.title,
                                   array_agg(u.discord_id) FILTER (WHERE u.discord_id IS NOT NULL) AS discord_ids
                            FROM calendar_events ce
                            LEFT JOIN calendar_event_interests cei ON cei.event_id = ce.id
                            LEFT JOIN users u ON u.id = cei.user_id
                            WHERE ce.event_time IS NOT NULL AND ce.event_timezone IS NOT NULL
                            GROUP BY ce.id, ce.title
                            HAVING (ce.event_date + ce.event_time) AT TIME ZONE ce.event_timezone BETWEEN $1 AND $2
                        """, window_start, window_end)
                        rc = discord.utils.get(guild.text_channels, name=NOTIFY_CHANNEL)
                        if not rc:
                            continue
                        for ev in cal_events:
                            mentions = " ".join(
                                m.mention for did in (ev['discord_ids'] or [])
                                if did and (m := guild.get_member(int(did)))
                            )
                            msg = f"Reminder! {ev['title']} starts in {minutes_ahead} minutes!"
                            if mentions:
                                msg += f"\n{mentions}"
                            await rc.send(msg)
                except Exception as e:
                    print(f"Error checking calendar reminders: {e}")
        except Exception as e:
            print(f"Error in event_reminder loop: {e}")

    @event_reminder.before_loop
    async def before_event_reminder(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def create_event(self, ctx, name: str, description: str, start_time_str: str, duration_minutes: int):
        """Creates a Discord scheduled event.
        Usage: !create_event "Name" "Description" <t:timestamp:F> duration_minutes
        """
        try:
            start_time = parse_discord_timestamp(start_time_str)
            if start_time is None:
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                except ValueError:
                    await ctx.send("Invalid time format. Use `<t:unix_timestamp:F>` or ISO format.")
                    return
            end_time = start_time + timedelta(minutes=duration_minutes)
            await ctx.guild.create_scheduled_event(
                name=name, description=description,
                start_time=start_time, end_time=end_time,
                entity_type=discord.EntityType.external,
                location="BDO",
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            await ctx.send(f'Event "{name}" created!')
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


class GearCog(commands.Cog, name="Gear"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def gear(self, ctx, *, image_url: str = None):
        """Saves, updates, or retrieves your gear image. Attach an image or provide a URL."""
        discord_id       = str(ctx.author.id)
        discord_username = ctx.author.name
        attached_url     = ctx.message.attachments[0].url if ctx.message.attachments else None

        if image_url and 'http' in image_url and '<@' not in image_url:
            await db_upsert_gear(discord_id, discord_username, gear_image_url=image_url)
            await ctx.send(f"Gear image saved for {ctx.author.name}.")
        elif attached_url:
            await db_upsert_gear(discord_id, discord_username, gear_image_url=attached_url)
            await ctx.send(f"Gear image saved for {ctx.author.name}.")
        elif image_url and '<@' in image_url:
            member = ctx.guild.get_member(int(image_url[2:-1]))
            await self.checkgear(ctx, member)
        else:
            row = await db_get_user_gear(discord_id)
            if row and row['gear_image_url']:
                await ctx.reply(row['gear_image_url'])
            else:
                await ctx.reply("No gear image saved. Use `!gear <url>` or attach an image.")

    @commands.command()
    async def checkgear(self, ctx, target_user: discord.Member):
        """Retrieves the gear image for a mentioned user. Usage: !checkgear @user"""
        row = await db_get_user_gear(str(target_user.id))
        if row and row['gear_image_url']:
            await ctx.reply(row['gear_image_url'])
        else:
            await ctx.reply(f"{target_user.name} has no gear image saved.")

    @commands.command()
    async def setap(self, ctx, ap: int):
        """Saves your AP. Usage: !setap <value>"""
        if ap < 0 or ap > 666:
            await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=ap))
            return
        await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_ap=ap)
        await ctx.send(f"AP set to {ap} for {ctx.author.name}.")

    @commands.command()
    async def setaap(self, ctx, aap: int):
        """Saves your AAP. Usage: !setaap <value>"""
        if aap < 0 or aap > 666:
            await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=aap))
            return
        await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_aap=aap)
        await ctx.send(f"AAP set to {aap} for {ctx.author.name}.")

    @commands.command()
    async def setdp(self, ctx, dp: int):
        """Saves your DP. Usage: !setdp <value>"""
        if dp < 0 or dp > 911:
            await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=dp))
            return
        await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_dp=dp)
        await ctx.send(f"DP set to {dp} for {ctx.author.name}.")

    @commands.command(aliases=['gs'])
    async def showgs(self, ctx):
        """Shows your AP, AAP, DP, and GS."""
        row = await db_get_user_gear(str(ctx.author.id))
        if row and all(row[k] is not None for k in ('gear_ap', 'gear_aap', 'gear_dp')):
            ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
            await ctx.send(f"**{ctx.author.name}'s Gear Score:**\nAP: {ap}\nAAP: {aap}\nDP: {dp}\nGS: {calculate_gs(ap, aap, dp)}")
        else:
            await ctx.send("Set your stats with `!setap`, `!setaap`, and `!setdp` first.")

    @commands.command(aliases=['gsguild', 'guildgs'])
    async def showguildgs(self, ctx):
        """Shows the GS of all guild members who have saved stats."""
        leaderboard = await self._build_table(ctx, sort_col=0, reverse=False)
        if not leaderboard:
            return
        table = tabulate(leaderboard, headers=["User", "AP", "AAP", "DP", "GS"], tablefmt="pretty")
        for chunk in self._chunk_table(table):
            await ctx.send(f"```\n{chunk}\n```")

    @commands.command()
    async def gslb(self, ctx):
        """GS leaderboard for guild members (paginated)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True)
        if not leaderboard:
            return
        view = LeaderboardPagination(leaderboard, "Guild Gear Score Leaderboard", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command()
    async def gsall(self, ctx):
        """GS leaderboard including non-members (paginated)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True, members_only=False)
        if not leaderboard:
            return
        view = LeaderboardPagination(leaderboard, "All Gear Score Leaderboard", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command()
    async def oldgslb(self, ctx):
        """GS leaderboard as plain text (no pagination)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True)
        if not leaderboard:
            return
        table = tabulate(leaderboard, headers=["User", "AP", "AAP", "DP", "GS"], tablefmt="pretty")
        for chunk in self._chunk_table(table):
            await ctx.send(f"```\n{chunk}\n```")

    async def _build_table(self, ctx, sort_col, reverse, members_only=True):
        rows = await db_get_all_with_gs()
        if members_only:
            role       = ctx.guild.get_role(GUILD_MEMBER_ROLE_ID)
            member_map = {str(m.id): m for m in role.members} if role else {}
        else:
            member_map = {str(m.id): m for m in ctx.guild.members}

        leaderboard = []
        for row in rows:
            member = member_map.get(row['discord_id'])
            if members_only and not member:
                continue
            ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
            name = member.name if member else (row['discord_username'] or row['discord_id'])
            leaderboard.append((name, ap, aap, dp, calculate_gs(ap, aap, dp)))

        if not leaderboard:
            await ctx.send("No gear score data available.")
            return None
        leaderboard.sort(key=lambda x: x[sort_col], reverse=reverse)
        return leaderboard

    @staticmethod
    def _chunk_table(table):
        chunks, current = [], ""
        for line in table.split('\n'):
            if len(current) + len(line) > 1900:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)
        return chunks


class QuotesCog(commands.Cog, name="Quotes"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quotelist", aliases=["ql", "qli"])
    async def quotelist(self, ctx, *, keyword: str = None):
        """Lists quotes with pagination. Usage: !quotelist [keyword]"""
        if keyword:
            rows  = await db_pool.fetch(
                "SELECT nadeko_id, keyword, author_name FROM quotes WHERE keyword ILIKE $1 ORDER BY created_at ASC",
                keyword.strip()
            )
            title = f"Quotes – {keyword.upper()}"
        else:
            rows  = await db_pool.fetch(
                "SELECT nadeko_id, keyword, author_name FROM quotes ORDER BY keyword ASC, created_at ASC"
            )
            title = "All Quotes"

        if not rows:
            await ctx.send(f"No quotes found{f' for **{keyword}**' if keyword else ''}.")
            return
        view = QuoteListView(rows, title)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command(name="quoteprint", aliases=["qp", "q", "!!"])
    async def quoteprint(self, ctx, *, keyword: str):
        """Prints a random quote for the keyword. Usage: !quoteprint <keyword>"""
        rows = await db_pool.fetch(
            "SELECT nadeko_id, text FROM quotes WHERE keyword ILIKE $1", keyword.strip()
        )
        if not rows:
            await ctx.send(f"No quotes found for **{keyword}**.")
            return
        quote = random.choice(rows)
        await ctx.reply(f"`{quote['nadeko_id']}` 📣 {quote['text']}")

    @commands.command(name="quoteshow", aliases=["qshow"])
    async def quoteshow(self, ctx, quote_id: str):
        """Shows full details of a quote by ID. Usage: !quoteshow <id>"""
        row = await db_pool.fetchrow(
            "SELECT nadeko_id, keyword, text, author_name, author_discord_id FROM quotes WHERE nadeko_id = $1",
            quote_id.lower()
        )
        if not row:
            await ctx.send(f"Quote `{quote_id}` not found.")
            return
        author = row['author_name'] or 'unknown'
        if row['author_discord_id']:
            author += f" ({row['author_discord_id']})"
        embed = discord.Embed(title=f"Quote {row['nadeko_id']}", description=row['text'], color=discord.Color.blurple())
        embed.add_field(name="Trigger", value=row['keyword'], inline=True)
        embed.set_footer(text=f"Created by {author}.")
        await ctx.send(embed=embed)

    @commands.command(name="quoteadd", aliases=["qa", "!"])
    async def quoteadd(self, ctx, keyword: str, *, text: str = ""):
        """Adds a new quote. Usage: !quoteadd <keyword> <text> (or attach an image)"""
        if ctx.message.attachments:
            text = (text + "\n" + ctx.message.attachments[0].url).strip()
        if not text:
            await ctx.send("Provide quote text or attach an image.")
            return
        keyword = keyword.upper()
        new_id  = await _generate_quote_id()
        await db_pool.execute(
            "INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text) VALUES ($1, $2, $3, $4, $5)",
            keyword, new_id, ctx.author.name, str(ctx.author.id), text
        )
        await ctx.send(f"Quote added! ID: `{new_id}` – **{keyword}**")

    @commands.command(name="quotedelete", aliases=["qd", "qdel"])
    async def quotedelete(self, ctx, quote_id: str):
        """Deletes a quote by ID (creator or admin only). Usage: !quotedelete <id>"""
        row = await db_pool.fetchrow(
            "SELECT keyword, author_discord_id FROM quotes WHERE nadeko_id = $1", quote_id.lower()
        )
        if not row:
            await ctx.send(f"Quote `{quote_id}` not found.")
            return
        if row['author_discord_id'] != str(ctx.author.id) and not await _is_admin(str(ctx.author.id)):
            await ctx.send("You can only delete your own quotes (or be an admin).")
            return
        await db_pool.execute("DELETE FROM quotes WHERE nadeko_id = $1", quote_id.lower())
        await ctx.send(f"Quote `{quote_id}` ({row['keyword']}) deleted.")

    @commands.command(name="quotesearch", aliases=["qsearch", "qfind"])
    async def quotesearch(self, ctx, keyword: str, *, search_term: str):
        """Search for quotes containing a term. Usage: !quotesearch <keyword> <term>"""
        rows = await db_pool.fetch(
            "SELECT nadeko_id, keyword, author_name FROM quotes WHERE keyword ILIKE $1 AND text ILIKE $2 ORDER BY created_at ASC",
            keyword.strip(), f"%{search_term}%"
        )
        if not rows:
            await ctx.send(f"No quotes in **{keyword}** matching `{search_term}`.")
            return
        view = QuoteListView(rows, f'Search: {keyword.upper()} · "{search_term}"')
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command(name="quotedeleteauthor", aliases=["qda"])
    async def quotedeleteauthor(self, ctx, member: discord.Member):
        """(Admin) Deletes all quotes by a user. Usage: !quotedeleteauthor @user"""
        if not await _is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        count = await db_pool.fetchval("SELECT COUNT(*) FROM quotes WHERE author_discord_id = $1", str(member.id))
        if not count:
            await ctx.send(f"No quotes found by **{member.name}**.")
            return
        view = ConfirmView(ctx.author.id)
        msg  = await ctx.send(f"⚠️ Delete **{count}** quote(s) by **{member.name}**?", view=view)
        await view.wait()
        if view.confirmed:
            await db_pool.execute("DELETE FROM quotes WHERE author_discord_id = $1", str(member.id))
            await msg.edit(content=f"Deleted **{count}** quote(s) by **{member.name}**.", view=None)
        else:
            await msg.edit(content="Cancelled.", view=None)

    @commands.command(name="quotesdeleteall", aliases=["qdall"])
    async def quotesdeleteall(self, ctx, *, keyword: str = None):
        """(Admin) Deletes all quotes, or all for a keyword. Usage: !quotesdeleteall [keyword]"""
        if not await _is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        if keyword:
            count   = await db_pool.fetchval("SELECT COUNT(*) FROM quotes WHERE keyword ILIKE $1", keyword.strip())
            warning = f"⚠️ Delete **{count}** quote(s) for **{keyword.upper()}**?"
        else:
            count   = await db_pool.fetchval("SELECT COUNT(*) FROM quotes")
            warning = f"⚠️ Delete **ALL {count}** quotes from the archive?"
        if not count:
            await ctx.send("No quotes to delete.")
            return
        view = ConfirmView(ctx.author.id)
        msg  = await ctx.send(warning, view=view)
        await view.wait()
        if view.confirmed:
            if keyword:
                await db_pool.execute("DELETE FROM quotes WHERE keyword ILIKE $1", keyword.strip())
            else:
                await db_pool.execute("DELETE FROM quotes")
            await msg.edit(content=f"Deleted **{count}** quote(s).", view=None)
        else:
            await msg.edit(content="Cancelled.", view=None)

    @commands.command(name="quotesexport", aliases=["qexport", "qex"])
    async def quotesexport(self, ctx):
        """(Admin) Exports all quotes as a Nadeko-compatible YAML file."""
        if not await _is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        rows = await db_pool.fetch(
            "SELECT keyword, nadeko_id, author_name, author_discord_id, text FROM quotes ORDER BY keyword ASC, created_at ASC"
        )
        if not rows:
            await ctx.send("No quotes to export.")
            return
        data = {}
        for row in rows:
            data.setdefault(row['keyword'], []).append({
                'id':  row['nadeko_id'] or '',
                'an':  row['author_name'] or '',
                'aid': int(row['author_discord_id']) if row['author_discord_id'] else 0,
                'txt': row['text'],
            })
        yml_bytes = yaml.dump(data, allow_unicode=True, sort_keys=False).encode('utf-8')
        await ctx.send(f"Exported **{len(rows)}** quotes.", file=discord.File(io.BytesIO(yml_bytes), filename="quotes-export.yml"))

    @commands.command(name="quotesimport", aliases=["qimport", "qim"])
    async def quotesimport(self, ctx):
        """(Admin) Imports quotes from an attached YAML file. Usage: !quotesimport (attach .yml)"""
        if not await _is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        if not ctx.message.attachments:
            await ctx.send("Please attach a `.yml` file.")
            return
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(('.yml', '.yaml')):
            await ctx.send("Attachment must be a `.yml` or `.yaml` file.")
            return
        raw = await attachment.read()
        try:
            data = yaml.safe_load(raw.decode('utf-8'))
        except yaml.YAMLError as e:
            await ctx.send(f"Failed to parse YAML: {e}")
            return
        if not isinstance(data, dict):
            await ctx.send("Invalid format — expected a keyword mapping at the top level.")
            return
        inserted = skipped = 0
        for keyword, quotes in data.items():
            if not isinstance(quotes, list):
                continue
            for q in quotes:
                nadeko_id   = str(q.get('id', '')).strip() or await _generate_quote_id()
                author_name = str(q.get('an', '')).strip() or None
                author_id   = str(q.get('aid', '')).strip() or None
                text        = str(q.get('txt', '')).strip()
                if not text:
                    skipped += 1
                    continue
                result = await db_pool.execute(
                    "INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (nadeko_id) DO NOTHING",
                    str(keyword).upper(), nadeko_id, author_name, author_id, text
                )
                if result == "INSERT 0 1":
                    inserted += 1
                else:
                    skipped += 1
        await ctx.send(f"Import complete. Inserted: **{inserted}** · Skipped/duplicate: **{skipped}**")


class FunCog(commands.Cog, name="Fun"):

    _8BALL_RESPONSES = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes, definitely.",
        "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
        "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
        "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful.",
    ]

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='8ball')
    async def eightball(self, ctx, *, question: str = None):
        """Ask the magic 8-ball a question. Usage: !8ball <question>"""
        if not question:
            await ctx.send("Ask a question! Usage: `!8ball <question>`")
            return
        normalized = question.lower().strip().rstrip('?').strip()
        key        = (ctx.author.id, normalized)
        now        = datetime.now(timezone.utc)
        cached     = _8BALL_CACHE.get(key)
        if cached and now < cached[1]:
            response = cached[0]
        else:
            response = random.choice(self._8BALL_RESPONSES)
            _8BALL_CACHE[key] = (response, now + _8BALL_TTL)
        await ctx.send(f"🎱 {response}")

    @commands.command()
    async def resetchat(self, ctx):
        """Cycles to the next AI model and resets the chat session."""
        global _model_idx, _chat
        _model_idx = (_model_idx + 1) % len(_MODELS)
        _chat      = genai.GenerativeModel(_MODELS[_model_idx]).start_chat(history=[])
        _chat.send_message(_context)
        await ctx.send(f"Chat reset. Model: **{_MODELS[_model_idx]}**")


# ── Bot-level events ──────────────────────────────────────────────────────────

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if bot.user.mentioned_in(message):
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not content:
            return
        async with message.channel.typing():
            try:
                payload  = json.dumps({
                    "user_id":      message.author.id,
                    "user_name":    message.author.name,
                    "display_name": message.author.display_name,
                    "guild_id":     message.guild.id,
                    "channel_id":   message.channel.id,
                    "content":      content,
                }, indent=4)
                response = _chat.send_message(payload)
                reply    = response.text
                while len(reply) > 2000:
                    r, reply = splitReplyToLessThan2000(reply)
                    await message.reply(r)
                await message.reply(reply)
            except Exception as e:
                await message.reply(f"Sorry, something went wrong.\n{e}")
    else:
        await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    error = getattr(error, 'original', error)
    print(f"[ERROR] Command '{ctx.command}' raised: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(e)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    global db_pool
    async with bot:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        print("Database pool created.")
        await bot.add_cog(EventsCog(bot))
        await bot.add_cog(GearCog(bot))
        await bot.add_cog(QuotesCog(bot))
        await bot.add_cog(FunCog(bot))
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
