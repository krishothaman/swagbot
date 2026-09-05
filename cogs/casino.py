"""The Casino Owner - the house, wearing a very good suit.

The merchant whispers, the landlord withholds, the gun man overshares. This
one is warm at you. He is pleased you came, he remembers your name, and every
single thing he says is true and is also working on him rather than for you.
He never pressures anyone to play. He doesn't have to.

--- WHY HE RUNS THE GAMES HIMSELF ---

A Discord button cannot invoke a slash command. So "the hub launches
/coinflip" isn't a thing that can be built - the hub has to deal the cards
itself. That's why the odds moved into casino_logic.py: both doors call the
same table, and nobody can tune one without tuning the other.

Blackjack is the exception. It's an interactive hand with its own view, so the
button hands straight off to the existing BlackjackView rather than
reimplementing hit/stand.

NOT a cog, despite living in cogs/ - he has no slash commands of his own and
/talk routes into him, the same way the landlord and the gun man do. Do not
add this to COGS in bot.py; there is no setup() to call.
"""

import random

import discord

import database as db
import casino_logic as casino
from config import MIN_BET
from cogs.quests import record_event

CASINO_ID = "casino_owner"

GREETINGS = [
    "There he is. I had a feeling about tonight. Sit anywhere you like — "
    "the tables don't mind, and neither do I.",

    "Welcome back. Your seat's still warm, which either means you never left "
    "or somebody's been sitting in it. Let's not investigate.",

    "Evening. Drinks are free, the carpet's new, and the math hasn't changed "
    "since the last time you asked. Play whatever you want.",

    "Good, good, come in. I was starting to worry the room was too quiet. "
    "A quiet room makes people think.",
]

# He never lies, and that's the unsettling part.
FLAVOR = [
    "I don't need you to lose. I need you to keep playing. Those are "
    "different, and only one of them is my business.",

    "Everybody who works here is very nice to you. That's not a coincidence, "
    "it's a line item.",

    "The odds are on the wall. Nobody reads the wall. I keep putting it up.",

    "There's no clock in here. People notice that eventually. Usually later "
    "than they'd like.",

    "I've never once had to ask a man to sit down. Not once, in all these "
    "years. Think about that on the way out.",
]


async def _resolve_bet(user_id: int, guild_id: int, bet: int):
    """Shared front door for every table: validate, then bank the wager
    against the gambling quest counter. Returns a refusal string, or None if
    play should continue.

    Counting the stake here rather than per game means a new table can't
    forget to feed gamble_coins - which would make the quest silently
    uncompletable depending on which game you chose.
    """
    balance = await db.get_balance(user_id, guild_id)
    problem = casino.validate_bet(bet, balance)
    if problem:
        return problem
    await record_event(user_id, guild_id, "gamble_coins", bet)
    return None


async def play_coinflip(user_id: int, guild_id: int, bet: int, choice: str) -> str:
    """One flip. Returns the line to show, whether it was played or refused."""
    refusal = await _resolve_bet(user_id, guild_id, bet)
    if refusal:
        return refusal

    result = casino.coinflip_flip(random)
    won = result == choice
    payout = casino.coinflip_payout(bet, won)
    # Not pay_with_boost - the house earnings boost stops at honest work.
    new_balance = await db.update_balance(user_id, guild_id, payout)

    head = (f"It's **{result}**. You called it — **+{bet}**."
            if won else f"It's **{result}**. Not your side — **-{bet}**.")
    return f"{head}\nBalance: **{new_balance:,}**"


async def play_slots(user_id: int, guild_id: int, bet: int) -> str:
    refusal = await _resolve_bet(user_id, guild_id, bet)
    if refusal:
        return refusal

    reels = casino.spin(random)
    payout, kind = casino.slots_payout(reels, bet)
    new_balance = await db.update_balance(user_id, guild_id, payout)

    line = {
        "jackpot": f"**ALL THREE.** +{payout:,}. The room is looking at you.",
        "pair": f"Two of a kind. +{payout:,}.",
        "miss": f"Nothing. -{bet:,}.",
    }[kind]
    return f"{' | '.join(reels)}\n{line}\nBalance: **{new_balance:,}**"


class BetModal(discord.ui.Modal):
    """Asks for a stake. Buttons can't take arguments, so this is how a table
    finds out how much you want on it."""

    bet = discord.ui.TextInput(label="How much?", placeholder="100", max_length=12)

    def __init__(self, title: str, on_bet):
        super().__init__(title=title)
        self.on_bet = on_bet

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.bet.value).strip().replace(",", "")
        if not raw.lstrip("-").isdigit():
            await interaction.response.send_message(
                "That's not a number. The tables are picky about that.", ephemeral=True
            )
            return
        await self.on_bet(interaction, int(raw))


class CasinoView(discord.ui.View):
    """The floor. One button per table."""

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your night.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Coinflip", style=discord.ButtonStyle.primary)
    async def coinflip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        async def played(modal_interaction: discord.Interaction, bet: int):
            view = CoinSideView(self.user_id, self.guild_id, bet)
            await modal_interaction.response.send_message(
                f"**{bet:,}** on the table. Call it.", view=view, ephemeral=True
            )

        await interaction.response.send_modal(BetModal("Coinflip", played))

    @discord.ui.button(label="Slots", style=discord.ButtonStyle.primary)
    async def slots(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        async def played(modal_interaction: discord.Interaction, bet: int):
            message = await play_slots(self.user_id, self.guild_id, bet)
            await modal_interaction.response.send_message(message)

        await interaction.response.send_modal(BetModal("Slots", played))

    @discord.ui.button(label="Blackjack", style=discord.ButtonStyle.primary)
    async def blackjack(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        async def played(modal_interaction: discord.Interaction, bet: int):
            # Handed straight to the existing view rather than reimplemented:
            # blackjack is an interactive hand, not a single roll.
            from cogs.blackjack import (
                new_deck, hand_value, format_hand, BlackjackView,
            )

            refusal = await _resolve_bet(self.user_id, self.guild_id, bet)
            if refusal:
                await modal_interaction.response.send_message(refusal, ephemeral=True)
                return

            deck = new_deck()
            player_hand = [deck.pop(), deck.pop()]
            dealer_hand = [deck.pop(), deck.pop()]

            if hand_value(player_hand) == 21:
                payout = int(bet * 1.5)
                await db.update_balance(self.user_id, self.guild_id, payout)
                embed = discord.Embed(title="BLACKJACK!", color=discord.Color.gold())
                embed.add_field(name="Your hand",
                                value=f"{format_hand(player_hand)} (21)", inline=False)
                embed.add_field(name="Result",
                                value=f"Natural blackjack! +{payout} coins", inline=False)
                await modal_interaction.response.send_message(embed=embed)
                return

            view = BlackjackView(self.user_id, self.guild_id, bet, deck,
                                 player_hand, dealer_hand)
            embed = discord.Embed(title="Blackjack", color=discord.Color.blurple())
            embed.add_field(
                name="Your hand",
                value=f"{format_hand(player_hand)} ({hand_value(player_hand)})",
                inline=False,
            )
            embed.add_field(
                name="Dealer shows",
                value=f"{format_hand(dealer_hand[:1])} + ?",
                inline=False,
            )
            await modal_interaction.response.send_message(embed=embed, view=view)

        await interaction.response.send_modal(BetModal("Blackjack", played))

    @discord.ui.button(label="Quests", style=discord.ButtonStyle.success)
    async def quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        # Reuses the shared NPC quest browser so his quests behave exactly like
        # everyone else's - imported here because cogs.npc imports this module.
        from cogs.npc import show_npc_quests
        await show_npc_quests(interaction, self.user_id, self.guild_id, CASINO_ID)


class CoinSideView(discord.ui.View):
    """Heads or tails, once the stake is known."""

    def __init__(self, user_id: int, guild_id: int, bet: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet = bet

    async def _call(self, interaction: discord.Interaction, side: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your bet.", ephemeral=True)
            return
        message = await play_coinflip(self.user_id, self.guild_id, self.bet, side)
        await interaction.response.edit_message(content=message, view=None)

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.secondary)
    async def heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._call(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._call(interaction, "tails")


async def casino_intro(user_id: int, guild_id: int):
    """Returns (embed, view). Unlike the gun man there's no gate - the house
    is happy to take money from anyone, and saying so is the character."""
    greeting = random.choice(GREETINGS)

    flavor = await db.get_npc_flavor_lines(CASINO_ID)
    if flavor:
        greeting = f"{greeting}\n\n*{random.choice(flavor)}*"

    balance = await db.get_balance(user_id, guild_id)
    embed = discord.Embed(
        title="The Casino Owner",
        description=greeting,
        color=discord.Color.dark_teal(),
    )
    embed.add_field(name="Your chips", value=f"{balance:,} coins", inline=True)
    embed.add_field(name="Minimum", value=f"{MIN_BET} coins", inline=True)
    embed.set_footer(text="House")
    return embed, CasinoView(user_id, guild_id)
