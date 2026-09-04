import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import MIN_BET
from cogs.quests import record_event

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def new_deck() -> list[tuple[str, str]]:
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def hand_value(hand: list[tuple[str, str]]) -> int:
    value = 0
    aces = 0
    for rank, _ in hand:
        if rank in ("J", "Q", "K"):
            value += 10
        elif rank == "A":
            value += 11
            aces += 1
        else:
            value += int(rank)

    while value > 21 and aces:
        value -= 10
        aces -= 1

    return value


def format_hand(hand: list[tuple[str, str]]) -> str:
    return " ".join(f"{rank}{suit}" for rank, suit in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, player_id: int, guild_id: int, bet: int, deck, player_hand, dealer_hand):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.guild_id = guild_id
        self.bet = bet
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.finished = False

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        for child in self.children:
            child.disabled = True

    async def _end_game(self, interaction: discord.Interaction, result: str, payout: int):
        """result: 'win', 'lose', 'push'. payout is the amount to add to balance
        (already signed - positive for win, negative for lose, 0 for push since
        the bet was never deducted up front in this implementation)."""
        self.finished = True
        self._disable_buttons()

        new_balance = await db.update_balance(self.player_id, self.guild_id, payout)

        player_val = hand_value(self.player_hand)
        dealer_val = hand_value(self.dealer_hand)

        if result == "win":
            outcome_text = f"Hell yeah! (+{payout} coins)"
        elif result == "lose":
            outcome_text = f"You lose. ({payout} coins)"
        else:
            outcome_text = "Push - bet returned."

        embed = discord.Embed(title="Blackjack - Result", color=discord.Color.blurple())
        embed.add_field(name="Your hand", value=f"{format_hand(self.player_hand)} ({player_val})", inline=False)
        embed.add_field(name="Dealer hand", value=f"{format_hand(self.dealer_hand)} ({dealer_val})", inline=False)
        embed.add_field(name="Result", value=outcome_text, inline=False)
        embed.set_footer(text=f"New balance: {new_balance}")

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        if self.finished:
            return

        self.player_hand.append(self.deck.pop())
        value = hand_value(self.player_hand)

        if value > 21:
            await self._end_game(interaction, "lose", -self.bet)
            return

        embed = discord.Embed(title="Blackjack", color=discord.Color.blurple())
        embed.add_field(name="Your hand", value=f"{format_hand(self.player_hand)} ({value})", inline=False)
        embed.add_field(name="Dealer shows", value=format_hand(self.dealer_hand[:1]) + " ??", inline=False)
        embed.set_footer(text=f"Bet: {self.bet}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        if self.finished:
            return

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

        player_val = hand_value(self.player_hand)
        dealer_val = hand_value(self.dealer_hand)

        if dealer_val > 21 or player_val > dealer_val:
            await self._end_game(interaction, "win", self.bet)
        elif player_val == dealer_val:
            await self._end_game(interaction, "push", 0)
        else:
            await self._end_game(interaction, "lose", -self.bet)


class Blackjack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Play a game of blackjack")
    @app_commands.describe(bet="How many coins to bet")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        if bet < MIN_BET:
            await interaction.response.send_message(f"Minimum bet is **{MIN_BET}** coins.", ephemeral=True)
            return

        balance = await db.get_balance(interaction.user.id, interaction.guild.id)
        if balance < bet:
            await interaction.response.send_message(
                f"You don't have enough coins. Your balance: **{balance}**", ephemeral=True
            )
            return

        await record_event(interaction.user.id, interaction.guild.id, "gamble_coins", bet)

        deck = new_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        if hand_value(player_hand) == 21:
            payout = int(bet * 1.5)
            await db.update_balance(interaction.user.id, interaction.guild.id, payout)
            embed = discord.Embed(title="BLACKJACK!", color=discord.Color.gold())
            embed.add_field(name="Your hand", value=f"{format_hand(player_hand)} (21)", inline=False)
            embed.add_field(name="Result", value=f"Natural blackjack! +{payout} coins", inline=False)
            await interaction.response.send_message(embed=embed)
            return

        view = BlackjackView(interaction.user.id, interaction.guild.id, bet, deck, player_hand, dealer_hand)
        embed = discord.Embed(title="Blackjack", color=discord.Color.blurple())
        embed.add_field(name="Your hand", value=f"{format_hand(player_hand)} ({hand_value(player_hand)})", inline=False)
        embed.add_field(name="Dealer shows", value=format_hand(dealer_hand[:1]) + " ??", inline=False)
        embed.set_footer(text=f"Bet: {bet}")
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))
