import discord
from discord.ext import commands


class ModerationCog(commands.Cog, name="Moderation"):

    @commands.command(name="prune", aliases=["clr", "clear"])
    @commands.has_permissions(manage_messages=True)
    async def prune(self, ctx, *args):
        """Prune messages. Usage: !prune [user] [count]

        !prune           — delete this command + the message before it
        !prune 50        — delete last 50 messages
        !prune @user     — delete user's messages in last 100
        !prune @user 50  — delete last 50 messages from user"""
        member = ctx.message.mentions[0] if ctx.message.mentions else None
        count  = next((min(int(a), 1000) for a in args if a.isdigit()), None)

        # Base !prune: delete command + one message before it
        if member is None and count is None:
            msgs = [ctx.message]
            async for msg in ctx.channel.history(limit=1, before=ctx.message):
                msgs.append(msg)
            await ctx.channel.delete_messages(msgs)
            return

        # All other variants: delete command message, then purge
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        limit = count if count else 100

        def check(msg: discord.Message) -> bool:
            if member:
                return msg.author.id == member.id
            return True

        deleted = await ctx.channel.purge(limit=limit, check=check, bulk=True)
        await ctx.send(f"🗑️ Deleted **{len(deleted)}** message(s).", delete_after=5)

    @prune.error
    async def prune_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the **Manage Messages** permission to use this.", delete_after=8)
        elif isinstance(error, discord.Forbidden):
            await ctx.send("❌ I don't have permission to delete messages here.", delete_after=8)
        elif isinstance(error, discord.HTTPException):
            await ctx.send(f"❌ Failed to delete messages: {error}", delete_after=8)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
