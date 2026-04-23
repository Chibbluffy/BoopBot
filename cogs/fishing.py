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

# (tier, name, min_boops, max_boops)
FISH_LOOT = [
    (0, "Old Boot",            2,    8),
    (0, "Tin Can",             1,    5),
    (0, "Seaweed",             3,   10),
    (1, "Carp",               15,   35),
    (1, "Perch",              20,   45),
    (1, "Sardine",            25,   55),
    (2, "Bass",               60,  120),
    (2, "Trout",              80,  150),
    (2, "Catfish",            90,  180),
    (3, "Tuna",              200,  400),
    (3, "Swordfish",         300,  500),
    (3, "Salmon",            250,  450),
    (4, "Golden Coelacanth", 1_500, 3_000),
    (4, "Ancient Sturgeon",  2_000, 4_000),
    (4, "Khalks Crab",       3_000, 5_000),
]

_FISH_TIER_EMOJI  = ["🥾", "🐟", "🐠", "🐡", "🦀"]
_FISH_TIER_COLORS = [0x607080, 0x4CAF50, 0x2196F3, 0x9C27B0, 0xFFD700]


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
    return fish[1], random.randint(fish[2], fish[3]), tier

def _find_item(query: str):
    q = query.lower()
    for item_id, item in SHOP_ITEMS.items():
        if q == item_id or q == item["name"].lower():
            return item_id, item
    for item_id, item in SHOP_ITEMS.items():
        if q in item["name"].lower() or q in item_id:
            return item_id, item
    return None, None


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

    @commands.command(name="fish")
    async def fish(self, ctx):
        """Cast your line and catch fish for boops!"""
        discord_id = str(ctx.author.id)
        profile    = await utils.get_fishing_profile(discord_id)

        embed = discord.Embed(description="🎣 Casting your line...", color=0x1e90ff)
        msg   = await ctx.send(embed=embed)

        await asyncio.sleep(random.uniform(2, 5))

        view = FishingView(ctx.author.id)
        embed.description = "🐟 Something's tugging on the line! Quick!"
        await msg.edit(embed=embed, view=view)

        timed_out = await view.wait()

        if timed_out or not view.clicked:
            embed.description = "🌊 The fish slipped away... Cast again!"
            embed.color = 0x607080
            await msg.edit(embed=embed, view=None)
            return

        if profile["active_bait"]:
            await utils.use_bait(discord_id, profile["active_bait"])
            profile = await utils.get_fishing_profile(discord_id)

        score              = _gear_score(profile["active_rod"], profile["active_float"], profile.get("active_bait"))
        fish_name, value, tier = _roll_fish(score)

        new_bal = await utils.add_boops(discord_id, value, ctx.author.name)
        embed.description = (
            f"{_FISH_TIER_EMOJI[tier]} **{ctx.author.display_name}** caught a **{fish_name}**!\n"
            f"+**{value:,}** boops  ·  Balance: **{new_bal:,}**"
        )
        embed.color = _FISH_TIER_COLORS[tier]
        await msg.edit(embed=embed, view=None)

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
                    prices = "  ".join(f"`{q}={item['price']*q:,}`" for q in BAIT_QUANTITIES)
                    lines.append(f"**{item['name']}** — {item['price']} ea\n  {prices}\n  _{item['desc']}_")
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


async def setup(bot):
    await bot.add_cog(FishingCog(bot))
