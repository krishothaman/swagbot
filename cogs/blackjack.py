import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import MIN_BET

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def new_deck() -> list[tuple[str, str]]:
    """Returns a shuffled deck as a list of (rank, suit) tuples."""
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def hand_value(hand: list[tuple[str, str]]) -> int:
    """Calculates blackjack value of a hand, treating Aces as 11 or 1
    automatically (soft/hard hand logic) so you don't have to."""
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
    """Interactive Hit/Stand buttons for an active game.
    TODO (Czar): this is the core of the game - fill in the pieces below."""

    def __init__(self, player_id: int, guild_id: int, bet: int, deck, player_hand, dealer_hand):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.guild_id = guild_id
        self.bet = bet
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        # TODO (Czar):
        # 1. Guard: if interaction.user.id != self.player_id, ignore/reject (not their game)
        # 2. Draw a card: self.player_hand.append(self.deck.pop())
        # 3. Recalculate hand_value(self.player_hand)
        # 4. If bust (> 21):
        #      - subtract self.bet from player's balance (they already paid it up front? decide
        #        whether you deduct the bet at game start or only on loss - pick one and be
        #        consistent)
        #      - disable buttons (self.stop() or set self.children disabled)
        #      - edit the message announcing the bust
        # 5. Otherwise, edit the message showing the updated hand and keep playing
        pass

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        # TODO (Czar):
        # 1. Guard: same player check as hit()
        # 2. Dealer draws until hand_value(dealer_hand) >= 17 (standard blackjack dealer rule)
        # 3. Compare hand_value(player_hand) vs hand_value(dealer_hand):
        #      - dealer busts or player > dealer -> player wins, award 2x bet (or whatever
        #        payout ratio you want)
        #      - tie -> push, return their bet
        #      - otherwise -> player loses
        # 4. Use db.update_balance(...) to apply the result
        # 5. Edit the message with the final result, disable buttons
        pass


class Blackjack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Play a game of blackjack")
    @app_commands.describe(bet="How many coins to bet")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        # TODO (Czar):
        # 1. Validate bet >= MIN_BET and player has enough balance
        # 2. deck = new_deck()
        # 3. Deal 2 cards each to player_hand and dealer_hand (deck.pop() x4)
        # 4. Check for natural blackjack (player_hand value == 21 with 2 cards) - instant win
        # 5. Otherwise, send a message showing player's hand + one dealer card (hide the other),
        #    attach a BlackjackView(...), and let the buttons take over
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))
