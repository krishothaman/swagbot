import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import MIN_BET
from cogs.quests import record_event

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

        result = random.choice(["heads", "tails"])
        won = result == choice.value
        payout = bet if won else -bet
        new_balance = await db.update_balance(interaction.user.id, interaction.guild.id, payout)

        outcome = f"🎉 It landed on **{result}** - you win **{bet}** coins!" if won \
            else f"💀 It landed on **{result}** - you lose **{bet}** coins."

        await interaction.response.send_message(f"{outcome}\nNew balance: **{new_balance}**")

    @app_commands.command(name="slots", description="Spin the slot machine")
    @app_commands.describe(bet="How many coins to bet")
    async def slots(self, interaction: discord.Interaction, bet: int):
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

        spin = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        display = " | ".join(spin)

        if spin[0] == spin[1] == spin[2]:
            payout = bet * 10
            outcome = f"🎰 JACKPOT! All three match! +{payout} coins"
        elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
            payout = bet * 2
            outcome = f"🎰 Two match! +{payout} coins"
        else:
            payout = -bet
            outcome = f"🎰 No match. {payout} coins"

        new_balance = await db.update_balance(interaction.user.id, interaction.guild.id, payout)

        embed = discord.Embed(title="Slots", description=display, color=discord.Color.purple())
        embed.add_field(name="Result", value=outcome, inline=False)
        embed.set_footer(text=f"New balance: {new_balance}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
