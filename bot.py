import asyncio
import logging

import discord

from discord.ext import commands

from config import DISCORD_TOKEN, COMMAND_PREFIX
from database import init_db, seed_npc_data

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True  # needed for leveling's on_message XP tracking
intents.members = True          # needed to resolve users for leaderboard etc.

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

COGS = [
    "cogs.economy",
    "cogs.blackjack",
    "cogs.games",
    "cogs.leveling",
    "cogs.npc"
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
