import discord, io, random, yaml
from discord.ext import commands
import utils


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


class QuotesCog(commands.Cog, name="Quotes"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quotelist", aliases=["ql", "qli"])
    async def quotelist(self, ctx, *, keyword: str = None):
        """Lists quotes with pagination. Usage: !quotelist [keyword]"""
        if keyword:
            rows  = await utils.pool.fetch(
                "SELECT nadeko_id, keyword, author_name FROM quotes WHERE keyword ILIKE $1 ORDER BY created_at ASC",
                keyword.strip()
            )
            title = f"Quotes – {keyword.upper()}"
        else:
            rows  = await utils.pool.fetch(
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
        rows = await utils.pool.fetch(
            "SELECT nadeko_id, text FROM quotes WHERE keyword ILIKE $1", keyword.strip()
        )
        if not rows:
            await ctx.send(f"No quotes found for **{keyword}**.")
            return
        quote = random.choice(rows)
        await ctx.reply(f"`{quote['nadeko_id']}` 📣 {quote['text']}")

    @commands.command(name="quoteget", aliases=["qg"])
    async def quoteget(self, ctx, quote_id: str):
        """Prints a quote by ID. Usage: !quoteget <id>"""
        row = await utils.pool.fetchrow(
            "SELECT nadeko_id, text FROM quotes WHERE nadeko_id = $1",
            quote_id.lower()
        )
        if not row:
            await ctx.send(f"Quote `{quote_id}` not found.")
            return
        await ctx.reply(f"`{row['nadeko_id']}` 📣 {row['text']}")

    @commands.command(name="quoteshow", aliases=["qshow"])
    async def quoteshow(self, ctx, quote_id: str):
        """Shows full details of a quote by ID. Usage: !quoteshow <id>"""
        row = await utils.pool.fetchrow(
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
        new_id  = await utils.generate_quote_id()
        await utils.pool.execute(
            "INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text) VALUES ($1, $2, $3, $4, $5)",
            keyword, new_id, ctx.author.name, str(ctx.author.id), text
        )
        await ctx.send(f"Quote added! ID: `{new_id}` – **{keyword}**")

    @commands.command(name="quotedelete", aliases=["qd", "qdel"])
    async def quotedelete(self, ctx, quote_id: str):
        """Deletes a quote by ID (creator or admin only). Usage: !quotedelete <id>"""
        row = await utils.pool.fetchrow(
            "SELECT keyword, author_discord_id FROM quotes WHERE nadeko_id = $1", quote_id.lower()
        )
        if not row:
            await ctx.send(f"Quote `{quote_id}` not found.")
            return
        if row['author_discord_id'] != str(ctx.author.id) and not await utils.is_admin(str(ctx.author.id)):
            await ctx.send("You can only delete your own quotes (or be an admin).")
            return
        await utils.pool.execute("DELETE FROM quotes WHERE nadeko_id = $1", quote_id.lower())
        await ctx.send(f"Quote `{quote_id}` ({row['keyword']}) deleted.")

    @commands.command(name="quotesearch", aliases=["qsearch", "qfind"])
    async def quotesearch(self, ctx, keyword: str, *, search_term: str):
        """Search for quotes containing a term. Usage: !quotesearch <keyword> <term>"""
        rows = await utils.pool.fetch(
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
        if not await utils.is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        count = await utils.pool.fetchval("SELECT COUNT(*) FROM quotes WHERE author_discord_id = $1", str(member.id))
        if not count:
            await ctx.send(f"No quotes found by **{member.name}**.")
            return
        view = ConfirmView(ctx.author.id)
        msg  = await ctx.send(f"⚠️ Delete **{count}** quote(s) by **{member.name}**?", view=view)
        await view.wait()
        if view.confirmed:
            await utils.pool.execute("DELETE FROM quotes WHERE author_discord_id = $1", str(member.id))
            await msg.edit(content=f"Deleted **{count}** quote(s) by **{member.name}**.", view=None)
        else:
            await msg.edit(content="Cancelled.", view=None)

    @commands.command(name="quotesdeleteall", aliases=["qdall"])
    async def quotesdeleteall(self, ctx, *, keyword: str = None):
        """(Admin) Deletes all quotes, or all for a keyword. Usage: !quotesdeleteall [keyword]"""
        if not await utils.is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        if keyword:
            count   = await utils.pool.fetchval("SELECT COUNT(*) FROM quotes WHERE keyword ILIKE $1", keyword.strip())
            warning = f"⚠️ Delete **{count}** quote(s) for **{keyword.upper()}**?"
        else:
            count   = await utils.pool.fetchval("SELECT COUNT(*) FROM quotes")
            warning = f"⚠️ Delete **ALL {count}** quotes from the archive?"
        if not count:
            await ctx.send("No quotes to delete.")
            return
        view = ConfirmView(ctx.author.id)
        msg  = await ctx.send(warning, view=view)
        await view.wait()
        if view.confirmed:
            if keyword:
                await utils.pool.execute("DELETE FROM quotes WHERE keyword ILIKE $1", keyword.strip())
            else:
                await utils.pool.execute("DELETE FROM quotes")
            await msg.edit(content=f"Deleted **{count}** quote(s).", view=None)
        else:
            await msg.edit(content="Cancelled.", view=None)

    @commands.command(name="quotesexport", aliases=["qexport", "qex"])
    async def quotesexport(self, ctx):
        """(Admin) Exports all quotes as a Nadeko-compatible YAML file."""
        if not await utils.is_admin(str(ctx.author.id)):
            await ctx.send("This command is admin only.")
            return
        rows = await utils.pool.fetch(
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
        if not await utils.is_admin(str(ctx.author.id)):
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
                nadeko_id   = str(q.get('id', '')).strip() or await utils.generate_quote_id()
                author_name = str(q.get('an', '')).strip() or None
                author_id   = str(q.get('aid', '')).strip() or None
                text        = str(q.get('txt', '')).strip()
                if not text:
                    skipped += 1
                    continue
                result = await utils.pool.execute(
                    "INSERT INTO quotes (keyword, nadeko_id, author_name, author_discord_id, text) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (nadeko_id) DO NOTHING",
                    str(keyword).upper(), nadeko_id, author_name, author_id, text
                )
                if result == "INSERT 0 1":
                    inserted += 1
                else:
                    skipped += 1
        await ctx.send(f"Import complete. Inserted: **{inserted}** · Skipped/duplicate: **{skipped}**")


async def setup(bot):
    await bot.add_cog(QuotesCog(bot))
