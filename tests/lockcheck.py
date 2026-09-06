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
import bot as botmod
from config import SHOT_BLOCKED_COMMANDS

U, G = 1, 2


class FakeResponse:
    def __init__(self): self.sent = None
    async def send_message(self, content, **kw): self.sent = content


class FakeInteraction:
    def __init__(self, command):
        self.user = type("U", (), {"id": U})()
        self.guild = type("G", (), {"id": G})()
        self.guild_id = G
        self.command = command
        self.response = FakeResponse()


async def main():
    await db.init_db()
    await db.seed_npc_data(); await db.seed_house_data(); await db.seed_quest_data()
    for cog in botmod.COGS:
        await botmod.bot.load_extension(cog)

    print("tree class:", type(botmod.bot.tree).__name__)
    assert isinstance(botmod.bot.tree, botmod.SwagTree), "custom tree not installed!"

    tree = botmod.bot.tree
    # Collect real command objects, including subcommands of groups.
    cmds = {}
    for c in tree.get_commands():
        if isinstance(c, discord.app_commands.Group):
            for sub in c.commands:
                cmds[f"{c.name} {sub.name}"] = sub
        else:
            cmds[c.name] = c

    await db.ensure_user(U, G)

    print("\n--- not shot: everything must pass ---")
    for name, cmd in sorted(cmds.items()):
        ok = await tree.interaction_check(FakeInteraction(cmd))
        assert ok, f"{name} blocked while healthy!"
    print(f"all {len(cmds)} commands allowed when healthy: OK")

    print("\n--- shot: blocklist must apply, and only it ---")
    await db.set_incapacitated(U, G, 600)
    blocked, allowed = [], []
    for name, cmd in sorted(cmds.items()):
        it = FakeInteraction(cmd)
        ok = await tree.interaction_check(it)
        (allowed if ok else blocked).append(name)
        if not ok:
            assert "bleeding out" in it.response.sent, "blocked with no explanation"

    print("BLOCKED:", blocked)
    print("ALLOWED:", allowed)

    # every blocked root must be in the configured set, and vice versa
    blocked_roots = {n.split()[0] for n in blocked}
    assert blocked_roots == SHOT_BLOCKED_COMMANDS, (
        f"mismatch: blocked={blocked_roots} configured={SHOT_BLOCKED_COMMANDS}"
    )
    # subcommands of an allowed group must stay allowed
    assert any(n.startswith("house ") for n in allowed), "house subcommands wrongly blocked"
    assert any(n.startswith("dev ") for n in allowed), "dev subcommands wrongly blocked"

    print("\n--- after clearing ---")
    await db.clear_incapacitated(U, G)
    for name, cmd in sorted(cmds.items()):
        assert await tree.interaction_check(FakeInteraction(cmd)), f"{name} still blocked"
    print("all commands allowed again: OK")

    print("\nLOCKOUT GATE CHECKS PASSED")

asyncio.run(main())
