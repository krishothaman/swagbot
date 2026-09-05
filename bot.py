import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import DISCORD_TOKEN, COMMAND_PREFIX, SHOT_BLOCKED_COMMANDS
from database import (init_db, seed_npc_data, seed_item_data, seed_house_data,
                      seed_quest_data)
import database as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True  # needed for leveling's on_message XP tracking
intents.members = True          # needed to resolve users for leaderboard etc.

def format_remaining(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"


class SwagTree(app_commands.CommandTree):
    """Gates every slash command behind the "are you shot" check.

    Doing this once here is deliberate - adding a guard per command means
    forgetting one eventually, and a punishment mechanic you can walk around
    isn't a punishment.
    """

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.command is None:
            return True

        # Only the top-level name matters, so /house buy is covered by "house".
        command = interaction.command
        root = command.root_parent.name if getattr(command, "root_parent", None) else command.name
        if root not in SHOT_BLOCKED_COMMANDS:
            return True

        remaining = await db.get_incapacitated_remaining(interaction.user.id, interaction.guild.id)
        if remaining <= 0:
            return True

        await interaction.response.send_message(
            f"🩸 You're bleeding out in a back room. Back on your feet in "
            f"**{format_remaining(remaining)}**.",
            ephemeral=True,
        )
        return False


bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, tree_cls=SwagTree)

COGS = [
    "cogs.economy",
    "cogs.blackjack",
    "cogs.games",
    "cogs.leveling",
    "cogs.npc",
    "cogs.housing",
    "cogs.quests",
    "cogs.heist",
    "cogs.dev"
]


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        log.error(f"Failed to sync slash commands: {e}")


async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            log.info(f"Loaded cog: {cog}")
        except Exception as e:
            log.error(f"Failed to load cog {cog}: {e}")


async def main():
    await init_db()
    await seed_npc_data()
    await seed_item_data()   # after NPCs: items reference them
    await seed_house_data()
    await seed_quest_data()
    await load_cogs()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN not found. Create a .env file with:\n"
            "DISCORD_TOKEN=your_token_here"
        )
    asyncio.run(main())
