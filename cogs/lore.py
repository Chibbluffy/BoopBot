import discord, traceback
from discord.ext import commands
import utils


class LoreListView(discord.ui.View):
    def __init__(self, guild_lore, user_lore, author_id, per_page=10, start_page=0):
        super().__init__(timeout=120)
        self.guild_lore   = guild_lore
        self.user_lore    = user_lore
        self.author_id    = author_id
        self.per_page     = per_page
        self.rows         = [("guild", r) for r in guild_lore] + [("personal", r) for r in user_lore]
        self.total_pages  = max(1, (len(self.rows) + per_page - 1) // per_page)
        self.current_page = min(max(0, start_page), self.total_pages - 1)
        self.message      = None
        self._sync_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Run `!lore list` yourself to page through this.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def create_embed(self):
        start = self.current_page * self.per_page
        lines = [
            f"`{r['id'][:8]}` [{scope}] {r['text']}"
            for scope, r in self.rows[start:start + self.per_page]
        ]
        embed = discord.Embed(
            title="Lore",
            description='\n'.join(lines) or "Nothing here yet.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} · "
                               f"{len(self.guild_lore)} guild · {len(self.user_lore)} personal")
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

    async def on_timeout(self):
        self.prev_button.disabled = True
        self.next_button.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class LoreCog(commands.Cog, name="Lore"):

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="lore", invoke_without_command=True)
    async def lore(self, ctx):
        await ctx.send_help(ctx.command)

    @staticmethod
    def _log_brain_error(command_name: str, e: Exception):
        print(f"[lore] {command_name} failed: {type(e).__name__}: {e}")
        traceback.print_exc()

    @lore.command(name="add")
    async def lore_add(self, ctx, *, text: str):
        """Adds shared guild lore. Usage: !lore add <text>"""
        try:
            resp = await utils.brain_lore_add(ctx.guild.id, text, ctx.author.id, ctx.author.display_name)
        except Exception as e:
            self._log_brain_error("lore add", e)
            await ctx.send(f"Sorry, something went wrong.\n{type(e).__name__}: {e}")
            return
        short_id = (resp.get("id") or "")[:8]
        await ctx.send(f"Added to guild lore. (`{short_id}`)")

    @lore.command(name="addme")
    async def lore_addme(self, ctx, *, text: str):
        """Adds a personal fact about you. Usage: !lore addme <text>"""
        try:
            resp = await utils.brain_lore_addme(ctx.author.id, text)
        except Exception as e:
            self._log_brain_error("lore addme", e)
            await ctx.send(f"Sorry, something went wrong.\n{type(e).__name__}: {e}")
            return
        short_id = (resp.get("id") or "")[:8]
        await ctx.send(f"Added to your personal facts. (`{short_id}`)")

    @lore.command(name="list")
    async def lore_list(self, ctx, page: int = 1):
        """Lists guild + your personal lore, paginated. Usage: !lore list [page]"""
        try:
            data = await utils.brain_lore_list(ctx.guild.id, ctx.author.id)
        except Exception as e:
            self._log_brain_error("lore list", e)
            await ctx.send(f"Sorry, something went wrong.\n{type(e).__name__}: {e}")
            return
        view = LoreListView(data["guild_lore"], data["user_lore"], ctx.author.id, start_page=page - 1)
        view.message = await ctx.send(embed=view.create_embed(), view=view)

    @lore.command(name="forget")
    async def lore_forget(self, ctx, short_id: str):
        """Deletes a lore entry by its short id shown in !lore list. Usage: !lore forget <short_id>"""
        try:
            resp = await utils.brain_lore_forget(ctx.guild.id, ctx.author.id, short_id)
        except Exception as e:
            self._log_brain_error("lore forget", e)
            await ctx.send(f"Sorry, something went wrong.\n{type(e).__name__}: {e}")
            return
        if resp.get("deleted"):
            await ctx.send(f"Forgot: \"{resp['text']}\"")
        elif resp.get("ambiguous"):
            await ctx.send(f"`{short_id}` matches more than one entry — use `!lore list` and a longer prefix.")
        else:
            await ctx.send(f"No lore entry found matching `{short_id}`.")


async def setup(bot):
    await bot.add_cog(LoreCog(bot))
