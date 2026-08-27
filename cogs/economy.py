import time
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import DAILY_REWARD, DAILY_COOLDOWN_SECONDS, WORK_MIN_REWARD, WORK_MAX_REWARD, WORK_COOLDOWN_SECONDS


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your (or someone else's) balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        await interaction.response.send_message(f"{member.mention} has {db.get_balance(member.id, interaction.guild.id)} coins")

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        last_daily = await db.get_cooldown(interaction.user.id, interaction.guild.id, "last_daily") 
        # TODO (Czar):
        # 1. Get last claim time: `await db.get_cooldown(user_id, guild_id, "last_daily")`
        # 2. Compare `time.time() - last_claim` against DAILY_COOLDOWN_SECONDS
        # 3. If still on cooldown -> tell them how long is left (format the seconds nicely)
        # 4. If not on cooldown ->
        #       await db.update_balance(user_id, guild_id, DAILY_REWARD)
        #       await db.set_cooldown(user_id, guild_id, "last_daily")
        #    then confirm to the user
        pass

    @app_commands.command(name="work", description="Work to earn some coins")
    async def work(self, interaction: discord.Interaction):
        # TODO (Czar): same cooldown pattern as /daily, but:
        # - use "last_work" and WORK_COOLDOWN_SECONDS instead
        # - reward should be random.randint(WORK_MIN_REWARD, WORK_MAX_REWARD)
        #   instead of a fixed amount - import `random` for this
        # - bonus idea: pick a random flavor-text message like
        #   "You worked as a {job} and earned {amount} coins" from a list of jobs
        pass

    @app_commands.command(name="transfer", description="Send coins to another user")
    @app_commands.describe(member="Who to send coins to", amount="How many coins to send")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        # TODO (Czar):
        # 1. Validate: amount > 0, member is not interaction.user (can't pay yourself),
        #    member is not a bot
        # 2. Check sender has enough balance (get_balance first)
        # 3. If valid: update_balance(sender, -amount) and update_balance(receiver, +amount)
        # 4. Respond confirming the transfer
        # Edge case to think about: what if two /transfer commands run at the same
        # instant for the same user? (not critical for a personal-server bot, but
        # good to think about for the "explain your architecture" interview angle)
        pass

    @app_commands.command(name="leaderboard", description="See the richest users in this server")
    async def leaderboard(self, interaction: discord.Interaction):
        # TODO (Czar):
        # 1. `rows = await db.get_leaderboard(interaction.guild.id, order_by="balance")`
        # 2. rows is a list of (user_id, balance) tuples
        # 3. Resolve each user_id to a display name with interaction.guild.get_member(user_id)
        # 4. Build a formatted leaderboard message/embed
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
