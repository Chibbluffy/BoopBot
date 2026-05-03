import discord, asyncio, random
from discord.ext import commands
import utils

SHOP_ITEMS = {
    # Rods (permanent, tier 1-7)
    "rod_beginner":     {"name": "Beginner's Rod",    "category": "rod",   "price":      500, "tier": 1, "desc": "A simple but functional rod."},
    "rod_apprentice":   {"name": "Apprentice Rod",    "category": "rod",   "price":    2_000, "tier": 2, "desc": "Better grip, better catches."},
    "rod_skilled":      {"name": "Skilled Rod",       "category": "rod",   "price":    8_000, "tier": 3, "desc": "Crafted with care."},
    "rod_professional": {"name": "Professional Rod",  "category": "rod",   "price":   25_000, "tier": 4, "desc": "Built for serious fishing."},
    "rod_artisan":      {"name": "Artisan Rod",       "category": "rod",   "price":   200_000, "tier": 5, "desc": "Masterfully balanced."},
    "rod_master":       {"name": "Master Rod",        "category": "rod",   "price":  1_000_000, "tier": 6, "desc": "Few fishers have held one."},
    "rod_guru":         {"name": "Guru Rod",          "category": "rod",   "price":  5_000_000, "tier": 7, "desc": "The pinnacle of fishing craft."},
    # Floats (permanent, tier 1-7)
    "float_beginner":     {"name": "Beginner's Float",   "category": "float", "price":      250, "tier": 1, "desc": "Standard sensitivity."},
    "float_apprentice":   {"name": "Apprentice Float",   "category": "float", "price":    1_000, "tier": 2, "desc": "Tuned for light bites."},
    "float_skilled":      {"name": "Skilled Float",      "category": "float", "price":    4_000, "tier": 3, "desc": "Detects what others miss."},
    "float_professional": {"name": "Professional Float", "category": "float", "price":   12_500, "tier": 4, "desc": "Precision at any depth."},
    "float_artisan":      {"name": "Artisan Float",      "category": "float", "price":  100_000, "tier": 5, "desc": "Reads the water like a book."},
    "float_master":       {"name": "Master Float",       "category": "float", "price":  500_000, "tier": 6, "desc": "Almost sentient."},
    "float_guru":         {"name": "Guru Float",         "category": "float", "price":2_500_000, "tier": 7, "desc": "Legends whisper its name."},
    # Bait (consumable, 1 per cast, tier 0-6)
    "bait_beginner":      {"name": "Beginner Bait",      "category": "bait",  "price":      10, "tier": 1, "desc": "A step up from worms."},
    "bait_apprentice":    {"name": "Apprentice Bait",    "category": "bait",  "price":      50, "tier": 2, "desc": "Fish find it hard to resist."},
    "bait_skilled":       {"name": "Skilled Bait",       "category": "bait",  "price":     250, "tier": 3, "desc": "Specially prepared blend."},
    "bait_professional":  {"name": "Professional Bait",  "category": "bait",  "price":   1_000, "tier": 4, "desc": "The pros won't share the recipe."},
    "bait_artisan":       {"name": "Artisan Bait",       "category": "bait",  "price":   4_000, "tier": 5, "desc": "Rare fish can't ignore this."},
    "bait_master":        {"name": "Master Bait",        "category": "bait",  "price":  15_000, "tier": 6, "desc": "You don't want to know how this is made. Trust me."},
}

# (tier, name, value, min_kg, max_kg)
FISH_LOOT = [
    # Junk (tier 0) — no records, no size
    (0, "Broken Bottle",           1,  0.0,   0.0),
    (0, "Broken Bottle Fragment",  1,  0.0,   0.0),
    (0, "Broken Fishing Rod",      1,  0.0,   0.0),
    (0, "Fish Bones",              1,  0.0,   0.0),
    (0, "Seaweed",                 1,  0.0,   0.0),
    (0, "Snapped Rope",            1,  0.0,   0.0),
    (0, "Tattered Boots",          1,  0.0,   0.0),
    (0, "Tin Can",                 1,  0.0,   0.0),
    (0, "Torn Net",                1,  0.0,   0.0),
    # Common (tier 1) — 10–23 boops
    (1, "Anchovy",           10,   0.01,  0.05),
    (1, "Dace",              12,   0.05,  0.5),
    (1, "Beltfish",          15,   0.2,   2.5),
    (1, "Clownfish",         16,   0.01,  0.12),
    (1, "Mudskipper",        16,   0.05,  0.25),
    (1, "Round Herring",     16,   0.02,  0.15),
    (1, "Starfish",          17,   0.05,  0.35),
    (1, "Flatfish",          18,   0.1,   1.5),
    (1, "Sandeel",           18,   0.003, 0.015),
    (1, "Whiting",           19,   0.2,   0.8),
    (1, "Rockfish",          20,   0.3,   2.0),
    (1, "Blue Tang",         23,   0.1,   0.3),
    # Uncommon (tier 2) — 48–116 boops
    (2, "Surfperch",         48,   0.1,   1.5),
    (2, "Flounder",          60,   0.3,   4.0),
    (2, "Croaker",           65,   0.2,   3.0),
    (2, "Redbreasted Wrasse",71,   0.05,  0.4),
    (2, "Grouper",           75,   1.0,  15.0),
    (2, "Flower Icefish",    79,   0.03,  0.2),
    (1, "Grunt",             80,   0.1,   0.8),
    (2, "Pomfret",           80,   0.3,   2.5),
    (2, "Angler",            90,   0.1,   1.5),
    (2, "Bahaba",           116,   2.0,  30.0),
    # Rare (tier 3) — 100–450 boops
    (3, "Charr",                  100,   0.5,   8.0),
    (3, "Giant Talking Catfish",  128,   3.0,  20.0),
    (3, "Bigfin Reef Squid",      200,   0.05,  0.5),
    (3, "Skate",                  220,   1.0,  25.0),
    (3, "Tilefish",               280,   1.0,  10.0),
    (3, "Tuna",                   350,  20.0, 300.0),
    (3, "Greater Amberjack",      400,   5.0,  70.0),
    (3, "Southern Rough Shrimp",  400,   0.005, 0.02),
    (3, "Goliath Grouper",        450,  50.0, 360.0),
    # Ultra Rare (tier 4) — 800–8,000 boops
    (4, "Yellow Corvina",        800,   0.5,    6.0),
    (4, "Electric Catfish",    1_500,   0.5,   20.0),
    (4, "Whitefin Trevally",   1_500,   0.5,    8.0),
    (4, "Blue Bat Star",       1_600,   0.02,   0.2),
    (4, "Golden Sea Bass",     2_400,   1.0,   12.0),
    (4, "Black Halibut",       2_500,   1.0,   20.0),
    (4, "White Crucian Carp",  2_500,   0.1,    2.0),
    (4, "Albino Coelacanth",   2_800,  15.0,   80.0),
    (4, "Giant Bitterling",    3_500,   0.01,   0.05),
    (4, "Hammer Mackerel",     3_500,   1.0,    5.0),
    (4, "Black Eye Crab",      4_000,   0.2,    2.0),
    (4, "White Grouper",       4_000,   3.0,   25.0),
    (4, "Rainbow Sardine",     5_000,   0.02,   0.12),
    (4, "Spotted Spined Loach",5_000,   0.005,  0.03),
    (4, "Golden Albacore",     6_400,   8.0,   40.0),
    (4, "Red Garra",           7_000,   0.01,   0.05),
    (4, "Footballfish",        8_000,   1.0,    6.0),
    (4, "Giant Oarfish",       8_000,  30.0,  200.0),
    (4, "Silver Beltfish",     8_000,   0.3,    3.0),
    # Legendary (tier 5) — 12,000+ boops, requires GS 10+
    (5, "Pirarucu",           12_000,  30.0,  200.0),
    (5, "Gar",                15_000,   2.0,   80.0),
    (5, "Nautilus",           18_000,   0.05,   0.4),
    (5, "Polka-dot Stingray", 18_400,   5.0,  120.0),
    (5, "Sea Bunny",          20_000,   0.001,  0.005),
    (5, "Blue-Ringed Octopus",25_000,   0.01,   0.1),
    (5, "Sea Pig",            28_000,   0.02,   0.2),
    (5, "Mantis Shrimp",      29_000,   0.03,   0.5),
    (5, "Frilled Shark",      32_000,   8.0,   20.0),
    (5, "Green Sea Turtle",   35_000,  80.0,  200.0),
    (5, "Humphead Parrotfish",35_000,  15.0,   75.0),
    (5, "Red Handfish",       38_000,   0.01,   0.03),
    (5, "Salp",               38_000,   0.001,  0.01),
    (5, "Moon Jelly",         40_000,   0.05,   0.5),
    (5, "Ranchu",             40_000,   0.1,    0.5),
    (5, "Pelican Eel",        42_000,   0.3,    2.5),
    (5, "Dorado",             58_000,   5.0,   40.0),
    (5, "Cloaking Shark",     72_000,   5.0,   80.0),
    (5, "Tripod Fish",        72_000,   0.2,    2.0),
    (5, "Glass Octopus",      73_000,   0.05,   0.3),
    (5, "Blue Angel",         75_000,   0.1,    2.0),
    (5, "Koi",                75_000,   2.0,   20.0),
    (5, "Vaquita",            78_000,  25.0,   55.0),
    (5, "Ghostfish",          80_000,   0.5,    8.0),
    (5, "Blue Lobster",       83_000,   0.3,    4.0),
    (5, "Blobfish",           85_000,   1.0,    5.0),
    (5, "Deep Sea Snailfish", 85_000,   0.05,   0.3),
    (5, "Barreleye",          86_000,   0.05,   0.4),
    (5, "Duke Squid",         88_000,   5.0,  150.0),
    (5, "Manta Ray",          88_000,  80.0, 1500.0),
    (5, "Betta",              90_000,   0.005,  0.05),
    (5, "Blanket Octopus",    92_000,   0.5,    8.0),
    (5, "Migaloo",            92_000, 200.0, 3000.0),
    (5, "Rainbowfish",        95_000,   0.05,   0.5),
    (5, "Flapjack Octopus",   99_000,   0.3,    5.0),
    (5, "Pink Dolphin",      100_000,  50.0,  160.0),
]

# fish_name → tier lookup for display coloring
_FISH_TIER_MAP: dict[str, int] = {f[1]: f[0] for f in FISH_LOOT}

# Non-junk fish in legendary-first order for leaderboard pages
_FISH_ORDER = [f[1] for f in FISH_LOOT[::-1] if f[0] > 0]

_FISH_PER_PAGE = 3
_TOP_N         = 5

_FISH_TIER_EMOJI = ["🥾", "🐟", "🐠", "🐡", "🦈", "🦀"]

_ANSI_RESET    = "\u001b[0m"
_ANSI_BAL      = "\u001b[1;37m"   # bold white for balance suffix
_FISH_TIER_ANSI = [
    "\u001b[2;37m",  # tier 0 junk:       dim white
    "\u001b[0;32m",  # tier 1 common:     green
    "\u001b[0;34m",  # tier 2 uncommon:   blue
    "\u001b[0;35m",  # tier 3 rare:       purple
    "\u001b[1;31m",  # tier 4 ultra rare: bold red
    "\u001b[1;33m",  # tier 5 legendary:  bold yellow
]


def _gear_score(rod_id, float_id, bait_id):
    return (
        SHOP_ITEMS.get(rod_id,   {}).get("tier", 0) +
        SHOP_ITEMS.get(float_id, {}).get("tier", 0) +
        SHOP_ITEMS.get(bait_id,  {}).get("tier", 0)
    )

# Drop weight table — (junk, common, uncommon, rare, ultra rare, legendary)
# Values are relative weights; they don't need to sum to 100 but are kept at 100
# for readability so you can read them directly as percentages. Max GS = 20.
_DROP_WEIGHTS = {
#   GS: ( jnk, com, unc, rar, ult, leg)
     0:  ( 50,  40,   7,   2,   1,   0),
     1:  ( 45,  35,  15,   3,   2,   0),
     2:  ( 40,  35,  17,   5,   3,   0),
     3:  ( 35,  30,  19,  12,   4,   0),
     4:  ( 30,  30,  20,  15,   5,   0),
     5:  ( 30,  25,  23,  15,   7,   0),
     6:  ( 30,  23,  23,  15,   9,   0),
     7:  ( 25,  21,  25,  19,  10,   0),
     8:  ( 20,  20,  30,  20,  10,   0),
     9:  ( 15,  20,  30,  25,  10,   0),
    10:  ( 10,  20,  29,  30,  10,   1),
    11:  (  9,  20,  29,  31,  10,   1),
    12:  (  8,  15,  28,  32,  15,   2),
    13:  (  7,  15,  27,  33,  15,   3),
    14:  (  6,  10,  26,  33,  21,   4),
    15:  (  5,  10,  25,  33,  22,   5),
    16:  (  4,  10,  24,  33,  23,   6),
    17:  (  3,  10,  23,  32,  25,   7),
    18:  (  2,  10,  22,  29,  29,   8),
    19:  (  1,  10,  21,  30,  29,   9),
    20:  (  1,  10,  20,  29,  30,  10),
}

def _roll_fish(gear_score):
    gs      = min(max(gear_score, 0), 20)
    weights = _DROP_WEIGHTS[gs]
    tier    = random.choices([0, 1, 2, 3, 4, 5], weights=weights, k=1)[0]
    pool    = [f for f in FISH_LOOT if f[0] == tier]
    fish    = random.choice(pool)
    size_kg = random.uniform(fish[3], fish[4])
    return fish[1], fish[2], tier, size_kg

def _fmt_size(size_kg: float) -> str:
    """Display size in grams if under 1 kg, otherwise kg, both at 2 decimal places."""
    if size_kg < 1.0:
        return f"{size_kg * 1000:.2f} g"
    return f"{size_kg:.2f} kg"

def _fmt_range(min_kg: float, max_kg: float) -> str:
    """Display a size range, using grams if the whole range is under 1 kg."""
    if max_kg < 1.0:
        return f"{min_kg * 1000:.2f}–{max_kg * 1000:.2f} g"
    return f"{min_kg}–{max_kg} kg"

_MYSTICAL_MAX       = 5
_MYSTICAL_CHANCE    = 0.001   # 0.1% per cast at GS 20
_ANSI_MYSTICAL      = "\u001b[1;36m"  # bold cyan
_TIER_NAMES         = ["Junk", "Common", "Uncommon", "Rare", "Ultra Rare", "Legendary"]

def _roll_forced_tier(tier: int):
    """Roll a random fish from a specific tier (used by Fish Whisperer mode)."""
    pool    = [f for f in FISH_LOOT if f[0] == tier]
    fish    = random.choice(pool)
    size_kg = random.uniform(fish[3], fish[4])
    return fish[1], fish[2], tier, size_kg

def _find_item(query: str):
    q = query.lower()
    for item_id, item in SHOP_ITEMS.items():
        if q == item_id or q == item["name"].lower():
            return item_id, item
    for item_id, item in SHOP_ITEMS.items():
        if q in item["name"].lower() or q in item_id:
            return item_id, item
    return None, None


def _build_leaderboard_pages(rows) -> list[str]:
    from collections import defaultdict
    by_fish: dict[str, list] = defaultdict(list)
    for row in rows:
        by_fish[row["fish_name"]].append(row)

    ordered = [(name, by_fish[name]) for name in _FISH_ORDER if name in by_fish]
    if not ordered:
        return []

    total_pages = max(1, -(-len(ordered) // _FISH_PER_PAGE))  # ceiling div
    pages = []
    for p, i in enumerate(range(0, len(ordered), _FISH_PER_PAGE), 1):
        chunk = ordered[i:i + _FISH_PER_PAGE]
        lines = []
        for fish_name, entries in chunk:
            tier  = _FISH_TIER_MAP.get(fish_name, 1)
            color = _FISH_TIER_ANSI[tier]
            lines.append(f"{color}{_FISH_TIER_EMOJI[tier]} {fish_name}{_ANSI_RESET}")
            for j, entry in enumerate(entries, 1):
                lines.append(f"  {j}. {entry['name']:<16} {_fmt_size(entry['record_kg'])}")
            lines.append("")
        content = (
            f"🏆 **Best Fishers** — Page {p}/{total_pages}\n"
            f"```ansi\n{chr(10).join(lines).rstrip()}\n```"
        )
        pages.append(content)
    return pages


_TIER_COLORS = [0x808080, 0x2ecc71, 0x3498db, 0x9b59b6, 0xe74c3c, 0xffd700]

def _build_fish_guide_pages() -> list[discord.Embed]:
    tier_config = [
        (0, "Junk"),
        (1, "Common"),
        (2, "Uncommon"),
        (3, "Rare"),
        (4, "Ultra Rare"),
        (5, "Legendary"),
    ]
    pages = []
    for tier_num, tier_name in tier_config:
        fish_list = [f for f in FISH_LOOT if f[0] == tier_num]
        emoji     = _FISH_TIER_EMOJI[tier_num]
        lines     = []
        for _, name, value, min_kg, max_kg in fish_list:
            if tier_num == 0:
                lines.append(f"**{name}**")
            else:
                lines.append(f"**{name}** · {value:,} boops · {_fmt_range(min_kg, max_kg)}")
        embed = discord.Embed(
            title=f"{emoji} {tier_name} Fish",
            description="\n".join(lines),
            color=_TIER_COLORS[tier_num],
        )
        pages.append(embed)
    return pages


class FishGuideView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=60)
        self.pages     = pages
        self.page      = 0
        self.author_id = author_id
        self._update_footer()
        self._sync_buttons()

    def _update_footer(self):
        self.pages[self.page].set_footer(text=f"Page {self.page + 1} of {len(self.pages)}")

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page == len(self.pages) - 1

    async def _go(self, interaction: discord.Interaction, delta: int):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your guide!", ephemeral=True)
            return
        self.page += delta
        self._update_footer()
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, -1)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, +1)


class BestFishersView(discord.ui.View):
    def __init__(self, pages: list[str], author_id: int):
        super().__init__(timeout=120)
        self.pages     = pages
        self.page      = 0
        self.author_id = author_id
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page == len(self.pages) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your leaderboard!", ephemeral=True)
            return
        self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.pages[self.page], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your leaderboard!", ephemeral=True)
            return
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.pages[self.page], view=self)


class FishingView(discord.ui.View):
    def __init__(self, caster_id: int, timeout: float = 20,
                 label: str = "🎣 Reel In!", style: discord.ButtonStyle = discord.ButtonStyle.primary):
        super().__init__(timeout=timeout)
        self.caster_id      = caster_id
        self.clicked        = False
        self.reel_in.label  = label
        self.reel_in.style  = style

    @discord.ui.button(label="🎣 Reel In!", style=discord.ButtonStyle.primary)
    async def reel_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.caster_id:
            await interaction.response.send_message("That's not your line!", ephemeral=True)
            return
        self.clicked = True
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.clicked = False


class FishingCog(commands.Cog, name="Fishing"):

    def __init__(self, bot):
        self.bot = bot
        # (channel_id, user_id) → (message, lines list)
        self._catch_logs: dict[tuple[int, int], tuple[discord.Message, list[str]]] = {}

    async def _get_log(self, ctx) -> tuple[discord.Message | None, list[str]]:
        """Return existing catch log message if it's still the last message in the channel."""
        key      = (ctx.channel.id, ctx.author.id)
        existing = self._catch_logs.get(key)
        if not existing:
            return None, []
        log_msg, lines = existing
        async for last in ctx.channel.history(limit=1):
            if last.id == log_msg.id:
                return log_msg, lines
        return None, []

    async def _update_log(self, ctx, new_line: str, new_bal: int, tier: int, is_pb: bool = False):
        """Append a catch line to the log, creating or reusing as needed."""
        key            = (ctx.channel.id, ctx.author.id)
        log_msg, lines = await self._get_log(ctx)

        pb_suffix = f"  \u001b[1;37m★ Personal Best!{_ANSI_RESET}" if is_pb else ""
        colored   = f"{_FISH_TIER_ANSI[tier]}{new_line}{_ANSI_RESET}{pb_suffix}"
        lines.append(colored)

        body = "\n".join(lines)
        if len(body) > 1800:
            lines   = [colored]
            log_msg = None

        display = "\n".join(
            lines[:-1] + [lines[-1] + f"  {_ANSI_BAL}·  Boop Balance: {new_bal:,}{_ANSI_RESET}"]
        )
        content = f"🎣 **{ctx.author.display_name}'s Catch Log**\n```ansi\n{display}\n```"

        if log_msg:
            await log_msg.edit(content=content)
            self._catch_logs[key] = (log_msg, lines)
        else:
            new_msg = await ctx.send(content=content)
            self._catch_logs[key] = (new_msg, lines)

    @commands.command(name="fish")
    async def fish(self, ctx):
        """Cast your line and catch fish for boops!"""
        discord_id      = str(ctx.author.id)
        profile         = await utils.get_fishing_profile(discord_id)
        mystical_active = profile.get("mystical_active", 0)

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        # ── Fish Whisperer mode: instant forced-tier catch ─────────────────────
        if mystical_active > 0:
            fish_name, value, tier, size_kg = _roll_forced_tier(mystical_active)

            if profile["active_bait"]:
                await utils.use_bait(discord_id, profile["active_bait"])

            new_bal = await utils.add_boops(discord_id, value, ctx.author.name)
            is_pb   = False
            if tier > 0:
                is_pb, _ = await utils.update_fish_record(discord_id, fish_name, size_kg)

            size_part = f"  {_fmt_size(size_kg)}" if tier > 0 else ""
            line      = f"{_FISH_TIER_EMOJI[tier]} {fish_name}{size_part}  +{value:,}"
            await self._update_log(ctx, line, new_bal, tier, is_pb)
            return

        # ── Normal fishing flow ────────────────────────────────────────────────
        inv   = await utils.get_inventory(discord_id)
        score = _gear_score(profile["active_rod"], profile["active_float"], profile.get("active_bait"))

        def _iname(iid):
            if iid == "rod_starter": return "Starter Rod"
            return SHOP_ITEMS.get(iid, {}).get("name", iid) if iid else None

        rod_name   = _iname(profile["active_rod"])
        float_name = _iname(profile["active_float"])
        bait_id    = profile.get("active_bait")
        bait_name  = _iname(bait_id)
        bait_count = inv.get(bait_id, 0) if bait_id else None

        gear_line  = f"🎣 {rod_name}"
        if float_name:
            gear_line += f"  ·  🪝 {float_name}"
        if bait_name:
            bait_warn  = " ⚠️" if bait_count is not None and bait_count <= 5 else ""
            gear_line += f"  ·  🪱 {bait_name} ×{bait_count}{bait_warn}"
        else:
            gear_line += "  ·  🪱 No bait"

        embed    = discord.Embed(
            description=f"🎣 Casting your line...\n\n{gear_line}\n⚙️ Fishing GS: **{score}**",
            color=0x1e90ff
        )
        cast_msg = await ctx.send(embed=embed)

        await asyncio.sleep(random.uniform(2, 5))

        # Mystical fish check — GS 20 only, 0.1% chance
        if score >= 10 and random.random() < _MYSTICAL_CHANCE:
            try:
                await cast_msg.delete()
            except discord.NotFound:
                pass

            inv            = await utils.get_inventory(discord_id)
            mystical_count = inv.get("mystical_fish", 0)

            if mystical_count < _MYSTICAL_MAX:
                await utils.add_inventory(discord_id, "mystical_fish", 1)
                new_count = mystical_count + 1

                if profile["active_bait"]:
                    await utils.use_bait(discord_id, profile["active_bait"])

                if new_count == _MYSTICAL_MAX:
                    embed_m = discord.Embed(
                        title="✨ Fish Whisperer",
                        description="The ocean bows to you.\nAll Mystical Fish collected. Use `!fishfocus` to command the tides.",
                        color=0x00ffff
                    )
                else:
                    embed_m = discord.Embed(
                        title="✨ A Mystical Fish...",
                        description=f"Something otherworldly slipped onto your line.\n**Mystical Fish ×{new_count}**",
                        color=0x00ffff
                    )
                await ctx.send(embed=embed_m)
            return

        # Pre-roll so we know if it's legendary before showing the button
        fish_name, value, tier, size_kg = _roll_fish(score)

        is_legendary = (tier == 5)

        if is_legendary:
            # ── 3-round legendary battle ───────────────────────────────────────
            _ROUNDS = [
                ("💪 Hold On!",    discord.ButtonStyle.success, "🟡⬛⬛  **Round 1 / 3**\n\nIt's **fighting back hard** — hold on tight!"),
                ("🎣 Pull!",       discord.ButtonStyle.primary,  "✅🟡⬛  **Round 2 / 3**\n\nIt's slowing down — **pull with everything you've got!**"),
                ("🏆 Reel It In!", discord.ButtonStyle.danger,   "✅✅🟡  **Round 3 / 3**\n\n**NOW! REEL IT IN!**"),
            ]
            _FAIL_MSGS = [
                "💨 It **snapped the line** and escaped into the deep...",
                "😮 You **lost your grip!** It slipped away!",
                "💔 **So close...** It broke free at the very last second!",
            ]

            embed.color = 0xffd700
            fail_msg    = None

            for i, (btn_label, btn_style, fight_msg) in enumerate(_ROUNDS):
                embed.description = f"⚠️ **LEGENDARY FISH ON THE LINE!**\n\n{fight_msg}"
                view = FishingView(ctx.author.id, timeout=3, label=btn_label, style=btn_style)
                await cast_msg.edit(embed=embed, view=view)
                timed_out = await view.wait()

                if timed_out or not view.clicked:
                    fail_msg = _FAIL_MSGS[i]
                    break

            try:
                await cast_msg.delete()
            except discord.NotFound:
                pass

            if fail_msg:
                await self._update_log(ctx, f"🌊 {fail_msg}", await utils.get_boops(discord_id), 0)
                return

        else:
            # ── Normal single-click flow ───────────────────────────────────────
            embed.description = "🐟 Something's tugging on the line! Quick!"
            view = FishingView(ctx.author.id, timeout=20)
            await cast_msg.edit(embed=embed, view=view)
            timed_out = await view.wait()

            try:
                await cast_msg.delete()
            except discord.NotFound:
                pass

            if timed_out or not view.clicked:
                await self._update_log(ctx, "🌊 Got away...", await utils.get_boops(discord_id), 0)
                return

        if profile["active_bait"] and tier > 0:
            await utils.use_bait(discord_id, profile["active_bait"])

        new_bal = await utils.add_boops(discord_id, value, ctx.author.name)

        is_pb = False
        if tier > 0:
            is_pb, _ = await utils.update_fish_record(discord_id, fish_name, size_kg)

        size_part = f"  {_fmt_size(size_kg)}" if tier > 0 else ""
        line      = f"{_FISH_TIER_EMOJI[tier]} {fish_name}{size_part}  +{value:,}"
        await self._update_log(ctx, line, new_bal, tier, is_pb)

    @commands.command(name="shop")
    async def shop(self, ctx):
        """Browse the fishing shop."""
        discord_id = str(ctx.author.id)
        inv        = await utils.get_inventory(discord_id)
        boops      = await utils.get_boops(discord_id)
        embed      = discord.Embed(title="🏪 Fishing Shop", description=f"💰 **Your balance: {boops:,} boops**", color=discord.Color.blurple())
        for category, label in [("rod", "🎣 Rods"), ("float", "🪝 Floats"), ("bait", "🪱 Bait")]:
            lines = []
            for item_id, item in SHOP_ITEMS.items():
                if item["category"] != category:
                    continue
                if category == "bait":
                    qty   = inv.get(item_id, 0)
                    stock = f"  · **×{qty}** owned" if qty > 0 else ""
                    lines.append(f"**{item['name']}** — {item['price']:,} ea{stock}\n  _{item['desc']}_")
                else:
                    owned = inv.get(item_id, 0) > 0
                    tag   = "  ✅ owned" if owned else ""
                    lines.append(f"**{item['name']}** — {item['price']:,} boops{tag}\n  _{item['desc']}_")
            embed.add_field(name=label, value="\n".join(lines), inline=False)
        embed.set_footer(text="!buy <item> [qty]  ·  !equip <item>  ·  !inv to see your gear")
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy(self, ctx, *, args: str):
        """Buy a shop item. Usage: !buy <item> [quantity]"""
        parts = args.rsplit(None, 1)
        if len(parts) == 2 and parts[1].isdigit():
            qty, query = int(parts[1]), parts[0]
        else:
            qty, query = 1, args

        item_id, item = _find_item(query)
        if not item:
            await ctx.send(f"Item not found: `{query}`. Use `!shop` to browse.")
            return

        if item["category"] in ("rod", "float"):
            qty = 1
            inv = await utils.get_inventory(str(ctx.author.id))
            if inv.get(item_id, 0) > 0:
                await ctx.send(f"You already own **{item['name']}**.")
                return
        elif item["category"] == "bait" and qty < 1:
            qty = 1

        total = item["price"] * qty
        boops = await utils.get_boops(str(ctx.author.id))
        if boops < total:
            await ctx.send(f"Not enough boops. Need **{total:,}**, you have **{boops:,}**.")
            return

        await utils.add_boops(str(ctx.author.id), -total, ctx.author.name)
        await utils.add_inventory(str(ctx.author.id), item_id, qty)
        label = f"**{qty}× {item['name']}**" if qty > 1 else f"**{item['name']}**"
        await ctx.send(f"✅ Bought {label} for **{total:,}** boops.")

    @commands.command(name="equip")
    async def equip(self, ctx, *, query: str):
        """Equip a rod, float, or set active bait. Usage: !equip <item>"""
        item_id, item = _find_item(query)
        if not item:
            await ctx.send(f"Item not found: `{query}`.")
            return
        inv = await utils.get_inventory(str(ctx.author.id))
        if not inv.get(item_id) and item_id != "rod_starter":
            await ctx.send(f"You don't own **{item['name']}**. Buy it with `!buy`.")
            return
        col = {"rod": "active_rod", "float": "active_float", "bait": "active_bait"}[item["category"]]
        await utils.pool.execute(
            f"""INSERT INTO fishing_profile (discord_id, {col}) VALUES ($1, $2)
                ON CONFLICT (discord_id) DO UPDATE SET {col} = $2""",
            str(ctx.author.id), item_id
        )
        await ctx.send(f"✅ Equipped **{item['name']}**.")

    @commands.command(name="unequip")
    async def unequip(self, ctx, *, query: str):
        """Unequip your float or active bait. Usage: !unequip <float|bait>"""
        item_id, item = _find_item(query)
        if not item or item["category"] == "rod":
            await ctx.send("You can only unequip floats or bait. (You always need a rod.)")
            return
        col = {"float": "active_float", "bait": "active_bait"}[item["category"]]
        await utils.pool.execute(
            f"UPDATE fishing_profile SET {col} = NULL WHERE discord_id = $1", str(ctx.author.id)
        )
        await ctx.send(f"✅ Unequipped **{item['name']}**.")

    @commands.command(name="fishfocus")
    async def fishfocus(self, ctx, level: int):
        """Set Fish Whisperer focus tier (0=off, 1-5). Usage: !fishfocus <0-5>"""
        discord_id     = str(ctx.author.id)
        inv            = await utils.get_inventory(discord_id)
        mystical_count = inv.get("mystical_fish", 0)

        if not 0 <= level <= 5:
            await ctx.send("Focus level must be 0 (off) through 5.")
            return
        if level > mystical_count:
            await ctx.send(f"You only have **{mystical_count}** Mystical Fish. You can't set focus to {level}.")
            return

        await utils.pool.execute(
            "UPDATE fishing_profile SET mystical_active = $1 WHERE discord_id = $2",
            level, discord_id
        )

        if level == 0:
            await ctx.send("✅ Fish Whisperer disabled. Back to normal fishing.")
        else:
            await ctx.send(f"✅ Fish Whisperer focus set to **{_TIER_NAMES[level]}**. Instant catch active.")

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx):
        """View your fishing gear and bait."""
        discord_id = str(ctx.author.id)
        profile    = await utils.get_fishing_profile(discord_id)
        inv        = await utils.get_inventory(discord_id)
        boops      = await utils.get_boops(discord_id)
        records    = await utils.get_fish_records(discord_id)

        def item_name(iid):
            if iid == "rod_starter": return "Starter Rod"
            return SHOP_ITEMS.get(iid, {}).get("name", iid) if iid else "None"

        gs           = _gear_score(profile["active_rod"], profile["active_float"], profile.get("active_bait"))
        total_species = len([f for f in FISH_LOOT if f[0] > 0])
        caught_species = len(records)
        lines = [
            f"💰 **Boops:** {boops:,}",
            f"🎣 **Rod:**   {item_name(profile['active_rod'])}",
            f"🪝 **Float:** {item_name(profile['active_float']) if profile['active_float'] else 'None'}",
            f"🪱 **Bait:**  {item_name(profile['active_bait'])  if profile['active_bait']  else 'None'}",
            f"⚙️ **Fishing GS:** {gs}",
            f"📖 **Species caught:** {caught_species} / {total_species}",
            "", "**Owned:**",
        ]
        equipped  = {profile["active_rod"], profile["active_float"], profile["active_bait"]}
        has_items = False
        for item_id, qty in inv.items():
            if qty <= 0 or item_id == "mystical_fish": continue
            name = SHOP_ITEMS.get(item_id, {}).get("name", item_id)
            tag  = " *(equipped)*" if item_id in equipped else ""
            lines.append(f"  {name} ×{qty}{tag}")
            has_items = True
        if not has_items:
            lines.append("  Nothing yet. Visit `!shop`!")

        mystical_count = inv.get("mystical_fish", 0)
        if mystical_count > 0:
            focus       = profile.get("mystical_active", 0)
            orbs        = ["🔴", "🟠", "🟡", "🟢", "🔵"]
            bar         = "".join(orbs[:mystical_count]) + "⬛" * (_MYSTICAL_MAX - mystical_count)
            focus_str   = f"🎯 Focus: **{_TIER_NAMES[focus]}**" if focus > 0 else "🎯 Focus: **Off**"
            if mystical_count >= _MYSTICAL_MAX:
                header  = "✨ **F I S H  W H I S P E R E R** ✨"
            else:
                header  = f"✨ **Mystical Fish**  {mystical_count} / {_MYSTICAL_MAX}"
            lines.append("")
            lines.append("─────────────────────")
            lines.append(header)
            lines.append(bar)
            lines.append(focus_str)
            lines.append("─────────────────────")

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            description="\n".join(lines),
            color=discord.Color.dark_green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="fishguide", aliases=["fishbook", "fishdex"])
    async def fishguide(self, ctx):
        """Browse all catchable fish by tier. Usage: !fishguide"""
        pages = _build_fish_guide_pages()
        view  = FishGuideView(pages, ctx.author.id)
        await ctx.send(embed=pages[0], view=view)

    @commands.command(name="fishrates", aliases=["fishchances", "droprates"])
    async def fishrates(self, ctx):
        """Show fishing drop rates by gear score. Usage: !fishrates"""
        header = f"{'GS':>3}  {'Junk':>5}  {'Comm':>5}  {'Unco':>5}  {'Rare':>5}  {'Ultra':>5}  {'Leg':>4}"
        lines  = [header, "─" * 44]
        for gs, w in _DROP_WEIGHTS.items():
            lines.append(f"{gs:>3}  {w[0]:>4}%  {w[1]:>4}%  {w[2]:>4}%  {w[3]:>4}%  {w[4]:>4}%  {w[5]:>3}%")

        embed = discord.Embed(
            title="📊 Fishing Drop Rates by GS",
            description=f"```\n{chr(10).join(lines)}\n```",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="GS = Rod tier + Float tier + Bait tier  ·  Max GS = 20")
        await ctx.send(embed=embed)

    @commands.command(name="fishrecords", aliases=["fishpb"])
    async def fishrecords(self, ctx, member: discord.Member = None):
        """View personal fish weight records. Usage: !fishrecords [@user]"""
        target     = member or ctx.author
        discord_id = str(target.id)
        records    = await utils.get_fish_records(discord_id)

        if not records:
            await ctx.send(f"**{target.display_name}** hasn't caught anything record-worthy yet.")
            return

        lines = []
        for row in records:
            tier  = _FISH_TIER_MAP.get(row["fish_name"], 1)
            color = _FISH_TIER_ANSI[tier]
            count = row["catch_count"]
            size_str = _fmt_size(row["record_kg"])
            lines.append(
                f"{color}{_FISH_TIER_EMOJI[tier]} {row['fish_name']:<22} {size_str:>12}"
                f"  ×{count}{_ANSI_RESET}"
            )

        content = f"🏆 **{target.display_name}'s Fish Records**\n```ansi\n" + "\n".join(lines) + "\n```"
        await ctx.send(content)

    @commands.command(name="bestfishers")
    async def bestfishers(self, ctx):
        """Top 5 weight records per fish, paginated. Usage: !bestfishers"""
        rows = await utils.get_all_fish_leaderboards()
        if not rows:
            await ctx.send("No fish records yet. Get fishing!")
            return

        pages = _build_leaderboard_pages(rows)
        if not pages:
            await ctx.send("No records to display.")
            return

        view = BestFishersView(pages, ctx.author.id)
        await ctx.send(pages[0], view=view)

    async def cog_load(self):
        await utils.pool.execute("""
            CREATE TABLE IF NOT EXISTS fish_records (
                discord_id  TEXT        NOT NULL,
                fish_name   TEXT        NOT NULL,
                record_kg   REAL        NOT NULL,
                catch_count INTEGER     NOT NULL DEFAULT 0,
                caught_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (discord_id, fish_name)
            )
        """)


async def setup(bot):
    await bot.add_cog(FishingCog(bot))
