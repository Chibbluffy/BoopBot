import discord, json, random
from datetime import timedelta, timezone, datetime
from discord.ext import commands
import google.generativeai as genai
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
        content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
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
                response = self.bot._chat.send_message(payload)
                reply    = response.text
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

    @commands.command()
    async def resetchat(self, ctx):
        """Cycles to the next AI model and resets the chat session."""
        self.bot._model_idx = (self.bot._model_idx + 1) % len(self.bot._models)
        self.bot._chat      = genai.GenerativeModel(self.bot._models[self.bot._model_idx]).start_chat(history=[])
        self.bot._chat.send_message(self.bot._context)
        await ctx.send(f"Chat reset. Model: **{self.bot._models[self.bot._model_idx]}**")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
