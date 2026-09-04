import time
import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import DAILY_REWARD, DAILY_COOLDOWN_SECONDS, WORK_MIN_REWARD, WORK_MAX_REWARD, WORK_COOLDOWN_SECONDS
from cogs.quests import record_event

JOBS = [
    "delivery driver", "street musician", "dog walker", "barista",
    "freelance coder", "mechanic", "chef", "taxi driver",
]


def format_seconds(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your (or someone else's) balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        bal = await db.get_balance(member.id, interaction.guild.id)
        await interaction.response.send_message(f"{member.mention} has **{bal}** coins")

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild.id
        last_claim = await db.get_cooldown(user_id, guild_id, "last_daily")
        elapsed = time.time() - last_claim

        if elapsed < DAILY_COOLDOWN_SECONDS:
            remaining = DAILY_COOLDOWN_SECONDS - elapsed
            await interaction.response.send_message(
                f"You've already claimed your daily. Come back in **{format_seconds(remaining)}**.",
                ephemeral=True,
            )
            return

        new_balance = await db.update_balance(user_id, guild_id, DAILY_REWARD)
        await db.set_cooldown(user_id, guild_id, "last_daily")
        await interaction.response.send_message(
            f"You claimed your daily reward of **{DAILY_REWARD}** coins. New balance: **{new_balance}**"
        )

    @app_commands.command(name="work", description="Work to earn some coins")
    async def work(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild.id
        last_work = await db.get_cooldown(user_id, guild_id, "last_work")
        elapsed = time.time() - last_work

        if elapsed < WORK_COOLDOWN_SECONDS:
            remaining = WORK_COOLDOWN_SECONDS - elapsed
            await interaction.response.send_message(
                f"Too tired buddy. Try again in **{format_seconds(remaining)}**.",
                ephemeral=True,
            )
            return

        earnings = random.randint(WORK_MIN_REWARD, WORK_MAX_REWARD)
        job = random.choice(JOBS)
        new_balance = await db.update_balance(user_id, guild_id, earnings)
        await db.set_cooldown(user_id, guild_id, "last_work")
        # Counted after the cooldown check, so only real shifts count.
        await record_event(user_id, guild_id, "work_count", 1)
        await interaction.response.send_message(
            f"You worked as a **{job}** and earned **{earnings}** coins. New balance: **{new_balance}**"
        )

    @app_commands.command(name="transfer", description="Send coins to another user")
    @app_commands.describe(member="Who to send coins to", amount="How many coins to send")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        sender = interaction.user

        if amount <= 0:
            await interaction.response.send_message("Amount must be positive.", ephemeral=True)
            return
        if member.id == sender.id:
            await interaction.response.send_message("You can't send coins to yourself. Are you really that broke?", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("You can't send coins to a bot. They don't need it.", ephemeral=True)
            return

        sender_balance = await db.get_balance(sender.id, interaction.guild.id)
        if sender_balance < amount:
            await interaction.response.send_message(
                f"You don't have enough coins, broke boy. Your balance: **{sender_balance}**", ephemeral=True
            )
            return

        await db.update_balance(sender.id, interaction.guild.id, -amount)
        await db.update_balance(member.id, interaction.guild.id, amount)

        await interaction.response.send_message(
            f"{sender.mention} sent **{amount}** coins to {member.mention}"
        )

    @app_commands.command(name="leaderboard", description="See who has the most bands in this server")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await db.get_leaderboard(interaction.guild.id, order_by="balance")

        if not rows:
            await interaction.response.send_message("No one has any money yet.")
            return

        lines = []
        for i, (user_id, balance) in enumerate(rows, start=1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown user ({user_id})"
            lines.append(f"**{i}.** {name} — {balance} coins")

        embed = discord.Embed(title="💰 Most Bands", description="\n".join(lines), color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
