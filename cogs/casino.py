import discord, random
from discord.ext import commands
import utils

_MIN_BET = 10

_SUITS  = ['♠', '♥', '♦', '♣']
_RANKS  = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
_CARD_VALUES = {
    'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
    '7': 7,  '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10,
}


def _new_deck():
    deck = [(r, s) for s in _SUITS for r in _RANKS]
    random.shuffle(deck)
    return deck

def _hand_value(hand):
    total = sum(_CARD_VALUES[r] for r, _ in hand)
    aces  = sum(1 for r, _ in hand if r == 'A')
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def _fmt_hand(hand, hide_second=False):
    if hide_second and len(hand) > 1:
        return f"{hand[0][0]}{hand[0][1]}  🂠"
    return "  ".join(f"{r}{s}" for r, s in hand)

def _bj_embed(player_hand, dealer_hand, bet, hide_dealer=True, result=None):
    color = {
        "win":  discord.Color.green(),
        "lose": discord.Color.red(),
        "push": discord.Color.light_grey(),
    }.get(result, discord.Color.blurple())
    dv = _hand_value(dealer_hand[:1]) if hide_dealer else _hand_value(dealer_hand)
    pv = _hand_value(player_hand)
    embed = discord.Embed(title="🃏 Blackjack", color=color)
    embed.add_field(
        name=f"Dealer {'🂠' if hide_dealer else f'({dv})'}",
        value=_fmt_hand(dealer_hand, hide_second=hide_dealer), inline=False
    )
    embed.add_field(name=f"You ({pv})", value=_fmt_hand(player_hand), inline=False)
    embed.set_footer(text=f"Bet: {bet:,} boops")
    return embed


class BlackjackView(discord.ui.View):
    def __init__(self, player_id: int):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.action    = None

    async def _check(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit",         style=discord.ButtonStyle.primary)
    async def hit(self, interaction, button):
        if not await self._check(interaction): return
        self.action = "hit"; self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Stand",       style=discord.ButtonStyle.secondary)
    async def stand(self, interaction, button):
        if not await self._check(interaction): return
        self.action = "stand"; self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger)
    async def double_down(self, interaction, button):
        if not await self._check(interaction): return
        self.action = "double"; self.stop()
        await interaction.response.defer()


class CasinoCog(commands.Cog, name="Casino"):

    @commands.command(name="betflip", aliases=["bf", "flip"])
    async def betflip(self, ctx, amount: int, choice: str):
        """Flip a coin for boops. Usage: !bf <amount> <h/t>"""
        if amount < _MIN_BET:
            await ctx.send(f"Minimum bet is **{_MIN_BET}** boops.")
            return
        choice = choice.lower()
        if choice not in ("h", "t", "heads", "tails"):
            await ctx.send("Choose **h** (heads) or **t** (tails).")
            return
        boops = await utils.get_boops(str(ctx.author.id))
        if boops < amount:
            await ctx.send(f"Not enough boops. You have **{boops:,}**.")
            return
        flip    = random.choice(["h", "t"])
        win     = choice[0] == flip
        new_bal = await utils.add_boops(str(ctx.author.id), amount if win else -amount, ctx.author.name)
        label   = "Heads 🪙" if flip == "h" else "Tails 🪙"
        if win:
            await ctx.send(f"**{label}!** You win **{amount:,}** boops! Balance: **{new_bal:,}**")
        else:
            await ctx.send(f"**{label}.** You lose **{amount:,}** boops. Balance: **{new_bal:,}**")

    @commands.command(name="betroll", aliases=["br"])
    async def betroll(self, ctx, amount: int):
        """Roll 1–100. >66: 2×, >90: 3×, 100: 10×. Usage: !br <amount>"""
        if amount < _MIN_BET:
            await ctx.send(f"Minimum bet is **{_MIN_BET}** boops.")
            return
        boops = await utils.get_boops(str(ctx.author.id))
        if boops < amount:
            await ctx.send(f"Not enough boops. You have **{boops:,}**.")
            return
        roll = random.randint(1, 100)
        if   roll == 100: mult, label = 10, "**JACKPOT! 100!** 🎉"
        elif roll > 90:   mult, label =  3, f"**{roll}** — Over 90! 🔥"
        elif roll > 66:   mult, label =  2, f"**{roll}** — Over 66!"
        else:             mult, label =  0, f"**{roll}** — Under 66."
        delta   = amount * mult - amount
        new_bal = await utils.add_boops(str(ctx.author.id), delta, ctx.author.name)
        if mult:
            await ctx.send(f"🎲 {label} You win **{amount * mult:,}** boops! Balance: **{new_bal:,}**")
        else:
            await ctx.send(f"🎲 {label} You lose **{amount:,}** boops. Balance: **{new_bal:,}**")

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx, amount: int):
        """Play blackjack. Usage: !bj <amount>"""
        if amount < _MIN_BET:
            await ctx.send(f"Minimum bet is **{_MIN_BET}** boops.")
            return
        boops = await utils.get_boops(str(ctx.author.id))
        if boops < amount:
            await ctx.send(f"Not enough boops. You have **{boops:,}**.")
            return

        deck        = _new_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        bet         = amount

        if _hand_value(player_hand) == 21:
            payout  = int(bet * 1.5)
            new_bal = await utils.add_boops(str(ctx.author.id), payout, ctx.author.name)
            embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="win")
            embed.description = f"🃏 **Blackjack!** You win **{payout:,}** boops! Balance: **{new_bal:,}**"
            await ctx.send(embed=embed)
            return

        msg = await ctx.send(embed=_bj_embed(player_hand, dealer_hand, bet))

        while True:
            can_double = len(player_hand) == 2 and boops >= bet * 2
            view = BlackjackView(ctx.author.id)
            if not can_double:
                view.remove_item(view.double_down)
            await msg.edit(view=view)

            timed_out = await view.wait()
            if timed_out:
                new_bal = await utils.add_boops(str(ctx.author.id), -bet, ctx.author.name)
                embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="lose")
                embed.description = f"⏱ Timed out. You lose **{bet:,}** boops. Balance: **{new_bal:,}**"
                await msg.edit(embed=embed, view=None)
                return

            if view.action == "hit":
                player_hand.append(deck.pop())
                pv = _hand_value(player_hand)
                if pv > 21:
                    new_bal = await utils.add_boops(str(ctx.author.id), -bet, ctx.author.name)
                    embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="lose")
                    embed.description = f"💥 Bust! ({pv}) You lose **{bet:,}** boops. Balance: **{new_bal:,}**"
                    await msg.edit(embed=embed, view=None)
                    return
                await msg.edit(embed=_bj_embed(player_hand, dealer_hand, bet), view=None)
                continue

            if view.action == "double":
                bet *= 2
                player_hand.append(deck.pop())
                pv = _hand_value(player_hand)
                if pv > 21:
                    new_bal = await utils.add_boops(str(ctx.author.id), -bet, ctx.author.name)
                    embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="lose")
                    embed.description = f"💥 Bust! ({pv}) You lose **{bet:,}** boops. Balance: **{new_bal:,}**"
                    await msg.edit(embed=embed, view=None)
                    return

            break  # stand or post-double — proceed to dealer

        while _hand_value(dealer_hand) < 17:
            dealer_hand.append(deck.pop())

        pv, dv = _hand_value(player_hand), _hand_value(dealer_hand)
        if dv > 21 or pv > dv:
            new_bal = await utils.add_boops(str(ctx.author.id), bet, ctx.author.name)
            embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="win")
            embed.description = f"🏆 You win **{bet:,}** boops! Balance: **{new_bal:,}**"
        elif pv == dv:
            new_bal = await utils.get_boops(str(ctx.author.id))
            embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="push")
            embed.description = f"🤝 Push — bet returned. Balance: **{new_bal:,}**"
        else:
            new_bal = await utils.add_boops(str(ctx.author.id), -bet, ctx.author.name)
            embed   = _bj_embed(player_hand, dealer_hand, bet, hide_dealer=False, result="lose")
            embed.description = f"😞 Dealer wins. You lose **{bet:,}** boops. Balance: **{new_bal:,}**"

        await msg.edit(embed=embed, view=None)


async def setup(bot):
    await bot.add_cog(CasinoCog(bot))
