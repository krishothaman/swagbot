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

from cogs.leveling import apply_level_up, xp_needed_for_level

U, G = 1, 2


async def main():
    await db.init_db()

    # Old bug: dumping a huge amount of XP via add_xp alone never changed level.
    xp, level = await db.add_xp(U, G, 100000)
    print("after raw add_xp: xp =", xp, "level (stale) =", level)
    assert level == 0, "sanity: level shouldn't move without apply_level_up"

    # New path: what /dev addxp now does.
    new_level = await apply_level_up(U, G, xp, level)
    print("after apply_level_up: new_level =", new_level)
    assert new_level > 0, "BUG STILL PRESENT: level did not increase"

    stored_xp, stored_level = await db.get_xp_and_level(U, G)
    print("persisted in db:", stored_xp, stored_level)
    assert stored_level == new_level, "level wasn't actually persisted"

    # Verify it's the correct level per the formula (not off by one, not stuck at +1)
    expected = 0
    while xp >= xp_needed_for_level(expected):
        expected += 1
    print("expected level:", expected)
    assert stored_level == expected, f"wrong level: got {stored_level}, expected {expected}"

    # Small xp addition that does NOT cross a threshold - level must not change
    xp2, level2 = await db.add_xp(U, G, 1)
    same_level = await apply_level_up(U, G, xp2, level2)
    print("tiny xp add -> level stays:", same_level == level2)
    assert same_level == level2

    print("ALL CHECKS PASSED")

asyncio.run(main())
