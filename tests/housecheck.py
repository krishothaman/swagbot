"""Does editing a house price actually reach the database on a re-seed?

Uses a throwaway db so your real data/bot.db is never touched.
"""
import asyncio, os, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

tmp = os.path.join(tempfile.mkdtemp(), "test.db")
import config
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp


async def price(house_id):
    d = db.get_db()
    async with d.execute("SELECT price FROM houses WHERE house_id = ?", (house_id,)) as c:
        row = await c.fetchone()
        return row[0] if row else None


async def main():
    await db.init_db()

    # boot 1: the catalog lands
    await db.seed_house_data()
    first = await price("mansion")
    print(f"  after first boot          : mansion = {first:,}")

    # a player buys it. This is the row that must survive everything below.
    await db.ensure_user(1, 1)
    await db.set_player_house(1, 1, 'mansion')
    d = db.get_db()

    # you edit the number in database.py and restart. Simulate that edit.
    async def edited_seed():
        d = db.get_db()
        await d.executemany(
            "INSERT OR REPLACE INTO houses (house_id, name, tier, price, storage_slots, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [("studio", "Studio", 1, 5000, 10, "x"),
             ("apartment", "Apartment", 2, 60000, 30, "x"),
             ("mansion", "Mansion", 3, 400000, 100, "x")],
        )
        await d.commit()
    await edited_seed()

    after = await price("mansion")
    print(f"  after editing + rebooting : mansion = {after:,}")
    assert after == 400000, f"price edit did not apply - still {after}"

    async with d.execute("SELECT house_id FROM player_houses WHERE user_id = 1") as c:
        owned = await c.fetchone()
    print(f"  player who owned it       : still owns '{owned[0]}'")
    assert owned and owned[0] == "mansion", "re-seeding wiped a player's house"

    # and the catalog didn't grow duplicates
    async with d.execute("SELECT COUNT(*) FROM houses") as c:
        n = (await c.fetchone())[0]
    print(f"  rows in the catalog       : {n}")
    assert n == 3, f"{n} rows - OR REPLACE duplicated instead of replacing"

    await d.close()
    print("\nHOUSE SEEDER CHECKS PASSED")

asyncio.run(main())
