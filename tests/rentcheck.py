"""/house collect: does rent accrue, cap, carry over the partial day, and reset
when the house changes hands?

Uses a throwaway db so your real data/bot.db is never touched. Time travel is
done by writing the ledger stamp backwards rather than mocking the clock.
"""
import asyncio, os, sys, tempfile, time
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

tmp_dir = tempfile.mkdtemp()
tmp = os.path.join(tmp_dir, "test.db")
import config
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp
import house_perks as P

DAY = P.SECONDS_PER_DAY
USER, GUILD = 1, 1


async def rewind(days: float):
    """Pretend the last collection happened `days` ago."""
    d = db.get_db()
    await d.execute(
        "UPDATE player_houses SET last_collect_at = ? WHERE user_id = ? AND guild_id = ?",
        (time.time() - days * DAY, USER, GUILD),
    )
    await d.commit()


async def collect_and_measure(housing):
    before = await db.get_balance(USER, GUILD)
    message = await housing.collect_rent(USER, GUILD)
    after = await db.get_balance(USER, GUILD)
    return after - before, message


async def main():
    await db.init_db()
    await db.seed_house_data()
    import cogs.housing as housing

    print("=== every seeded house has perks (a typo'd key = a dead tier) ===")
    seeded = {h[0] for h in await db.get_houses()}
    print(f"  seeded  : {sorted(seeded)}")
    print(f"  perks   : {sorted(P.HOUSE_PERKS)}")
    assert seeded == set(P.HOUSE_PERKS), \
        f"house catalog and perk table disagree: {seeded ^ set(P.HOUSE_PERKS)}"

    await db.ensure_user(USER, GUILD)
    await db.set_balance(USER, GUILD, 0)

    print("\n=== no house, no rent ===")
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 0, "collected rent without owning anything"

    print("\n=== buying stamps the ledger, so day one pays nothing ===")
    await db.set_player_house(USER, GUILD, "studio")
    stamp = await db.get_house_rent_stamp(USER, GUILD)
    assert stamp > 0, "buying a house left the ledger unstamped"
    assert abs(stamp - time.time()) < 5, "purchase stamp is not ~now"
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 0, "a house paid rent the moment it was bought"

    print("\n=== three days in a studio pays 3 x 50 ===")
    await rewind(3)
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 150, f"expected 150, got {gained}"

    print("\n=== collecting twice in a row pays nothing the second time ===")
    gained, _ = await collect_and_measure(housing)
    print(f"  {gained:+} coins")
    assert gained == 0, "double collect paid twice"

    print("\n=== the partial day carries over instead of being forfeited ===")
    # 3.5 days owed pays 3. The leftover half-day must survive the collection,
    # so half a day later you're owed one more - not one and a half days later.
    await rewind(3.5)
    gained, _ = await collect_and_measure(housing)
    assert gained == 150, f"expected 150 for 3.5 days, got {gained}"
    stamp = await db.get_house_rent_stamp(USER, GUILD)
    leftover = time.time() - stamp
    print(f"  paid 3 days, {leftover / DAY:.2f} days left on the clock")
    assert 0.4 * DAY < leftover < 0.6 * DAY, \
        f"the half day was thrown away (only {leftover / DAY:.2f} days carried)"

    print("\n=== a month away still only pays the 7 day cap ===")
    await rewind(30)
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 50 * P.RENT_CAP_DAYS, f"expected {50 * P.RENT_CAP_DAYS}, got {gained}"

    # ...and the 23 uncapped days must NOT still be sitting on the clock.
    gained, _ = await collect_and_measure(housing)
    print(f"  immediately after: {gained:+} coins")
    assert gained == 0, "the capped-off days were still collectable"

    print("\n=== upgrading pays the new tier's rate ===")
    await db.set_player_house(USER, GUILD, "mansion", is_upgrade=True)
    await rewind(2)
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 1500 * 2, f"expected 3000, got {gained}"

    print("\n=== selling and rebuying does not hand you a backlog ===")
    await rewind(7)
    await db.remove_player_house(USER, GUILD)
    await db.set_player_house(USER, GUILD, "studio")
    gained, _ = await collect_and_measure(housing)
    print(f"  {gained:+} coins after a fresh purchase")
    assert gained == 0, "rebuying collected rent for a house you didn't own"

    print("\n=== a house bought before this feature existed starts from now ===")
    # Their ledger is 0, the column default. Reading that literally is ~54
    # years of elapsed rent; it must stamp instead of paying.
    d = db.get_db()
    await d.execute(
        "UPDATE player_houses SET last_collect_at = 0 WHERE user_id = ? AND guild_id = ?",
        (USER, GUILD),
    )
    await d.commit()
    gained, message = await collect_and_measure(housing)
    print(f"  {gained:+} coins - {message}")
    assert gained == 0, "an unstamped ledger paid out free rent"
    stamp = await db.get_house_rent_stamp(USER, GUILD)
    assert stamp > 0, "collecting on an unstamped ledger left it unstamped"
    print(f"  ledger now stamped: {stamp > 0}")

    await db.get_db().close()
    print("\nrentcheck OK")


async def migration_check():
    """An existing database predates last_collect_at. init_db must add it in
    place without dropping anyone's house."""
    print("\n=== migrating a database that predates the rent ledger ===")
    import aiosqlite
    old = os.path.join(tempfile.mkdtemp(), "old.db")
    conn = await aiosqlite.connect(old)
    await conn.execute("""
        CREATE TABLE player_houses (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            house_id TEXT NOT NULL,
            purchased_at REAL NOT NULL,
            upgraded_at REAL,
            PRIMARY KEY (user_id, guild_id)
        )
    """)
    await conn.execute(
        "INSERT INTO player_houses VALUES (?, ?, 'mansion', ?, NULL)",
        (7, 7, time.time()),
    )
    await conn.commit()
    await conn.close()

    config.DB_PATH = old
    db.DB_PATH = old
    await db.init_db()
    await db.seed_house_data()

    d = db.get_db()
    async with d.execute("PRAGMA table_info(player_houses)") as c:
        columns = {row[1] for row in await c.fetchall()}
    print(f"  columns after migration: {sorted(columns)}")
    assert "last_collect_at" in columns, "migration did not add last_collect_at"

    house = await db.get_player_house(7, 7)
    assert house is not None and house[0] == "mansion", "migration dropped the house"
    print(f"  the existing tenant kept their {house[1]}")
    assert await db.get_house_rent_stamp(7, 7) == 0, \
        "migration invented a stamp instead of defaulting to 0"

    await db.get_db().close()
    print("\nmigration OK")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(migration_check())
