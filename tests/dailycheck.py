"""The infinite-daily exploit, as a regression test.

daily_hustle pays 250 coins + 75 XP for "have 500 coins". Nothing is spent, so
before the fix you could turn it in and immediately re-accept, forever.
This must FAIL against the old code.
"""
import asyncio, os, sys, tempfile, time
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import config
config.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
import database as db
db.DB_PATH = config.DB_PATH

USER, GUILD = 31, 1
DAY = 86400


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_quest_data()
    await db.ensure_user(USER, GUILD)

    from cogs.quests import accept_quest, turn_in_quest
    import daily_reset

    # give them enough to satisfy "have 500 coins" outright
    await db.update_balance(USER, GUILD, 1000)

    print("=== the loop: turn in, re-accept, turn in again ===")
    start = await db.get_balance(USER, GUILD)
    print(f"  starting balance: {start}")

    print(f"  accept : {await accept_quest(USER, GUILD, 'daily_hustle')}")
    print(f"  turn in: {await turn_in_quest(USER, GUILD, 'daily_hustle')}")
    after_one = await db.get_balance(USER, GUILD)
    print(f"  balance: {after_one}")

    second = await accept_quest(USER, GUILD, 'daily_hustle')
    print(f"  re-accept immediately: {second}")

    # THE ASSERTION: the second accept must be refused
    ok = await db.get_player_quest_status(USER, GUILD, 'daily_hustle')
    assert ok != "active", (
        "EXPLOIT LIVE: daily_hustle was re-accepted immediately after turn-in"
    )
    print("  -> refused, as it should be")

    print("\n=== hammer it: 20 accept/turn-in cycles back to back ===")
    before = await db.get_balance(USER, GUILD)
    for _ in range(20):
        await accept_quest(USER, GUILD, 'daily_hustle')
        await turn_in_quest(USER, GUILD, 'daily_hustle')
    gained = await db.get_balance(USER, GUILD) - before
    print(f"  gained over 20 attempted loops: {gained} coins")
    assert gained == 0, f"EXPLOIT LIVE: farmed {gained} coins with no reset"

    print("\n=== daily_stash: same shape, keeps the lockpicks ===")
    await db.add_item_to_inventory(USER, GUILD, "lockpick", 2)
    await accept_quest(USER, GUILD, 'daily_stash')
    await turn_in_quest(USER, GUILD, 'daily_stash')
    before = await db.get_balance(USER, GUILD)
    for _ in range(10):
        await accept_quest(USER, GUILD, 'daily_stash')
        await turn_in_quest(USER, GUILD, 'daily_stash')
    gained = await db.get_balance(USER, GUILD) - before
    print(f"  gained over 10 attempted loops: {gained} coins")
    assert gained == 0, f"EXPLOIT LIVE: farmed {gained} coins on daily_stash"

    print("\n=== after the reset boundary it comes back ===")
    now = time.time()
    tomorrow = daily_reset.last_reset(now) + DAY + 60
    assert daily_reset.is_available(now, now=tomorrow), \
        "quest completed today is still locked after the next midnight UTC"
    assert not daily_reset.is_available(now, now=now), \
        "quest completed just now reads as available"
    assert daily_reset.is_available(None, now=now), \
        "a never-completed quest must be available"
    print("  boundary math correct (locked now, open after next midnight UTC)")

    print("\n=== counter dailies still reset their progress ===")
    await db.set_player_quest_status(USER, GUILD, 'daily_gamble', 'active')
    await db.add_quest_progress(USER, GUILD, 'gamble_coins', 60)
    assert await db.get_quest_progress(USER, GUILD, 'daily_gamble') == 60
    await db.set_player_quest_status(USER, GUILD, 'daily_gamble', 'active')
    p = await db.get_quest_progress(USER, GUILD, 'daily_gamble')
    assert p == 0, f"progress carried over: {p}"
    print("  daily_gamble progress resets to 0 on re-accept")

    await db.get_db().close()
    print("\nDAILY RESET CHECKS PASSED")

asyncio.run(main())
