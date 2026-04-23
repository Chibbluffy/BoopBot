import discord, random
from datetime import datetime, timedelta, timezone
from discord.ext import commands
import utils

BEG_LINES = [
    "Here, take this and never speak of it again.",
    "You absolute scrub. Fine.",
    "This is painful to watch. Take it.",
    "I've seen rocks with more dignity.",
    "Please, for the love of — just take it.",
    "Don't spend it all in one place. Actually, please do.",
    "I'm embarrassed for you. Here.",
]


class EconomyCog(commands.Cog, name="Economy"):

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        """Check your boop balance (or another user's)."""
        target = member or ctx.author
        boops  = await utils.get_boops(str(target.id))
        await ctx.send(f"💰 **{target.display_name}** has **{boops:,}** boops.")

    @commands.command(name="daily")
    async def daily(self, ctx):
        """Collect 100 boops. Usable once every 23 hours."""
        discord_id = str(ctx.author.id)
        await utils.ensure_economy_user(discord_id, ctx.author.name)
        row = await utils.pool.fetchrow(
            "SELECT daily_last FROM users WHERE discord_id = $1", discord_id
        )
        now = datetime.now(timezone.utc)
        if row and row["daily_last"]:
            delta = now - row["daily_last"]
            if delta.total_seconds() < 23 * 3600:
                remaining = timedelta(hours=23) - delta
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m = rem // 60
                await ctx.send(f"⏳ Already collected today. Come back in **{h}h {m}m**.")
                return
        await utils.pool.execute(
            "UPDATE users SET daily_last = $2 WHERE discord_id = $1", discord_id, now
        )
        new_bal = await utils.add_boops(discord_id, 100, ctx.author.name)
        await ctx.send(f"✅ {ctx.author.mention} collected **100** boops! Balance: **{new_bal:,}**")

    @commands.command(name="beg")
    async def beg(self, ctx):
        """Beg for boops. Only works when you have fewer than 100."""
        boops = await utils.get_boops(str(ctx.author.id))
        if boops >= 100:
            await ctx.send("You're not poor enough to beg. (Need < 100 boops)")
            return
        amount  = random.randint(1, 50)
        new_bal = await utils.add_boops(str(ctx.author.id), amount, ctx.author.name)
        await ctx.send(f"🙏 {random.choice(BEG_LINES)}\n{ctx.author.mention} received **{amount}** boops. Balance: **{new_bal:,}**")

    @commands.command(name="give")
    async def give(self, ctx, member: discord.Member, amount: int):
        """Give boops to another user. Usage: !give @user <amount>"""
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        if member.id == ctx.author.id:
            await ctx.send("You can't give boops to yourself.")
            return
        ok = await utils.transfer_boops(str(ctx.author.id), str(member.id), amount)
        if not ok:
            await ctx.send("You don't have enough boops.")
            return
        await ctx.send(f"💸 **{ctx.author.display_name}** gave **{amount:,}** boops to **{member.display_name}**.")

    @commands.command(name="award")
    async def award(self, ctx, member: discord.Member, amount: int):
        """(Admin) Award boops to a user out of thin air. Usage: !award @user <amount>"""
        if not await utils.is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        new_bal = await utils.add_boops(str(member.id), amount, member.name)
        await ctx.send(f"🏅 **{ctx.author.display_name}** awarded **{amount:,}** boops to **{member.display_name}**. Their balance: **{new_bal:,}**")

    @commands.command(name="richest", aliases=["booplb"])
    async def richest(self, ctx):
        """Top boop leaderboard."""
        rows = await utils.pool.fetch(
            """SELECT COALESCE(NULLIF(discord_username,''), username) AS name, boops
               FROM users WHERE boops > 0 AND discord_id IS NOT NULL
               ORDER BY boops DESC LIMIT 10"""
        )
        if not rows:
            await ctx.send("No one has any boops yet.")
            return
        lines = [f"**{i+1}.** {r['name']} — **{r['boops']:,}** boops" for i, r in enumerate(rows)]
        embed = discord.Embed(title="💰 Richest Frogs", description="\n".join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
