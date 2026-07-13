import discord, random
from datetime import timedelta, timezone, datetime
from discord.ext import commands
import utils


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
        self.bot       = bot
        self._8ball_cache: dict = {}
        self._ttl = timedelta(hours=1)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if not self.bot.user.mentioned_in(message):
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
        if not content:
            return
        async with message.channel.typing():
            try:
                reply = await utils.brain_generate(
                    guild_id=message.guild.id, channel_id=message.channel.id,
                    user_id=message.author.id, user_name=message.author.name,
                    display_name=message.author.display_name, content=content,
                    is_mention=True,
                )
                while len(reply) > 2000:
                    r, reply = utils.split_reply(reply)
                    await message.reply(r)
                await message.reply(reply)
            except Exception as e:
                await message.reply(f"Sorry, something went wrong.\n{e}")

    @commands.command(name='8ball')
    async def eightball(self, ctx, *, question: str = None):
        """Ask the magic 8-ball a question. Usage: !8ball <question>"""
        if not question:
            await ctx.send("Ask a question! Usage: `!8ball <question>`")
            return
        normalized = question.lower().strip().rstrip('?').strip()
        key        = (ctx.author.id, normalized)
        now        = datetime.now(timezone.utc)
        cached     = self._8ball_cache.get(key)
        if cached and now < cached[1]:
            response = cached[0]
        else:
            response = random.choice(self._8BALL_RESPONSES)
            self._8ball_cache[key] = (response, now + self._ttl)
        await ctx.send(f"🎱 {response}")

    @commands.command(name="roll")
    async def roll(self, ctx, maximum: int = 100):
        """Roll a random number from 1 to N (default 100). Usage: !roll [max]"""
        if maximum < 2:
            await ctx.send("Give me a number greater than 1 to roll!")
            return
        result = random.randint(1, maximum)
        if result == 1:
            embed = discord.Embed(
                title="🔴 CRITICAL FAIL",
                description=f"# **{result:,}**",
                color=discord.Color.red(),
            )
            embed.set_footer(text="F.")
        elif result == maximum:
            embed = discord.Embed(
                title="🌟 CRITICAL SUCCESS",
                description=f"# **{result:,}**",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Insane.")
        else:
            embed = discord.Embed(
                description=f"# **{result:,}**",
                color=discord.Color.blurple(),
            )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Range", value=f"1 – {maximum:,}", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def resetchat(self, ctx):
        """Clears this channel's rolling AI chat history."""
        await utils.brain_clear_history(ctx.channel.id)
        await ctx.send("Chat history cleared for this channel.")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
