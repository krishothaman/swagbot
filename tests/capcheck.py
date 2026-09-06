import asyncio, os, sqlite3, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import database as db
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")

from cogs.quests import accept_quest, build_quest_embed
from config import MAX_ACTIVE_QUESTS

U, G = 77, 2


async def main():
    await db.init_db()
    await db.seed_npc_data(); await db.seed_house_data(); await db.seed_quest_data()
    await db.ensure_user(U, G)

    # Fresh user: accept quests until we hit the cap, using only untouched quests.
    all_ids = [q["quest_id"] for q in await db.get_quests_by_category("npc")]
    all_ids += [q["quest_id"] for q in await db.get_quests_by_category("daily")]
    print("available quest ids:", all_ids)

    accepted = 0
    for qid in all_ids:
        msg = await accept_quest(U, G, qid)
        ok = msg.startswith("Accepted")
        print(f"  accept {qid}: {'OK' if ok else msg}")
        if ok:
            accepted += 1

    active = await db.count_active_quests(U, G)
    print(f"\naccepted={accepted} active={active} cap={MAX_ACTIVE_QUESTS}")
    assert active == MAX_ACTIVE_QUESTS, f"expected cap {MAX_ACTIVE_QUESTS}, got {active}"
    assert accepted == MAX_ACTIVE_QUESTS, "accepted more than the cap allows"

    # The next one must be refused *because of the cap*, not for another reason.
    remaining = [q for q in all_ids
                 if await db.get_player_quest_status(U, G, q) == "available"]
    assert remaining, "test needs at least one untouched quest left over"
    msg = await accept_quest(U, G, remaining[0])
    print("refusal message:", msg)
    assert "juggling too much" in msg, f"cap not enforced, got: {msg}"

    embed = await build_quest_embed(U, G)
    print("\nembed renders:", [f.name for f in embed.fields])

    print("\nCAP ENFORCED CORRECTLY")

asyncio.run(main())
