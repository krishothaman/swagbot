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

from cogs.quests import accept_quest, turn_in_quest, check_progress, record_event

U, G = 9, 2
QID = "first_errand"


async def main():
    await db.init_db()
    await db.seed_npc_data(); await db.seed_house_data(); await db.seed_quest_data()
    await db.ensure_user(U, G)

    q = await db.get_quest(QID)
    print("quest:", q["title"], "|", q["condition_type"], q["condition_amount"], "| npc:", q["npc_id"])
    assert q["condition_type"] == "work_count"

    # the old lockpick quest must be gone
    assert q["condition_type"] != "deliver_item", "still the old lockpick quest"

    # working before accepting shouldn't count
    await record_event(U, G, "work_count", 1)
    print("\naccept:", await accept_quest(U, G, QID))
    cur, req, done = await check_progress(U, G, q)
    print("after accept:", cur, "/", req)
    assert cur == 0, "pre-accept work leaked in"

    bal = await db.get_balance(U, G)
    for i in range(1, 4):
        await record_event(U, G, "work_count", 1)
        cur, req, done = await check_progress(U, G, q)
        print(f"  after work #{i}: {cur}/{req} complete={done}")
        if i < 3:
            msg = await turn_in_quest(U, G, QID)
            assert "Not done" in msg, f"paid out early at {cur}/{req}"
            assert await db.get_balance(U, G) == bal, "balance moved early"

    print("\nturn in:", await turn_in_quest(U, G, QID))
    assert await db.get_balance(U, G) == bal + 300

    # --- pruning: simulate removing a quest from quest_data.py ---
    print("\n--- prune test ---")
    all_before = {r["quest_id"] for r in await db.get_quests_by_category("daily")}
    print("daily quests before:", sorted(all_before))

    import quest_data
    removed = "daily_gamble"
    kept = [x for x in quest_data.QUESTS if x["quest_id"] != removed]
    # give the player an active row on the quest we're about to remove
    await accept_quest(U, G, removed)
    assert await db.get_player_quest_status(U, G, removed) == "active"

    quest_data.QUESTS = kept
    await db.seed_quest_data()

    gone = await db.get_quest(removed)
    print(f"'{removed}' after removal from file:", gone)
    assert gone is None, "removed quest still in DB"
    status = await db.get_player_quest_status(U, G, removed)
    print("orphaned player row status:", status)
    assert status == "available", "orphaned player_quests row not cleaned up"

    print("\nWORK QUEST + PRUNE CHECKS PASSED")

asyncio.run(main())
