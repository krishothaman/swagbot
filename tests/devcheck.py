import asyncio, inspect, os, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import discord
from discord import app_commands
print("discord.py", discord.__version__)

# 1. Does Group accept the kwargs we pass?
params = inspect.signature(app_commands.Group.__init__).parameters
for k in ("guild_only", "default_permissions"):
    print(f"Group supports {k}:", k in params)

# 2. Does the Cog error hook name exist?
from discord.ext import commands
print("cog_app_command_error is a real hook:", hasattr(commands.Cog, "cog_app_command_error"))

import database as db
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
import config
import cogs.dev as dev

# 3. Commands actually registered under the group
names = sorted(c.name for c in dev.Dev.dev.commands)
print("dev commands:", names)

# 4. Every one of them must carry the owner check
missing = [c.name for c in dev.Dev.dev.commands if not c.checks]
print("commands MISSING owner check:", missing or "none")


class FakeUser:
    def __init__(self, uid): self.id = uid
    def __str__(self): return f"user{self.id}"

class FakeClient:
    def __init__(self, owner): self._owner = owner
    async def is_owner(self, user): return user.id == self._owner

class FakeBoom:
    async def is_owner(self, user): raise RuntimeError("discord api down")

class FakeInteraction:
    def __init__(self, uid, client): self.user, self.client = FakeUser(uid), client


async def main():
    # OWNER_ID configured -> only that exact id passes
    dev.OWNER_ID = 111
    print("owner passes:", await dev.is_owner(FakeInteraction(111, FakeClient(999))))
    print("stranger denied:", not await dev.is_owner(FakeInteraction(222, FakeClient(999))))
    # even the real app owner is denied when OWNER_ID names someone else
    print("app-owner denied when OWNER_ID set:", not await dev.is_owner(FakeInteraction(999, FakeClient(999))))

    # OWNER_ID unset -> fall back to application owner
    dev.OWNER_ID = None
    print("fallback owner passes:", await dev.is_owner(FakeInteraction(999, FakeClient(999))))
    print("fallback stranger denied:", not await dev.is_owner(FakeInteraction(222, FakeClient(999))))
    # errors must deny, never grant
    print("fails closed on exception:", not await dev.is_owner(FakeInteraction(999, FakeBoom())))

asyncio.run(main())
