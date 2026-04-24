import discord, random
from discord.ext import commands
from wcwidth import wcswidth
import utils

INVALID_STAT_RESPONSES = [
    "Bro really said {value}. Be serious.",
    "There is no way you actually typed that with a straight face.",
    "I don't know what game you think you're playing, but it's not this one.",
    "Cute number. Put in a real one.",
    "lmaooo no.",
    "I've seen better numbers from a keyboard smash.",
    "Sir/Ma'am this is a Wendy's.",
]


def _wc_ljust(s: str, width: int) -> str:
    """Left-justify s in a field of display-width `width`, accounting for wide chars."""
    pad = width - wcswidth(s)
    return s + " " * max(pad, 0)

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

        # Build row data
        rows = []
        for i, (name, ap, aap, dp, gs) in enumerate(page_slice):
            rank   = start + i + 1
            label  = f"{rank:2}. {name}"
            gs_str = str(int(gs)) if gs else "—"
            st_str = f"{ap or '—':>3} · {aap or '—':>3} · {dp or '—':>3}"
            rows.append((label, gs_str, st_str))

        # Column widths based on actual display width
        name_w = max(wcswidth(r[0]) for r in rows)
        gs_w   = max(len(r[1]) for r in rows)

        header_name = _wc_ljust("Name", name_w)
        header      = f"{header_name}  {'GS':>{gs_w}}  AP  · AAP ·  DP"
        divider     = "-" * (name_w + gs_w + 18)

        lines = [header, divider]
        for label, gs_str, st_str in rows:
            lines.append(f"{_wc_ljust(label, name_w)}  {gs_str:>{gs_w}}  {st_str}")

        embed = discord.Embed(
            title=self.title,
            description="```\n" + "\n".join(lines) + "\n```",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your leaderboard!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction, button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)


class LeaderboardNewPagination(discord.ui.View):
    def __init__(self, data, title, author_id):
        super().__init__(timeout=60)
        self.data         = data
        self.title        = title
        self.author_id    = author_id
        self.per_page     = 15
        self.current_page = 0
        self.total_pages  = (len(data) - 1) // self.per_page + 1

    def create_embed(self):
        start      = self.current_page * self.per_page
        page_slice = self.data[start:start + self.per_page]

        lines = []
        for i, (name, ap, aap, dp, gs) in enumerate(page_slice):
            rank   = start + i + 1
            gs_str = str(int(gs)) if gs else "—"
            ap_str  = str(ap)  if ap  else "—"
            aap_str = str(aap) if aap else "—"
            dp_str  = str(dp)  if dp  else "—"
            lines.append(f"**{rank}. {name}**")
            lines.append(f"GS {gs_str}  ·  {ap_str} / {aap_str} / {dp_str}")
            lines.append("")

        embed = discord.Embed(
            title=self.title,
            description="\n".join(lines).rstrip(),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"AP / AAP / DP  ·  Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your leaderboard!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction, button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)


class GearCog(commands.Cog, name="Gear"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def gear(self, ctx, *, image_url: str = None):
        """Saves, updates, or retrieves your gear image. Attach an image or provide a URL."""
        discord_id   = str(ctx.author.id)
        attached_url = ctx.message.attachments[0].url if ctx.message.attachments else None

        if image_url and 'http' in image_url and '<@' not in image_url:
            await utils.db_upsert_gear(discord_id, ctx.author.name, gear_image_url=image_url)
            await ctx.send(f"Gear image saved for {ctx.author.name}.")
        elif attached_url:
            await utils.db_upsert_gear(discord_id, ctx.author.name, gear_image_url=attached_url)
            await ctx.send(f"Gear image saved for {ctx.author.name}.")
        elif image_url and '<@' in image_url:
            member = ctx.guild.get_member(int(image_url[2:-1]))
            await self.checkgear(ctx, member)
        else:
            row = await utils.db_get_user_gear(discord_id)
            if row and row['gear_image_url']:
                await ctx.reply(row['gear_image_url'])
            else:
                await ctx.reply("No gear image saved. Use `!gear <url>` or attach an image.")

    @commands.command()
    async def checkgear(self, ctx, target_user: discord.Member):
        """Retrieves the gear image for a mentioned user. Usage: !checkgear @user"""
        row = await utils.db_get_user_gear(str(target_user.id))
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
        await utils.db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_ap=ap)
        await ctx.send(f"AP set to {ap} for {ctx.author.name}.")

    @commands.command()
    async def setaap(self, ctx, aap: int):
        """Saves your AAP. Usage: !setaap <value>"""
        if aap < 0 or aap > 666:
            await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=aap))
            return
        await utils.db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_aap=aap)
        await ctx.send(f"AAP set to {aap} for {ctx.author.name}.")

    @commands.command()
    async def setdp(self, ctx, dp: int):
        """Saves your DP. Usage: !setdp <value>"""
        if dp < 0 or dp > 911:
            await ctx.send(random.choice(INVALID_STAT_RESPONSES).format(value=dp))
            return
        await utils.db_upsert_gear(str(ctx.author.id), ctx.author.name, gear_dp=dp)
        await ctx.send(f"DP set to {dp} for {ctx.author.name}.")

    @commands.command(aliases=['gs'])
    async def showgs(self, ctx):
        """Shows your AP, AAP, DP, and GS."""
        row = await utils.db_get_user_gear(str(ctx.author.id))
        if row and all(row[k] is not None for k in ('gear_ap', 'gear_aap', 'gear_dp')):
            ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
            await ctx.send(f"**{ctx.author.name}'s Gear Score:**\nAP: {ap}\nAAP: {aap}\nDP: {dp}\nGS: {utils.calculate_gs(ap, aap, dp)}")
        else:
            await ctx.send("Set your stats with `!setap`, `!setaap`, and `!setdp` first.")

    @commands.command(aliases=['gsguild', 'guildgs'])
    async def showguildgs(self, ctx):
        """Shows the GS of all guild members, sorted alphabetically."""
        leaderboard = await self._build_table(ctx, sort_col=0, reverse=False)
        if not leaderboard:
            return
        view = LeaderboardPagination(leaderboard, "Guild Gear Scores", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command()
    async def gslb(self, ctx):
        """GS leaderboard for guild members (paginated)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True)
        if not leaderboard:
            return
        view = LeaderboardPagination(leaderboard, "Guild Gear Score Leaderboard", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command()
    async def gslbnew(self, ctx):
        """GS leaderboard (new layout, two lines per entry)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True)
        if not leaderboard:
            return
        view = LeaderboardNewPagination(leaderboard, "Guild Gear Score Leaderboard", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command()
    async def gsall(self, ctx):
        """GS leaderboard including non-members (paginated)."""
        leaderboard = await self._build_table(ctx, sort_col=4, reverse=True, members_only=False)
        if not leaderboard:
            return
        view = LeaderboardPagination(leaderboard, "All Gear Score Leaderboard", ctx.author.id)
        await ctx.send(embed=view.create_embed(), view=view)

    async def _build_table(self, ctx, sort_col, reverse, members_only=True):
        rows = await utils.db_get_all_with_gs()
        role_id = utils.GUILD_MEMBER_ROLE_ID
        if members_only and role_id:
            member_map = {
                str(m.id): m for m in ctx.guild.members
                if any(r.id == role_id for r in m.roles)
            }
        else:
            member_map = {str(m.id): m for m in ctx.guild.members}

        leaderboard = []
        for row in rows:
            member = member_map.get(row['discord_id'])
            if members_only and not member:
                continue
            ap, aap, dp = row['gear_ap'], row['gear_aap'], row['gear_dp']
            name = member.display_name if member else (row['discord_username'] or row['discord_id'])
            leaderboard.append((name, ap, aap, dp, utils.calculate_gs(ap, aap, dp)))

        if not leaderboard:
            await ctx.send("No gear score data available.")
            return None
        leaderboard.sort(key=lambda x: x[sort_col], reverse=reverse)
        return leaderboard


async def setup(bot):
    await bot.add_cog(GearCog(bot))
