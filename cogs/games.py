import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import MIN_BET

SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🍉", "⭐", "💎"]


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="coinflip", description="Bet on a coinflip")
    @app_commands.describe(bet="How many coins to bet", choice="heads or tails")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: app_commands.Choice[str]):
        # TODO (Czar):
        # 1. Validate bet >= MIN_BET and user has enough balance
        # 2. result = random.choice(["heads", "tails"])
        # 3. If result == choice.value -> win, award e.g. 2x bet
        #    else -> lose, deduct bet
        # 4. Respond showing the result and new balance
        pass

    @app_commands.command(name="slots", description="Spin the slot machine")
    @app_commands.describe(bet="How many coins to bet")
    async def slots(self, interaction: discord.Interaction, bet: int):
        # TODO (Czar):
        # 1. Validate bet >= MIN_BET and user has enough balance
        # 2. Spin 3 random symbols: [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        # 3. Decide payout rules yourself, e.g.:
        #      - all 3 match -> big win (5x-10x bet)
        #      - 2 match -> small win (2x bet)
        #      - no match -> lose the bet
        # 4. Respond showing the spin result (e.g. "🍒 | 🍋 | 🍒") and outcome
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
