import time
import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX, XP_MESSAGE_COOLDOWN_SECONDS


def xp_needed_for_level(level: int) -> int:
    return 3 * (level ** 2) + 25 * level + 75


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        user_id, guild_id = message.author.id, message.guild.id
        last_xp_time = await db.get_cooldown(user_id, guild_id, "last_message_xp")

        if time.time() - last_xp_time < XP_MESSAGE_COOLDOWN_SECONDS:
            return

        amount = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        xp, level = await db.add_xp(user_id, guild_id, amount)
        await db.set_cooldown(user_id, guild_id, "last_message_xp")

        needed = xp_needed_for_level(level)
        if xp >= needed:
            new_level = level + 1
            await db.set_level(user_id, guild_id, new_level)
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} leveled up to **level {new_level}**!"
                )
            except discord.HTTPException:
                pass

    @app_commands.command(name="rank", description="Check your (or someone else's) level and XP")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user

        xp, level = await db.get_xp_and_level(member.id, interaction.guild.id)
        needed = xp_needed_for_level(level)

        embed = discord.Embed(title=f"{member.display_name}'s Rank", color=discord.Color.green())
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{needed}", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rank_leaderboard", description="See the highest-level users in this server")
    async def rank_leaderboard(self, interaction: discord.Interaction):
        rows = await db.get_leaderboard(interaction.guild.id, order_by="xp")

        if not rows:
            await interaction.response.send_message("No one has earned any XP yet.")
            return

        lines = []
        for i, (user_id, xp) in enumerate(rows, start=1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown user ({user_id})"
            lines.append(f"**{i}.** {name} — {xp} XP")

        embed = discord.Embed(title="⭐ Top XP", description="\n".join(lines), color=discord.Color.green())
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
