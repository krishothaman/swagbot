import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
import casino_logic as casino
from cogs.quests import record_event

# The reel and the payout table live in casino_logic so the Casino Owner's hub
# plays the identical game - a button can't invoke a slash command, so the hub
# runs the game itself and would otherwise need its own copy of the odds.
SLOT_SYMBOLS = casino.SLOT_SYMBOLS


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
        balance = await db.get_balance(interaction.user.id, interaction.guild.id)
        problem = casino.validate_bet(bet, balance)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return

        await record_event(interaction.user.id, interaction.guild.id, "gamble_coins", bet)

        result = casino.coinflip_flip(random)
        won = result == choice.value
        payout = casino.coinflip_payout(bet, won)
        # Deliberately NOT pay_with_boost: the house earnings boost covers
        # work, dailies and quests. Boosting a win here would make laundering
        # coins through a coinflip a better rate than any honest job.
        new_balance = await db.update_balance(interaction.user.id, interaction.guild.id, payout)

        outcome = f"🎉 It landed on **{result}** - you win **{bet}** coins!" if won \
            else f"💀 It landed on **{result}** - you lose **{bet}** coins."

        await interaction.response.send_message(f"{outcome}\nNew balance: **{new_balance}**")

    @app_commands.command(name="slots", description="Spin the slot machine")
    @app_commands.describe(bet="How many coins to bet")
    async def slots(self, interaction: discord.Interaction, bet: int):
        balance = await db.get_balance(interaction.user.id, interaction.guild.id)
        problem = casino.validate_bet(bet, balance)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return

        await record_event(interaction.user.id, interaction.guild.id, "gamble_coins", bet)

        spin = casino.spin(random)
        display = " | ".join(spin)
        payout, kind = casino.slots_payout(spin, bet)
        outcome = {
            "jackpot": f"🎰 JACKPOT! All three match! +{payout} coins",
            "pair": f"🎰 Two match! +{payout} coins",
            "miss": f"🎰 No match. {payout} coins",
        }[kind]

        # Not boosted by your house - see the note in coinflip above.
        new_balance = await db.update_balance(interaction.user.id, interaction.guild.id, payout)

        embed = discord.Embed(title="Slots", description=display, color=discord.Color.purple())
        embed.add_field(name="Result", value=outcome, inline=False)
        embed.set_footer(text=f"New balance: {new_balance}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
