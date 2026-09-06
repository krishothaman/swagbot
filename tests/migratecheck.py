import asyncio, os, sqlite3, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import database as db
path = os.path.join(tempfile.mkdtemp(), "old.db")
db.DB_PATH = path

# Build a database in the OLD shape, with a real player in it.
conn = sqlite3.connect(path)
conn.execute("""CREATE TABLE users (
    user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0, xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0, last_daily REAL NOT NULL DEFAULT 0,
    last_work REAL NOT NULL DEFAULT 0, last_message_xp REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id))""")
conn.execute("INSERT INTO users (user_id,guild_id,balance,xp,level) VALUES (1,2,73456,900,12)")
conn.commit(); conn.close()
print("pre-migration columns:", [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(users)")])


async def main():
    await db.init_db()
    cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(users)")]
    print("post-migration columns:", cols)
    assert "last_heist" in cols and "incapacitated_until" in cols

    # The whole point: existing money must survive.
    bal = await db.get_balance(1, 2)
    xp, lvl = await db.get_xp_and_level(1, 2)
    print(f"preserved: balance={bal} xp={xp} level={lvl}")
    assert bal == 73456 and xp == 900 and lvl == 12, "MIGRATION DESTROYED PLAYER DATA"

    # lockout round-trip
    assert await db.get_incapacitated_remaining(1, 2) == 0
    await db.set_incapacitated(1, 2, 600)
    rem = await db.get_incapacitated_remaining(1, 2)
    print("remaining after set(600s):", round(rem))
    assert 595 < rem <= 600
    await db.clear_incapacitated(1, 2)
    assert await db.get_incapacitated_remaining(1, 2) == 0
    print("lockout set/clear: OK")

    # unknown user must not be considered locked
    assert await db.get_incapacitated_remaining(999, 2) == 0
    print("unknown user not locked: OK")

    # running init again must be a no-op, not a wipe
    await db.init_db()
    assert await db.get_balance(1, 2) == 73456, "second init wiped data"
    print("re-running init is idempotent: OK")

    print("\nMIGRATION CHECKS PASSED")

asyncio.run(main())
