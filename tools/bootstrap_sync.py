"""One-off: logs in, loads the same cogs as bot.py (so the tree is populated),
copies the global command set into every guild the bot is already in (instant
per-guild sync instead of waiting on Discord's global cache), then exits.
Doesn't touch the already-running bot process - this is a separate, short-lived
connection that closes itself as soon as the sync is done.
"""

import asyncio
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord.ext import commands

from config import DISCORD_TOKEN
from database import init_db, seed_npc_data, seed_house_data
from bot import COGS

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guilds = bot.guilds
    if not guilds:
        print("Bot isn't in any servers - nothing to sync to.")
    for guild in guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) to '{guild.name}' ({guild.id}): "
              f"{sorted(c.name for c in synced)}")
    await bot.close()


async def main():
    await init_db()
    await seed_npc_data()
    await seed_house_data()
    for cog in COGS:
        await bot.load_extension(cog)
    async with bot:
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())
