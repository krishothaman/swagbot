import time
import random
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX, XP_MESSAGE_COOLDOWN_SECONDS


def xp_needed_for_level(level: int) -> int:
    """Design decision left to you: how much XP should each level require?
    A common simple formula is: 5 * (level ** 2) + 50 * level + 100
    TODO (Czar): pick/tweak a formula you like. Just make sure it's an
    increasing function of `level` so higher levels take longer."""
    return 5 * (level ** 2) + 50 * level + 100


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # TODO (Czar):
        # 1. Ignore bot messages: if message.author.bot: return
        # 2. Ignore DMs: if message.guild is None: return
        # 3. Cooldown check using db.get_cooldown(..., "last_message_xp") vs
        #    XP_MESSAGE_COOLDOWN_SECONDS, same pattern as economy's /daily
        # 4. If off cooldown:
        #      amount = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        #      xp, level = await db.add_xp(message.author.id, message.guild.id, amount)
        #      await db.set_cooldown(message.author.id, message.guild.id, "last_message_xp")
        # 5. Check for level-up: if xp >= xp_needed_for_level(level):
        #      new_level = level + 1
        #      await db.set_level(message.author.id, message.guild.id, new_level)
        #      -> send a level-up announcement in the channel
        #    Think about: should XP reset to 0 on level-up, or keep accumulating
        #    total XP forever? Either is a valid design - just be consistent.
        pass

    @app_commands.command(name="rank", description="Check your (or someone else's) level and XP")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        # TODO (Czar):
        # 1. Default member to interaction.user if None
        # 2. xp, level = await db.get_xp_and_level(member.id, interaction.guild.id)
        # 3. needed = xp_needed_for_level(level)
        # 4. Respond showing level, current xp / needed xp (e.g. "Level 3 - 120/250 XP")
        pass

    @app_commands.command(name="rank_leaderboard", description="See the highest-level users in this server")
    async def rank_leaderboard(self, interaction: discord.Interaction):
        # TODO (Czar): same pattern as economy's /leaderboard, but
        # db.get_leaderboard(interaction.guild.id, order_by="xp")
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
