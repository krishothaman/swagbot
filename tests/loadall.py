import asyncio, os, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import database as db
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")

import discord
from discord.ext import commands
from bot import COGS


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    for cog in COGS:
        await bot.load_extension(cog)
        print("loaded", cog)

    print("top-level:", sorted(c.name for c in bot.tree.get_commands()))

asyncio.run(main())
