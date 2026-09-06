import time
import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import (DAILY_REWARD, DAILY_COOLDOWN_SECONDS, WORK_MIN_REWARD, WORK_MAX_REWARD,
                    WORK_COOLDOWN_SECONDS, GIG_COOLDOWN_SECONDS, GIG_MIN_REWARD,
                    GIG_MAX_REWARD, GIG_XP)
from cogs.quests import record_event
from cogs.housing import pay_with_boost, house_cut
from cogs.leveling import apply_level_up
# Re-exported: cogs/heist.py has always imported format_seconds from here, and
# it stays importable from here even though the body moved to ui.py.
from ui import format_seconds

JOBS = [
    "delivery driver", "street musician", "dog walker", "barista",
    "freelance coder", "mechanic", "chef", "taxi driver",
]

# A gig is a week's work, so it gets a story rather than a job title. One of
# these is rolled per claim - the payout is identical either way, this is only
# so claiming it seven days running doesn't read like the same button twice.
GIGS = [
    "ran security for a warehouse nobody wanted to talk about",
    "drove a van across three states and asked zero questions",
    "did a week of night shifts at the docks",
    "fixed every machine in a laundromat that was definitely not a laundromat",
    "sat in a parked car for six days watching a door",
    "moved furniture for a man who had no furniture",
    "worked the door at a club that opened at 4am",
    "counted inventory in a warehouse with no inventory",
]


async def claim_gig(user_id: int, guild_id: int):
    """The weekly payout. Returns (paid, message).

    Split out of the command so the seven-day cooldown can be tested without a
    Discord interaction - same shape as housing.collect_rent. Pays through
    pay_with_boost, so a house lifts the gig exactly like it lifts /work.
    """
    last_gig = await db.get_cooldown(user_id, guild_id, "last_gig")
    elapsed = time.time() - last_gig

    if elapsed < GIG_COOLDOWN_SECONDS:
        remaining = GIG_COOLDOWN_SECONDS - elapsed
        return False, (f"You've already done your gig this week. "
                       f"Next one in **{format_seconds(remaining)}**.")

    earnings = random.randint(GIG_MIN_REWARD, GIG_MAX_REWARD)
    gig = random.choice(GIGS)
    base, bonus, new_balance = await pay_with_boost(user_id, guild_id, earnings)
    xp, level = await db.add_xp(user_id, guild_id, GIG_XP)
    await apply_level_up(user_id, guild_id, xp, level)
    # Stamped only after the payout lands, so a failure can't burn the week.
    await db.set_cooldown(user_id, guild_id, "last_gig")
    return True, (f"You {gig} and cleared **{base}** coins{house_cut(bonus)}. "
                  f"New balance: **{new_balance}**")


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

        base, bonus, new_balance = await pay_with_boost(user_id, guild_id, DAILY_REWARD)
        await db.set_cooldown(user_id, guild_id, "last_daily")
        await interaction.response.send_message(
            f"You claimed your daily reward of **{base}** coins{house_cut(bonus)}. "
            f"New balance: **{new_balance}**"
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
        base, bonus, new_balance = await pay_with_boost(user_id, guild_id, earnings)
        await db.set_cooldown(user_id, guild_id, "last_work")
        # Counted after the cooldown check, so only real shifts count.
        await record_event(user_id, guild_id, "work_count", 1)
        await interaction.response.send_message(
            f"You worked as a **{job}** and earned **{base}** coins{house_cut(bonus)}. "
            f"New balance: **{new_balance}**"
        )

    @app_commands.command(name="gig", description="Take a week-long job. One per week, pays properly.")
    async def gig(self, interaction: discord.Interaction):
        paid, message = await claim_gig(interaction.user.id, interaction.guild.id)
        if not paid:
            await interaction.response.send_message(message, ephemeral=True)
            return
        await interaction.response.send_message(message)

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
