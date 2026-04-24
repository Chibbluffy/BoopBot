import discord, asyncio, random
from discord.ext import commands
import utils

SHOP_ITEMS = {
    # Rods (permanent, tier 1-4)
    "rod_ash":        {"name": "Ash Rod",        "category": "rod",   "price":     500, "tier": 1, "desc": "A step up from twigs."},
    "rod_maple":      {"name": "Maple Rod",      "category": "rod",   "price":   2_000, "tier": 2, "desc": "Balanced and reliable."},
    "rod_mediah":     {"name": "Mediah Rod",     "category": "rod",   "price":   8_000, "tier": 3, "desc": "Favored by serious fishers."},
    "rod_gold":       {"name": "Gold Rod",       "category": "rod",   "price":  30_000, "tier": 4, "desc": "Legendary catches await."},
    # Floats (permanent, tier 1-4)
    "float_basic":    {"name": "Basic Float",    "category": "float", "price":     200, "tier": 1, "desc": "Improves line sensitivity."},
    "float_balenos":  {"name": "Balenos Float",  "category": "float", "price":   1_000, "tier": 2, "desc": "Lightweight Balenos craftsmanship."},
    "float_mediah":   {"name": "Mediah Float",   "category": "float", "price":   5_000, "tier": 3, "desc": "Deep-water detection."},
    "float_calpheon": {"name": "Calpheon Float", "category": "float", "price":  15_000, "tier": 4, "desc": "The pinnacle of float design."},
    # Bait (consumable, 1 per cast, tier 0-2)
    "bait_worm":      {"name": "Worm",           "category": "bait",  "price":       2, "tier": 0, "desc": "Basic bait. Gets the job done."},
    "bait_crab":      {"name": "Crab Bait",      "category": "bait",  "price":      10, "tier": 1, "desc": "Attracts better fish."},
    "bait_special":   {"name": "Special Bait",   "category": "bait",  "price":     100, "tier": 2, "desc": "Rare fish are drawn to this."},
}

BAIT_QUANTITIES = [1, 5, 25, 100, 500, 2_000]

# (tier, name, value, min_kg, max_kg)
FISH_LOOT = [
    # Junk (tier 0) — no records, no meaningful value
    (0, "Old Fishing Rod",    1,   0.1,   1.5),
    (0, "Ripped Tights",      1,   0.05,  0.4),
    (0, "Broken Bottle",      1,   0.1,   0.8),
    (0, "Torn Net",           1,   0.2,   1.5),
    # Common (tier 1) — ~1,500 BDO silver / 1,000
    (1, "Beltfish",           2,   0.5,   3.0),
    (1, "Anchovy",            1,   0.05,  0.3),
    (1, "Dace",               2,   0.1,   1.5),
    (1, "Grunt",              2,   0.1,   1.5),
    (1, "Mudskipper",         1,   0.05,  0.3),
    # Uncommon (tier 2) — ~15,000–29,000 BDO silver / 1,000
    (2, "Grouper",           18,   2.0,  20.0),
    (2, "Flounder",          15,   0.5,   5.0),
    (2, "Croaker",           18,   0.5,   4.0),
    (2, "Pomfret",           23,   0.5,   3.0),
    (2, "Angler",            29,   1.0,  10.0),
    # Rare (tier 3) — ~150,000–165,000 BDO silver / 1,000
    (3, "Tuna",             154,  30.0, 200.0),
    (3, "Tilefish",         153,   2.0,  15.0),
    (3, "Greater Amberjack",157,   5.0,  50.0),
    (3, "Goliath Grouper",  156,  20.0, 300.0),
    (3, "Skate",            165,   2.0,  25.0),
    # Legendary (tier 4) — BDO prize fish / 1,000
    (4, "Silver Beltfish",  1_000,  5.0,  30.0),
    (4, "Yellow Corvina",     800,  3.0,  20.0),
    (4, "Blue Bat Star",      600,  0.1,   1.5),
    (4, "Requiem Shark",    1_500, 50.0, 300.0),
    (4, "Giant Black Squid",1_200, 10.0,  80.0),
]

# fish_name → tier lookup for display coloring
_FISH_TIER_MAP: dict[str, int] = {f[1]: f[0] for f in FISH_LOOT}

# Non-junk fish in legendary-first order for leaderboard pages
_FISH_ORDER = [f[1] for f in FISH_LOOT[::-1] if f[0] > 0]

_FISH_PER_PAGE = 3
_TOP_N         = 5

_FISH_TIER_EMOJI = ["🥾", "🐟", "🐠", "🐡", "🦀"]

_ANSI_RESET    = "\u001b[0m"
_ANSI_BAL      = "\u001b[1;37m"   # bold white for balance suffix
_FISH_TIER_ANSI = [
    "\u001b[2;37m",  # tier 0 junk:      dim white
    "\u001b[0;32m",  # tier 1 common:    green
    "\u001b[0;34m",  # tier 2 uncommon:  blue
    "\u001b[0;35m",  # tier 3 rare:      purple
    "\u001b[1;33m",  # tier 4 legendary: bold yellow
]


def _gear_score(rod_id, float_id, bait_id):
    return (
        SHOP_ITEMS.get(rod_id,   {}).get("tier", 0) +
        SHOP_ITEMS.get(float_id, {}).get("tier", 0) +
        SHOP_ITEMS.get(bait_id,  {}).get("tier", 0)
    )

def _roll_fish(gear_score):
    weights = [
        max(2,  30 - gear_score * 2.5),
        max(10, 40 - gear_score * 1.5),
        min(45, 18 + gear_score * 2.0),
        min(30,  8 + gear_score * 2.0),
        min(15,  4 + gear_score * 0.5),
    ]
    tier = random.choices([0, 1, 2, 3, 4], weights=weights, k=1)[0]
    pool = [f for f in FISH_LOOT if f[0] == tier]
    fish = random.choice(pool)
    # fish = (tier, name, value, min_kg, max_kg)
    size_kg = round(random.uniform(fish[3], fish[4]), 1)
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
                lines.append(f"  {j}. {entry['name']:<16} {entry['record_kg']:.1f} kg")
            lines.append("")
        content = (
            f"🏆 **Best Fishers** — Page {p}/{total_pages}\n"
            f"```ansi\n{chr(10).join(lines).rstrip()}\n```"
        )
        pages.append(content)
    return pages


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
    def __init__(self, caster_id: int):
        super().__init__(timeout=20)
        self.caster_id = caster_id
        self.clicked   = False

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
        discord_id = str(ctx.author.id)
        profile    = await utils.get_fishing_profile(discord_id)

        # Delete the !fish command to keep chat clean
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        embed    = discord.Embed(description="🎣 Casting your line...", color=0x1e90ff)
        cast_msg = await ctx.send(embed=embed)

        await asyncio.sleep(random.uniform(2, 5))

        view = FishingView(ctx.author.id)
        embed.description = "🐟 Something's tugging on the line! Quick!"
        await cast_msg.edit(embed=embed, view=view)

        timed_out = await view.wait()

        # Always delete the cast/reel message before showing results
        try:
            await cast_msg.delete()
        except discord.NotFound:
            pass

        if timed_out or not view.clicked:
            await self._update_log(ctx, "🌊 Got away...", await utils.get_boops(discord_id), 0)
            return

        if profile["active_bait"]:
            await utils.use_bait(discord_id, profile["active_bait"])
            profile = await utils.get_fishing_profile(discord_id)

        score                         = _gear_score(profile["active_rod"], profile["active_float"], profile.get("active_bait"))
        fish_name, value, tier, size_kg = _roll_fish(score)
        new_bal                       = await utils.add_boops(discord_id, value, ctx.author.name)

        is_pb = False
        if tier > 0:
            is_pb, _ = await utils.update_fish_record(discord_id, fish_name, size_kg)

        line = f"{_FISH_TIER_EMOJI[tier]} {fish_name}  {size_kg:.1f} kg  +{value:,}"
        await self._update_log(ctx, line, new_bal, tier, is_pb)

    @commands.command(name="shop")
    async def shop(self, ctx):
        """Browse the fishing shop."""
        embed = discord.Embed(title="🏪 Fishing Shop", color=discord.Color.blurple())
        for category, label in [("rod", "🎣 Rods"), ("float", "🪝 Floats"), ("bait", "🪱 Bait")]:
            lines = []
            for item_id, item in SHOP_ITEMS.items():
                if item["category"] != category:
                    continue
                if category == "bait":
                    lines.append(f"**{item['name']}** — {item['price']} ea\n  _{item['desc']}_")
                else:
                    lines.append(f"**{item['name']}** — {item['price']:,} boops\n  _{item['desc']}_")
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
        elif item["category"] == "bait" and qty not in BAIT_QUANTITIES:
            await ctx.send(f"Available quantities: {', '.join(str(q) for q in BAIT_QUANTITIES)}")
            return

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

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx):
        """View your fishing gear and bait."""
        discord_id = str(ctx.author.id)
        profile    = await utils.get_fishing_profile(discord_id)
        inv        = await utils.get_inventory(discord_id)

        def item_name(iid):
            if iid == "rod_starter": return "Starter Rod"
            return SHOP_ITEMS.get(iid, {}).get("name", iid) if iid else "None"

        lines = [
            f"🎣 **Rod:**   {item_name(profile['active_rod'])}",
            f"🪝 **Float:** {item_name(profile['active_float']) if profile['active_float'] else 'None'}",
            f"🪱 **Bait:**  {item_name(profile['active_bait'])  if profile['active_bait']  else 'None'}",
            "", "**Owned:**",
        ]
        equipped  = {profile["active_rod"], profile["active_float"], profile["active_bait"]}
        has_items = False
        for item_id, qty in inv.items():
            if qty <= 0: continue
            name = SHOP_ITEMS.get(item_id, {}).get("name", item_id)
            tag  = " *(equipped)*" if item_id in equipped else ""
            lines.append(f"  {name} ×{qty}{tag}")
            has_items = True
        if not has_items:
            lines.append("  Nothing yet. Visit `!shop`!")

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            description="\n".join(lines),
            color=discord.Color.dark_green()
        )
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
            lines.append(
                f"{color}{_FISH_TIER_EMOJI[tier]} {row['fish_name']:<22} {row['record_kg']:>7.1f} kg"
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
        await utils.pool.execute(
            "ALTER TABLE fish_records ADD COLUMN IF NOT EXISTS catch_count INTEGER NOT NULL DEFAULT 0"
        )


async def setup(bot):
    await bot.add_cog(FishingCog(bot))
