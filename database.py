"""
Shared database layer.

Design decision: economy balance and leveling XP live in the SAME `users`
table (one row per user PER SERVER, since balances/levels shouldn't
carry across servers). Every cog imports functions from here instead of
touching sqlite directly - keeps the "does this user exist yet" logic
in one place.
"""

import aiosqlite
import time
from config import DB_PATH, STARTING_BALANCE

_db: aiosqlite.Connection | None = None


async def init_db():
    """Call once on bot startup. Creates tables if they don't exist."""
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            balance INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            last_daily REAL NOT NULL DEFAULT 0,
            last_work REAL NOT NULL DEFAULT 0,
            last_message_xp REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )
    """)
    await _db.commit()


def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized - call init_db() first")
    return _db


async def ensure_user(user_id: int, guild_id: int):
    """Insert a row for this user in this guild if one doesn't exist yet.
    Call this at the top of any command that reads/writes user data."""
    db = get_db()
    await db.execute(
        """INSERT OR IGNORE INTO users (user_id, guild_id, balance)
           VALUES (?, ?, ?)""",
        (user_id, guild_id, STARTING_BALANCE),
    )
    await db.commit()


async def get_balance(user_id: int, guild_id: int) -> int:
    await ensure_user(user_id, guild_id)
    db = get_db()
    async with db.execute(
        "SELECT balance FROM users WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def update_balance(user_id: int, guild_id: int, amount: int):
    """Adds `amount` to balance. Pass a negative number to subtract.
    Returns the new balance."""
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?",
        (amount, user_id, guild_id),
    )
    await db.commit()
    return await get_balance(user_id, guild_id)


async def get_cooldown(user_id: int, guild_id: int, field: str) -> float:
    """field must be one of: last_daily, last_work, last_message_xp
    Returns unix timestamp of last use (0 if never used)."""
    await ensure_user(user_id, guild_id)
    db = get_db()
    async with db.execute(
        f"SELECT {field} FROM users WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def set_cooldown(user_id: int, guild_id: int, field: str):
    """Stamps `field` with the current time. field must be one of:
    last_daily, last_work, last_message_xp"""
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        f"UPDATE users SET {field} = ? WHERE user_id = ? AND guild_id = ?",
        (time.time(), user_id, guild_id),
    )
    await db.commit()


async def get_xp_and_level(user_id: int, guild_id: int) -> tuple[int, int]:
    await ensure_user(user_id, guild_id)
    db = get_db()
    async with db.execute(
        "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else (0, 0)


async def add_xp(user_id: int, guild_id: int, amount: int):
    """Adds XP. Does NOT handle level-up logic - that's a design decision
    for you to make in cogs/leveling.py (e.g. what formula decides how much
    XP is needed per level). Returns new (xp, level) tuple unchanged from DB
    so leveling.py can compare before/after and decide if a level-up happened."""
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        "UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?",
        (amount, user_id, guild_id),
    )
    await db.commit()
    return await get_xp_and_level(user_id, guild_id)


async def set_level(user_id: int, guild_id: int, new_level: int):
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        "UPDATE users SET level = ? WHERE user_id = ? AND guild_id = ?",
        (new_level, user_id, guild_id),
    )
    await db.commit()


async def get_leaderboard(guild_id: int, order_by: str = "balance", limit: int = 10):
    """order_by must be 'balance' or 'xp'."""
    if order_by not in ("balance", "xp"):
        raise ValueError("order_by must be 'balance' or 'xp'")
    db = get_db()
    async with db.execute(
        f"SELECT user_id, {order_by} FROM users WHERE guild_id = ? "
        f"ORDER BY {order_by} DESC LIMIT ?",
        (guild_id, limit),
    ) as cursor:
        return await cursor.fetchall()

# TODO (Czar): if you add more games later (slots, coinflip), they only need
# get_balance / update_balance from here - no schema changes needed.
