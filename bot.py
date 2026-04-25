import discord, asyncio, os, asyncpg, traceback
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
import utils

TOKEN               = os.getenv("BOT_TOKEN")
DATABASE_URL        = os.getenv("DATABASE_URL")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY")
CHATBOT_CONTEXT_FILE = os.getenv("CHATBOT_CONTEXT_FILE", "chatbot_context.txt")

_COGS = [
    "cogs.events",
    "cogs.gear",
    "cogs.quotes",
    "cogs.fun",
    "cogs.economy",
    "cogs.fishing",
    "cogs.casino",
    "cogs.moderation",
]

# ── Custom help command ────────────────────────────────────────────────────────

_FIELD_LIMIT = 1000
_EMBED_LIMIT = 5800


class BoopHelpCommand(commands.HelpCommand):

    def _label(self, cmd):
        if cmd.aliases:
            return f'{cmd.name} [{", ".join(cmd.aliases)}]'
        return cmd.name

    def _brief(self, cmd):
        doc = cmd.short_doc or ''
        if 'Usage:' in doc:
            doc = doc[:doc.index('Usage:')].strip('. ')
        return doc

    def _cmd_entries(self, cmds):
        return [f'**{cmd.name}** {f"[{chr(44).join(cmd.aliases)}] " if cmd.aliases else ""}— {self._brief(cmd)}'
                for cmd in cmds]

    def _split_entries(self, entries):
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
        fields.append(('\u200b', '*Use `!help <command>` for full usage details.*'))
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


# ── Bot instance ───────────────────────────────────────────────────────────────

intents                 = discord.Intents.default()
intents.guilds          = True
intents.message_content = True
intents.members         = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    activity=discord.Game(name="!help"),
    help_command=BoopHelpCommand()
)


# ── Bot-level events ───────────────────────────────────────────────────────────

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


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    async with bot:
        utils.pool = await asyncpg.create_pool(DATABASE_URL)
        print("Database pool created.")

        # Chatbot state stored on bot instance so cogs can access it
        genai.configure(api_key=GOOGLE_API_KEY)
        bot._models    = ['gemini-2.5-flash-lite', 'gemini-2.5-flash']
        bot._model_idx = 0
        with open(CHATBOT_CONTEXT_FILE, 'r') as f:
            bot._context = f.read()
        bot._chat = None  # initialized lazily on first mention

        for ext in _COGS:
            await bot.load_extension(ext)
            print(f"Loaded {ext}")

        await bot.start(TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
