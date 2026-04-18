import discord, asyncio, os, json, math, asyncpg, traceback, random
from tabulate import tabulate
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from copy import deepcopy


load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
NOTIFY_CHANNEL = 'looking-for-group'

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True
# intents.channels = True

bot = commands.Bot(command_prefix='!', intents=intents, activity=discord.Game(name="!help"), help_command=commands.DefaultHelpCommand(show_parameter_descriptions=False))

CHEST_INFO_CHANNEL_ID = int(os.getenv("CHEST_INFO_CHANNEL_ID"))
CHEST_INFO_MESSAGE_ID = int(os.getenv("CHEST_INFO_MESSAGE_ID"))
GUILD_MEMBER_ROLE_ID = int(os.getenv("GUILD_MEMBER_ROLE_ID"))

CHEST_EVENTS_FILE = os.getenv("CHEST_EVENTS_FILE")
DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = None

global next_chest_events
next_chest_events = {}


################# EVENTS #################
@bot.command()
async def create_event(ctx, name: str, description: str, start_time_str: str, duration_minutes: int):
    """
    Creates a Discord event in the specified channel.

    Usage:      !create_event #channel "Event Name" "Event Description" <t:1743987610:F> duration_minutes
    Example:    !create_event #testing "Test Event" "" <t:1743987610:F> 30

    Arguments:
        channel (discord.VoiceChannel): #Channel the notifications should be in
        name (str): Name of the event
        description (str): Whatever u want I guess
        start_time_str (str): discord formatted time string for when the event will take place
        duration_minutes (int): How long the event will last in minutes
    """
    print("create event")
    try:
        start_time = parse_discord_timestamp(start_time_str)
        if start_time is None:
            try:
                start_time = datetime.fromisoformat(start_time_str)
            except ValueError:
                await ctx.send("Invalid date/time format. Please use <t:unix_timestamp:F> or ISO format (YYYY-MM-DD HH:MM).")
                return
        end_time = start_time + timedelta(minutes=duration_minutes)

        await ctx.guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                entity_type=discord.EntityType.external,
                location="BDO",
                privacy_level=discord.PrivacyLevel.guild_only,
            )

        await ctx.send(f'Event "{name}" created!')

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

def parse_discord_timestamp(timestamp_str):
    """Parses a Discord timestamp string like <t:1743987610:F>."""
    try:
        if timestamp_str.startswith('<t:') and timestamp_str.endswith('>'):
            parts = timestamp_str[3:-1].split(':')
            if len(parts) >= 1:
                unix_timestamp = int(parts[0])
                return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc) #important to set timezone to UTC.
        return None
    except (ValueError, IndexError):
        return None

@tasks.loop(minutes=1)
async def event_reminder():
    try:
        now = datetime.now(timezone.utc)
        for guild in bot.guilds:
            remind_channel = discord.utils.get(guild.text_channels, name=NOTIFY_CHANNEL)
            if remind_channel:
                events = await guild.fetch_scheduled_events()
                for event in events:
                    try:
                        if event.status == discord.EventStatus.scheduled:
                            interested_users = []
                            async for user in event.users():
                                interested_users.append(user)

                            thirty_min_before = event.start_time - timedelta(minutes=30)
                            five_min_before = event.start_time - timedelta(minutes=5)

                            if thirty_min_before <= now < thirty_min_before + timedelta(minutes=1):
                                mentions = " ".join(user.mention for user in interested_users)
                                message = f"Reminder! {event.name} is starting in 30 minutes! {event.url} \n{mentions}"
                                await remind_channel.send(message)
                            elif five_min_before <= now < five_min_before + timedelta(minutes=1):
                                mentions = " ".join(user.mention for user in interested_users)
                                message = f"Reminder! {event.name} is starting in 5 minutes! {event.url} \n{mentions}"
                                await remind_channel.send(message)
                    except Exception as e:
                        print(f"Error processing event {event.id}: {e}")

            # Non-Discord calendar events from the website database
            try:
                for minutes_ahead in [30, 5]:
                    window_start = now + timedelta(minutes=minutes_ahead)
                    window_end   = window_start + timedelta(minutes=1)
                    cal_events = await db_pool.fetch("""
                        SELECT ce.id, ce.title,
                               array_agg(u.discord_id) FILTER (WHERE u.discord_id IS NOT NULL) AS discord_ids
                        FROM calendar_events ce
                        LEFT JOIN calendar_event_interests cei ON cei.event_id = ce.id
                        LEFT JOIN users u ON u.id = cei.user_id
                        WHERE ce.event_time IS NOT NULL AND ce.event_timezone IS NOT NULL
                        GROUP BY ce.id, ce.title
                        HAVING (ce.event_date + ce.event_time) AT TIME ZONE ce.event_timezone
                               BETWEEN $1 AND $2
                    """, window_start, window_end)

                    for cal_event in cal_events:
                        discord_ids = [d for d in (cal_event['discord_ids'] or []) if d is not None]
                        remind_channel = discord.utils.get(guild.text_channels, name=NOTIFY_CHANNEL)
                        if not remind_channel:
                            continue
                        mentions = []
                        for discord_id in discord_ids:
                            member = guild.get_member(int(discord_id))
                            if member:
                                mentions.append(member.mention)
                        mention_str = " ".join(mentions)
                        message = f"Reminder! {cal_event['title']} is starting in {minutes_ahead} minutes!"
                        if mention_str:
                            message += f"\n{mention_str}"
                        await remind_channel.send(message)
            except Exception as e:
                print(f"Error checking calendar event reminders: {e}")
    except Exception as e:
        print(f"Error in event_reminder loop: {e}")


################# CHESTS #################
'''
def load_chest_events():
    global next_chest_events
    try:
        with open(CHEST_EVENTS_FILE, 'r') as f:
            data = json.load(f)
            # convert string times back to datetime objects.
            for server_group, group_data in data.items():
                for server, event_time in group_data.items():
                    if event_time:
                        data[server_group][server] = datetime.fromisoformat(event_time)
            next_chest_events = data
    except FileNotFoundError:
        return {
            "Arsha": {"PvP": None, "Anon": None},
            "Balenos": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Calpheon": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Serendia": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Kamasylvia": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Valencia": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Mediah": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None},
            "Velia": {"1": None, "2": None, "3": None, "4": None, "5": None, "6": None}
        }

def save_chest_events():
    #convert datetime objects into string for json storage.
    global next_chest_events
    data = deepcopy(next_chest_events)
    for server_group, group_data in data.items():
        for server, event_time in group_data.items():
            if event_time:
                data[server_group][server] = event_time.isoformat()
    with open(CHEST_EVENTS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def create_chest_embed():
    embed = discord.Embed(title='Chest Event Timers')
    for server_group, group_data in sorted(next_chest_events.items()):
        info_string = ""
        for server, event_time in group_data.items():
            if event_time:
                # Convert ISO 8601 string to datetime object
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time)
                timestamp = int(event_time.timestamp())
                info_string += f"{server}: <t:{timestamp}:F> <t:{timestamp}:R>\n"
            else:
                info_string += f"{server}: Not Set\n"
        embed.add_field(name=f'{server_group}', value=info_string, inline=True)
    return embed

@tasks.loop(minutes=1)
async def update_chest_info():
    global next_chest_events
    now = datetime.now(timezone.utc)
    info_channel = bot.get_channel(CHEST_INFO_CHANNEL_ID)
    if info_channel:
        try:
            info_message = await info_channel.fetch_message(CHEST_INFO_MESSAGE_ID)
            load_chest_events()
            for server_group, group_data in next_chest_events.items():
                for server_number, last_event_time in group_data.items():
                    if last_event_time is not None and now >= last_event_time:
                        next_event_time = last_event_time + timedelta(hours=3, minutes=13)
                        next_chest_events[server_group][server_number] = next_event_time
            save_chest_events()
            await info_message.edit(embed=create_chest_embed())

        except discord.NotFound:
            print(f"Error: Info message with ID {CHEST_INFO_MESSAGE_ID} not found in channel {CHEST_INFO_CHANNEL_ID}")
            update_chest_info.stop()
        except discord.Forbidden:
            print(f"Error: Bot does not have permission to access channel {CHEST_INFO_CHANNEL_ID} or message {CHEST_INFO_MESSAGE_ID}")
            update_chest_info.stop()
        except Exception as e:
            print(f"Error in update_chest_info loop: {e}")

@bot.command(name="chest")
async def chest(ctx, server: str, server_number: str, time_str: str):
    """Manually sets the next chest event time for a specific server.
    Usage: !chest <ServerName> <t:unix_timestamp:F> or None
    Example: !chest Serendia 4 <t:1744660549:F>
    Example: !chest Serendia 1 None
    """
    global next_chest_events
    for server_name, group_info in next_chest_events.items():
        if server == server_name:
            if time_str.lower() == "none":
                next_chest_events[server][server_number] = None
                save_chest_events()
                await update_chest_info()
            else:
                try:
                    parsed_time = parse_discord_timestamp(time_str)
                    next_chest_events[server][server_number] = parsed_time
                    save_chest_events()
                    await update_chest_info()
                except ValueError:
                    await ctx.send("Invalid Discord timestamp format. Please use <t:unix_timestamp:F> or 'None'.")
                    return
'''

################# GEAR #################
_ALLOWED_GEAR_COLS = {'gear_ap', 'gear_aap', 'gear_dp', 'gear_image_url'}

async def db_upsert_gear(discord_id: str, discord_username: str, **fields):
    """Upsert whitelisted gear fields for a user by discord_id.

    Resolution order:
      1. Update any existing row that already has this discord_id (linked account or prior stub).
      2. Auto-link to a web account whose username matches the Discord username and has no discord_id yet.
      3. Create a new stub using discord_username as the username (never discord_{id}).
    """
    fields = {k: v for k, v in fields.items() if k in _ALLOWED_GEAR_COLS}
    if not fields:
        return

    field_keys = list(fields.keys())
    set_clause = ', '.join(f'{k} = ${i + 3}' for i, k in enumerate(field_keys))
    base_params = [discord_id, discord_username] + list(fields.values())

    # Step 1: update existing row matched by discord_id
    result = await db_pool.execute(
        f"UPDATE users SET discord_username = $2, {set_clause}, updated_at = NOW() WHERE discord_id = $1",
        *base_params
    )
    if result != "UPDATE 0":
        return

    # Step 2: auto-link a web account whose username matches the Discord username
    # (same logic the OAuth flow uses — if the names match it's almost certainly the same person)
    result = await db_pool.execute(
        f"""UPDATE users
            SET discord_id = $1, discord_username = $2, {set_clause}, updated_at = NOW()
            WHERE username = $2 AND discord_id IS NULL""",
        *base_params
    )
    if result != "UPDATE 0":
        return

    # Step 3: no existing account — create a stub using the real Discord username, never discord_{id}
    col_list = ', '.join(field_keys)
    placeholders = ', '.join(f'${i + 4}' for i in range(len(field_keys)))
    set_clause_excl = ', '.join(f'{k} = EXCLUDED.{k}' for k in field_keys)
    insert_params = [discord_id, discord_username, discord_username] + list(fields.values())
    await db_pool.execute(
        f"""
        INSERT INTO users (discord_id, discord_username, username, password_hash, role, {col_list})
        VALUES ($1, $2, $3, '', 'member', {placeholders})
        ON CONFLICT (discord_id) DO UPDATE SET
            discord_username = EXCLUDED.discord_username,
            {set_clause_excl},
            updated_at = NOW()
        """,
        *insert_params
    )

async def db_get_user_gear(discord_id: str):
    """Returns a row with gear fields for the given discord_id, or None."""
    return await db_pool.fetchrow(
        "SELECT gear_ap, gear_aap, gear_dp, gear_image_url FROM users WHERE discord_id = $1",
        discord_id
    )

async def db_get_all_with_gs():
    """Returns all users who have all three gear score fields set."""
    return await db_pool.fetch(
        """SELECT discord_id, discord_username, gear_ap, gear_aap, gear_dp
           FROM users
           WHERE gear_ap IS NOT NULL AND gear_aap IS NOT NULL AND gear_dp IS NOT NULL
             AND discord_id IS NOT NULL"""
    )

@bot.command()
async def gear(ctx, *, image_url: str = None):
    """Saves, updates, or retrieves a gear image URL for a specific user.
    Can also save an attached image if no URL is provided.
    """
    print("gear command")
    discord_id = str(ctx.author.id)
    discord_username = ctx.author.name
    attached_image_url = None

    if ctx.message.attachments:
        attached_image_url = ctx.message.attachments[0].url

    if image_url and 'http' in image_url and '<@' not in image_url:
        print('save url')
        await db_upsert_gear(discord_id, discord_username, gear_image_url=image_url)
        await ctx.send(f"Gear image URL saved/updated for {ctx.author.name}.")
    elif attached_image_url:
        print('save attachment url')
        await db_upsert_gear(discord_id, discord_username, gear_image_url=attached_image_url)
        await ctx.send(f"Gear image from attachment saved/updated for {ctx.author.name}.")
    elif image_url and '<@' in image_url:
        print("checkgear")
        await checkgear(ctx, ctx.guild.get_member(int(image_url[2:-1])))
    else:
        print("show gear")
        row = await db_get_user_gear(discord_id)
        if row and row['gear_image_url']:
            await ctx.reply(row['gear_image_url'])
        else:
            await ctx.reply("You have not saved a gear image URL yet. Use `!gear <image_url>` or attach an image to save one.")

@bot.command()
async def checkgear(ctx, target_user: discord.Member):
    """Retrieves the gear image URL for a mentioned user."""
    print('checkgear command')
    row = await db_get_user_gear(str(target_user.id))
    if row and row['gear_image_url']:
        await ctx.reply(row['gear_image_url'])
    else:
        await ctx.reply(f"{target_user.name} has not saved a gear image URL yet.")


################# GS #################
INVALID_STAT_RESPONSES = [
    "Bro really said {value}. Be serious.",
    "There is no way you actually typed that with a straight face.",
    "I don't know what game you think you're playing, but it's not this one.",
    "Cute number. Put in a real one.",
    "lmaooo no.",
    "I've seen better numbers from a keyboard smash.",
    "Sir/Ma'am this is a Wendy's.",
]

def calculate_gs(ap, aap, dp):
    return (ap + aap) / 2 + dp

@bot.command()
async def setap(ctx, ap: int):
    """Saves the AP stat for the user."""
    if ap < 0 or ap > 666:
        await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=ap))
        return
    print(f"setap command: {ctx.author.name} ({ctx.author.id}) -> AP={ap}")
    await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_ap=ap)
    await ctx.send(f"AP set to {ap} for {ctx.author.name}.")

@bot.command()
async def setaap(ctx, aap: int):
    """Saves the AAP stat for the user."""
    if aap < 0 or aap > 666:
        await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=aap))
        return
    print(f"setaap command: {ctx.author.name} ({ctx.author.id}) -> AAP={aap}")
    await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_aap=aap)
    await ctx.send(f"AAP set to {aap} for {ctx.author.name}.")

@bot.command()
async def setdp(ctx, dp: int):
    """Saves the DP stat for the user."""
    if dp < 0 or dp > 911:
        await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=dp))
        return
    print(f"setdp command: {ctx.author.name} ({ctx.author.id}) -> DP={dp}")
    await db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_dp=dp)
    await ctx.send(f"DP set to {dp} for {ctx.author.name}.")

@bot.command()
async def showgs(ctx):
    """Displays the AP, AAP, DP, and GS for the user."""
    print(f"showgs command: {ctx.author.name} ({ctx.author.id})")
    row = await db_get_user_gear(str(ctx.author.id))
    if row and row['gear_ap'] is not None and row['gear_aap'] is not None and row['gear_dp'] is not None:
        ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
        gs = calculate_gs(ap, aap, dp)
        await ctx.send(f"**{ctx.author.name}'s Gear Score:**\nAP: {ap}\nAAP: {aap}\nDP: {dp}\nGS: {gs}")
    else:
        await ctx.send("Please set your AP, AAP, and DP using !setap, !setaap, and !setdp.")

@bot.command()
async def gs(ctx):
    """Displays the AP, AAP, DP, and GS for the user."""
    await showgs(ctx)

async def create_table(ctx, sort_on_col, reverse, members_only=True):
    print(f"create_table: requested by {ctx.author.name} ({ctx.author.id}), sort_col={sort_on_col}, reverse={reverse}, members_only={members_only}")
    rows = await db_get_all_with_gs()
    if members_only:
        member_role = ctx.guild.get_role(GUILD_MEMBER_ROLE_ID)
        member_map = {str(m.id): m for m in member_role.members} if member_role else {}
    else:
        member_map = {str(m.id): m for m in ctx.guild.members}
    leaderboard = []
    for row in rows:
        member = member_map.get(row['discord_id'])
        if members_only and not member:
            continue  # skip users without the guild member role
        ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
        gs_val = calculate_gs(ap, aap, dp)
        name = member.name if member else (row['discord_username'] or row['discord_id'])
        leaderboard.append((name, ap, aap, dp, gs_val))

    if not leaderboard:
        await ctx.send("No gear score data available.")
        return None

    leaderboard.sort(key=lambda x: x[sort_on_col], reverse=reverse)
    return leaderboard

@bot.command(aliases=['gsguild', 'guildgs'])
async def showguildgs(ctx):
    """Displays the GS of everyone in guild who has saved gs."""
    print(f"showguildgs command: {ctx.author.name} ({ctx.author.id})")
    leaderboard = await create_table(ctx, 0, False)

    if not leaderboard:
        return

    headers = ["User", "AP", "AAP", "DP", "GS"]
    full_table = tabulate(leaderboard, headers=headers, tablefmt="pretty")

    if len(full_table) < 1900:
        await ctx.send(f"```\n{full_table}\n```")
    else:
        # If the table is too long, we split it by lines
        lines = full_table.split("\n")
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk) + len(line) > 1900:
                await ctx.send(f"```\n{current_chunk}\n```")
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        # Send the final remaining chunk
        if current_chunk:
            await ctx.send(f"```\n{current_chunk}\n```")

@bot.command()
async def gslb(ctx):
    """Displays the ranking of GS of everyone in guild who has saved gs."""
    print(f"gslb command: {ctx.author.name} ({ctx.author.id})")
    leaderboard = await create_table(ctx, 4, True) # Sorted by GS
    if not leaderboard:
        return

    view = LeaderboardPagination(leaderboard, "Guild Gear Score Leaderboard", ctx.author.id)
    await ctx.send(embed=view.create_embed(), view=view)

@bot.command()
async def gsall(ctx):
    """Displays the GS ranking of everyone who has saved gs, including non-members."""
    print(f"gsall command: {ctx.author.name} ({ctx.author.id})")
    leaderboard = await create_table(ctx, 4, True, members_only=False)
    if not leaderboard:
        return

    view = LeaderboardPagination(leaderboard, "All Gear Score Leaderboard", ctx.author.id)
    await ctx.send(embed=view.create_embed(), view=view)

@bot.command()
async def oldgslb(ctx):
    """Displays the ranking of GS of everyone in guild who has saved gs."""
    print(f"oldgslb command: {ctx.author.name} ({ctx.author.id})")
    leaderboard = await create_table(ctx, 4, True)

    headers = ["User", "AP", "AAP", "DP", "GS"]
    full_table = tabulate(leaderboard, headers=headers, tablefmt="pretty")  # Display all

    if len(full_table) < 1900:
        await ctx.send(f"```\n{full_table}\n```")
    else:
        # If the table is too long, we split it by lines
        lines = full_table.split("\n")
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk) + len(line) > 1900:
                await ctx.send(f"```\n{current_chunk}\n```")
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        # Send the final remaining chunk
        if current_chunk:
            await ctx.send(f"```\n{current_chunk}\n```")

# --- PAGINATION VIEW CLASS ---
class LeaderboardPagination(discord.ui.View):
    def __init__(self, data, title, author_id):
        super().__init__(timeout=60)
        self.data = data
        self.title = title
        self.author_id = author_id  
        self.per_page = 20
        self.current_page = 0
        self.total_pages = (len(data) - 1) // self.per_page + 1

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_slice = self.data[start:end]

        headers = ["User", "AP", "AAP", "DP", "GS"]
        table = tabulate(page_slice, headers=headers, tablefmt="pretty")
        
        embed = discord.Embed(
            title=self.title,
            description=f"```\n{table}\n```",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This isn't your leaderboard! Use the command yourself to navigate.", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

################# QUOTES #################

import string as _string
import io
import yaml
_QUOTE_ID_CHARS = _string.ascii_lowercase + _string.digits  # a-z0-9, matches Nadeko's format

async def _generate_quote_id() -> str:
    """Generate a unique 5-char alphanumeric ID not already in the quotes table."""
    while True:
        new_id = ''.join(random.choices(_QUOTE_ID_CHARS, k=5))
        exists = await db_pool.fetchrow("SELECT 1 FROM quotes WHERE nadeko_id = $1", new_id)
        if not exists:
            return new_id

async def _is_admin(discord_id: str) -> bool:
    row = await db_pool.fetchrow(
        "SELECT role FROM users WHERE discord_id = $1", discord_id
    )
    return row is not None and row['role'] == 'admin'


class QuoteListView(discord.ui.View):
    def __init__(self, rows, title, per_page=15):
        super().__init__(timeout=120)
        self.rows = rows
        self.title = title
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = max(1, (len(rows) + per_page - 1) // per_page)
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def create_embed(self):
        start = self.current_page * self.per_page
        page = self.rows[start:start + self.per_page]
        lines = [
            f"`{r['nadeko_id']}` :  {r['keyword']} by {r['author_name'] or 'unknown'}"
            for r in page
        ]
        embed = discord.Embed(
            title=self.title,
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} \u00b7 {len(self.rows)} quotes total")
        return embed

    @discord.ui.button(label="\u25c4 Prev", style=discord.ButtonStyle.gray)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next \u25ba", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


@bot.command(name="quotelist", aliases=["ql", "qli"])
async def quotelist(ctx, *, keyword: str = None):
    """Lists quotes with pagination. Optionally filter by keyword.
    Usage: !quotelist [keyword]
    """
    if keyword:
        rows = await db_pool.fetch(
            """SELECT nadeko_id, keyword, author_name FROM quotes
               WHERE keyword ILIKE $1 ORDER BY created_at ASC""",
            keyword.strip()
        )
        title = f"Quotes \u2013 {keyword.upper()}"
    else:
        rows = await db_pool.fetch(
            """SELECT nadeko_id, keyword, author_name FROM quotes
               ORDER BY keyword ASC, created_at ASC"""
        )
        title = "All Quotes"

    if not rows:
        msg = f"No quotes found for **{keyword}**." if keyword else "No quotes in the archive."
        await ctx.send(msg)
        return

    view = QuoteListView(rows, title)
    await ctx.send(embed=view.create_embed(), view=view)


@bot.command(name="quoteprint", aliases=["qp", "q", "!!"])
async def quoteprint(ctx, *, keyword: str):
    """Prints a random quote for the given keyword.
    Usage: !quoteprint <keyword>
           !q <keyword>
    """
    rows = await db_pool.fetch(
        "SELECT nadeko_id, text FROM quotes WHERE keyword ILIKE $1",
        keyword.strip()
    )
    if not rows:
        await ctx.send(f"No quotes found for keyword **{keyword}**.")
        return

    quote = random.choice(rows)
    await ctx.reply(f"`{quote['nadeko_id']}` 📣 {quote['text']}")


@bot.command(name="quoteshow", aliases=["qshow"])
async def quoteshow(ctx, quote_id: str):
    """Shows full details of a quote by its ID.
    Usage: !quoteshow <id>
    """
    row = await db_pool.fetchrow(
        "SELECT nadeko_id, keyword, text, author_name, author_discord_id FROM quotes WHERE nadeko_id = $1",
        quote_id.lower()
    )
    if not row:
        await ctx.send(f"Quote `{quote_id}` not found.")
        return

    author_str = row['author_name'] or 'unknown'
    if row['author_discord_id']:
        author_str += f" ({row['author_discord_id']})"

    embed = discord.Embed(
        title=f"Quote {row['nadeko_id']}",
        description=row['text'],
        color=discord.Color.blurple()
    )
    embed.add_field(name="Trigger", value=row['keyword'], inline=True)
    embed.set_footer(text=f"Created by {author_str}.")
    await ctx.send(embed=embed)


@bot.command(name="quoteadd", aliases=["qa"])
async def quoteadd(ctx, keyword: str, *, text: str):
    """Adds a new quote to the archive.
    Usage: !quoteadd <keyword> <quote text>
    """
    if not keyword or not text:
        await ctx.send("Usage: `!quoteadd <keyword> <quote text>`")
        return

    keyword = keyword.upper()
    new_id = await _generate_quote_id()
    author_name = ctx.author.name
    author_discord_id = str(ctx.author.id)

    await db_pool.execute(
        """INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text)
           VALUES ($1, $2, $3, $4, $5)""",
        keyword, new_id, author_name, author_discord_id, text
    )

    await ctx.send(f"Quote added! ID: `{new_id}` \u2013 **{keyword}**")


@bot.command(name="quotedelete", aliases=["qd", "qdel"])
async def quotedelete(ctx, quote_id: str):
    """Deletes a quote by ID. Only the creator or an officer/admin can delete.
    Usage: !quotedelete <id>
    """
    row = await db_pool.fetchrow(
        "SELECT nadeko_id, keyword, author_discord_id FROM quotes WHERE nadeko_id = $1",
        quote_id.lower()
    )
    if not row:
        await ctx.send(f"Quote `{quote_id}` not found.")
        return

    caller_id = str(ctx.author.id)
    is_creator = row['author_discord_id'] == caller_id
    is_admin   = await _is_admin(caller_id)

    if not is_creator and not is_admin:
        await ctx.send("You can only delete your own quotes (or be an admin).")
        return

    await db_pool.execute("DELETE FROM quotes WHERE nadeko_id = $1", quote_id.lower())
    await ctx.send(f"Quote `{quote_id}` ({row['keyword']}) deleted.")


@bot.command(name="quotesearch", aliases=["qsearch", "qfind"])
async def quotesearch(ctx, keyword: str, *, search_term: str):
    """Search for quotes within a keyword containing a specific term.
    Usage: !quotesearch <keyword> <search term>
    """
    rows = await db_pool.fetch(
        """SELECT nadeko_id, keyword, author_name FROM quotes
           WHERE keyword ILIKE $1 AND text ILIKE $2
           ORDER BY created_at ASC""",
        keyword.strip(), f"%{search_term}%"
    )
    if not rows:
        await ctx.send(f"No quotes in **{keyword}** matching `{search_term}`.")
        return

    view = QuoteListView(rows, f"Search: {keyword.upper()} \u00b7 \"{search_term}\"")
    await ctx.send(embed=view.create_embed(), view=view)


class ConfirmView(discord.ui.View):
    """Generic confirm/cancel prompt. Only the invoking user can interact."""
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("Cancelled.", ephemeral=True)


@bot.command(name="quotedeleteauthor", aliases=["qda"])
async def quotedeleteauthor(ctx, member: discord.Member):
    """(Admin only) Deletes all quotes added by the specified user.
    Usage: !quotedeleteauthor @user
    """
    if not await _is_admin(str(ctx.author.id)):
        await ctx.send("This command is admin only.")
        return

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM quotes WHERE author_discord_id = $1",
        str(member.id)
    )
    if not count:
        await ctx.send(f"No quotes found by **{member.name}**.")
        return

    view = ConfirmView(ctx.author.id)
    msg = await ctx.send(
        f"⚠️ This will delete **{count}** quote(s) by **{member.name}**. Are you sure?",
        view=view
    )
    await view.wait()

    if view.confirmed:
        await db_pool.execute(
            "DELETE FROM quotes WHERE author_discord_id = $1", str(member.id)
        )
        await msg.edit(content=f"Deleted **{count}** quote(s) by **{member.name}**.", view=None)
    else:
        await msg.edit(content="Cancelled.", view=None)


@bot.command(name="quotesdeleteall", aliases=["qdall"])
async def quotesdeleteall(ctx, *, keyword: str = None):
    """(Admin only) Deletes all quotes, or all quotes for a specific keyword.
    Usage: !quotesdeleteall
           !quotesdeleteall <keyword>
    """
    if not await _is_admin(str(ctx.author.id)):
        await ctx.send("This command is admin only.")
        return

    if keyword:
        count = await db_pool.fetchval(
            "SELECT COUNT(*) FROM quotes WHERE keyword ILIKE $1", keyword.strip()
        )
        warning = f"⚠️ This will delete **{count}** quote(s) for keyword **{keyword.upper()}**. Are you sure?"
    else:
        count = await db_pool.fetchval("SELECT COUNT(*) FROM quotes")
        warning = f"⚠️ This will delete **ALL {count}** quotes from the archive. Are you sure?"

    if not count:
        await ctx.send("No quotes to delete.")
        return

    view = ConfirmView(ctx.author.id)
    msg = await ctx.send(warning, view=view)
    await view.wait()

    if view.confirmed:
        if keyword:
            await db_pool.execute("DELETE FROM quotes WHERE keyword ILIKE $1", keyword.strip())
            await msg.edit(content=f"Deleted **{count}** quote(s) for **{keyword.upper()}**.", view=None)
        else:
            await db_pool.execute("DELETE FROM quotes")
            await msg.edit(content=f"Deleted all **{count}** quotes.", view=None)
    else:
        await msg.edit(content="Cancelled.", view=None)


@bot.command(name="quotesexport", aliases=["qexport", "qex"])
async def quotesexport(ctx):
    """(Admin only) Exports all quotes as a Nadeko-compatible YAML file.
    Usage: !quotesexport
    """
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
        kw = row['keyword']
        if kw not in data:
            data[kw] = []
        data[kw].append({
            'id':  row['nadeko_id'] or '',
            'an':  row['author_name'] or '',
            'aid': int(row['author_discord_id']) if row['author_discord_id'] else 0,
            'txt': row['text'],
        })

    yml_bytes = yaml.dump(data, allow_unicode=True, sort_keys=False).encode('utf-8')
    file = discord.File(io.BytesIO(yml_bytes), filename="quotes-export.yml")
    await ctx.send(f"Exported **{len(rows)}** quotes.", file=file)


@bot.command(name="quotesimport", aliases=["qimport", "qim"])
async def quotesimport(ctx):
    """(Admin only) Imports quotes from an attached Nadeko-compatible YAML file.
    Skips any quote whose nadeko_id already exists in the database.
    Usage: !quotesimport  (attach a .yml file)
    """
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

    inserted = 0
    skipped  = 0
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
                """INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (nadeko_id) DO NOTHING""",
                str(keyword).upper(), nadeko_id, author_name, author_id, text
            )
            if result == "INSERT 0 1":
                inserted += 1
            else:
                skipped += 1

    await ctx.send(f"Import complete. Inserted: **{inserted}** · Skipped/duplicate: **{skipped}**")


################# 8BALL #################
_8BALL_RESPONSES = [
    # Positive
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes, definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    # Neutral
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    # Negative
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
]

_8BALL_CACHE = {}  # (user_id, normalized_question) -> (response, expiry)
_8BALL_TTL = timedelta(hours=1)

@bot.command(name='8ball')
async def eightball(ctx, *, question: str = None):
    """Ask the magic 8-ball a question."""
    print(f"8ball command: {ctx.author.name} ({ctx.author.id}) -> '{question}'")
    if not question:
        await ctx.send("You need to ask a question! Usage: `!8ball <your question>`")
        return

    normalized = question.lower().strip().rstrip('?').strip()
    key = (ctx.author.id, normalized)
    now = datetime.now(timezone.utc)

    cached = _8BALL_CACHE.get(key)
    if cached and now < cached[1]:
        response = cached[0]
    else:
        response = random.choice(_8BALL_RESPONSES)
        _8BALL_CACHE[key] = (response, now + _8BALL_TTL)

    await ctx.send(f"🎱 {response}")

################# CHATBOT #################
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
CHATBOT_CONTEXT_FILE = os.getenv("CHATBOT_CONTEXT_FILE", "chatbot_context.txt")
import google.generativeai as genai

# Configure the API key from an environment variable
genai.configure(api_key=GOOGLE_API_KEY)
# Create a GenerativeModel instance
models = [
            'gemini-2.5-flash-lite',
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'gemini-2.5-pro']
model = 0

with open(CHATBOT_CONTEXT_FILE, 'r') as f:
    context = f.read()

# Start a new chat session
chat = genai.GenerativeModel(models[model]).start_chat(history=[])

response = chat.send_message(context)
print(response)

@bot.command()
async def resetchat(ctx):
    global models
    global model
    global chat
    global context

    # Start a new chat session
    model = (model+1)%5
    chat = genai.GenerativeModel(models[model]).start_chat(history=[])
    response = chat.send_message(context)
    print(response)

    await ctx.send(f"Chat has been reset. Model changed to {models[model]}")


@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself to prevent infinite loops.
    if message.author == bot.user:
        return

    # Check if the message starts with a mention of the bot.
    if bot.user.mentioned_in(message):
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        print(f"Received query: '{content}' from {message.author}")
        
        # If the query is empty after removing the mention, just ignore it.
        if not content:
            return

        message_data = {
            "user_id": message.author.id,
            "user_name": message.author.name,
            "display_name": message.author.display_name,
            "guild_id": message.guild.id,
            "channel_id": message.channel.id,
            "content": content
        }
        global chat

        # show the bot is typing
        async with message.channel.typing():
            try:        
                json_string = json.dumps(message_data, indent=4)
                response = chat.send_message(json_string)
                reply = response.text
                print(f'{response.text[:100]}')
                while len(reply) > 2000:
                    r, reply = splitReplyToLessThan2000(reply)
                    await message.reply(r)
                await message.reply(reply)
            except Exception as e:
                print(e)
                await message.reply(f"Sorry, something went wrong. \n{e}")
    else:
        await bot.process_commands(message) 

def splitReplyToLessThan2000(reply):
    for i in range(1999, 0, -1):
        if reply[i] == '\n':
            return reply[:i], reply[i:]
    for i in range(1999, 0, -1):
        if reply[i] == ' ':
            return reply[:i], reply[i:]
    return reply[:1999], reply[1999:]

@bot.event
async def on_command_error(ctx, error):
    # Unwrap CheckFailure / CommandInvokeError wrappers to get the real cause
    error = getattr(error, 'original', error)
    print(f"[ERROR] Command '{ctx.command}' raised an exception: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    if not event_reminder.is_running():
        event_reminder.start()
    if not update_chest_info.is_running():
        info_channel = bot.get_channel(CHEST_INFO_CHANNEL_ID)
        global CHEST_INFO_MESSAGE_ID

        if info_channel and CHEST_INFO_MESSAGE_ID is None:
            # Create the initial info message
            try:
                initial_message = await info_channel.send(embed=create_chest_embed())
                CHEST_INFO_MESSAGE_ID = initial_message.id
                print(f"Initial chest info message created with ID: {CHEST_INFO_MESSAGE_ID}")
                update_chest_info.start()  # Start the update task after creating the message
            except discord.Forbidden:
                print(f"Error: Bot does not have permission to send messages in channel {CHEST_INFO_CHANNEL_ID}")
            except Exception as e:
                print(f"Error creating initial info message: {e}")
        elif info_channel and CHEST_INFO_MESSAGE_ID is not None:
            update_chest_info.start()  # Start the update task if the message ID is already set
        elif not info_channel:
            print(f"Error: Info channel with ID {INFO_CHANNEL_ID} not found.")

async def main():
    global db_pool
    async with bot:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        print("Database pool created.")
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
