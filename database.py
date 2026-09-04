
import aiosqlite
import time
from config import DB_PATH, STARTING_BALANCE

_db: aiosqlite.Connection | None = None


async def _migrate_quest_tables(db: aiosqlite.Connection):
    """One-time migration to the condition-based quest schema.

    Only fires if a `quests` table exists WITHOUT the new columns - so it runs
    once on the next boot after this change and never again. Without the
    version check this would wipe player quest progress on every restart.
    """
    async with db.execute("PRAGMA table_info(quests)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if not columns:
        return  # fresh database, nothing to migrate - CREATE TABLE handles it
    if "condition_type" in columns:
        return  # already on the new schema

    await db.execute("DROP TABLE IF EXISTS quests")
    await db.execute("DROP TABLE IF EXISTS player_quests")
    await db.commit()


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
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS npcs (
            npc_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            greeting_text TEXT NOT NULL
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            npc_id TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, guild_id, item_id)
        )
    """)
    await _migrate_quest_tables(_db)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS quests (
            quest_id TEXT PRIMARY KEY,
            npc_id TEXT,
            category TEXT NOT NULL DEFAULT 'npc',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            condition_type TEXT NOT NULL,
            condition_target TEXT,
            condition_amount INTEGER NOT NULL DEFAULT 1,
            reward_coins INTEGER NOT NULL DEFAULT 0,
            reward_xp INTEGER NOT NULL DEFAULT 0,
            reward_item_id TEXT,
            reward_item_qty INTEGER NOT NULL DEFAULT 0,
            repeatable INTEGER NOT NULL DEFAULT 0
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS player_quests (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            quest_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            progress INTEGER NOT NULL DEFAULT 0,
            accepted_at REAL NOT NULL DEFAULT 0,
            completed_at REAL,
            PRIMARY KEY (user_id, guild_id, quest_id)
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS npc_flavor (
            npc_id TEXT NOT NULL,
            line TEXT NOT NULL,
            PRIMARY KEY (npc_id, line)
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS houses (
            house_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tier INTEGER NOT NULL,
            price INTEGER NOT NULL,
            storage_slots INTEGER NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS player_houses (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            house_id TEXT NOT NULL,
            purchased_at REAL NOT NULL,
            upgraded_at REAL,
            PRIMARY KEY (user_id, guild_id)
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS house_storage (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, guild_id, item_id)
        )
    """)
    await _db.commit()
async def seed_npc_data():
    db = get_db()

    await db.execute(
        "INSERT OR IGNORE INTO npcs (npc_id, name, role, greeting_text) VALUES (?, ?, ?, ?)",
        ("shady_merchant", "Shady Merchant", "merchant",
         "i got the stuff, what do you want?"),
    )

    items = [
        ("lockpick", "Lockpick", 150, "shady_merchant", "yk what to do with it."),
        ("fake_id", "Fake ID", 300, "shady_merchant", "you can use it for whatever the heck you want."),
        ("lucky_coin", "Lucky Coin", 500, "shady_merchant", "hehe."),
    ]
    await db.executemany(
        "INSERT OR IGNORE INTO items (item_id, name, price, npc_id, description) VALUES (?, ?, ?, ?, ?)",
        items,
    )

    await db.execute(
        "INSERT OR IGNORE INTO npcs (npc_id, name, role, greeting_text) VALUES (?, ?, ?, ?)",
        ("landlord", "The Landlord", "landlord",
         "You're standing in my lobby. State your business."),
    )

    # Flavor lines get picked at random when you talk to an NPC. The merchant's
    # fifth-floor line is deliberately in here and not scripted anywhere.
    flavor = [
        ("shady_merchant", "keep your voice down, the walls listen."),
        ("shady_merchant", "There has always been a fifth floor."),
        ("shady_merchant", "you look like someone who pays retail. dont be that guy."),
        ("shady_merchant", "i dont ask where you got it. dont ask where i got it."),
    ]
    await db.executemany(
        "INSERT OR IGNORE INTO npc_flavor (npc_id, line) VALUES (?, ?)", flavor
    )

    await db.commit()


async def seed_house_data():
    db = get_db()

    houses = [
        ("studio", "Studio", 1, 2500, 10,
         "One room, one window, one lock that mostly works."),
        ("apartment", "Apartment", 2, 12000, 30,
         "Real walls. Real neighbors. A door that closes properly."),
        ("mansion", "Mansion", 3, 60000, 100,
         "More rooms than you'll ever walk into."),
    ]
    await db.executemany(
        "INSERT OR IGNORE INTO houses (house_id, name, tier, price, storage_slots, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        houses,
    )

    await db.commit()
async def get_npc(npc_id: str):
    db = get_db()
    async with db.execute(
        "SELECT npc_id, name, role, greeting_text FROM npcs WHERE npc_id = ?", (npc_id,)
    ) as cursor:
        return await cursor.fetchone()
async def get_items_for_npc(npc_id: str):
    db = get_db()
    async with db.execute(
        "SELECT item_id, name, price, description FROM items WHERE npc_id = ?", (npc_id,)
    ) as cursor:
        return await cursor.fetchall()
async def get_item(item_id: str):
    db = get_db()
    async with db.execute(
        "SELECT item_id, name, price, npc_id, description FROM items WHERE item_id = ?", (item_id,)
    ) as cursor:
        return await cursor.fetchone()
async def get_player_items(user_id: int, guild_id: int):
    db = get_db()
    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ) as cursor:
        return await cursor.fetchall()
async def add_item_to_inventory(user_id: int, guild_id: int, item_id: str, quantity: int = 1):
    db = get_db()
    await db.execute(
        """INSERT INTO inventory (user_id, guild_id, item_id, quantity)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, guild_id, item_id)
           DO UPDATE SET quantity = quantity + excluded.quantity""",
        (user_id, guild_id, item_id, quantity),
    )
    await db.commit()

async def remove_item_from_inventory(user_id: int, guild_id: int, item_id: str, quantity: int = 1):
    db = get_db()

    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", 
        (user_id,guild_id,item_id),
        
    
    ) as cursor: 
        row = await cursor.fetchone()

    owned = row[0] if row else 0
    if owned < quantity:
        return False  # negative value

    if owned == quantity:
        
        await db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (user_id, guild_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (quantity, user_id, guild_id, item_id),
        )

    await db.commit()
    return True


async def get_inventory(user_id: int, guild_id: int):
    db = get_db()
    async with db.execute(
        """SELECT inventory.item_id ,items.name, inventory.quantity FROM inventory
           JOIN items ON items.item_id = inventory.item_id
           WHERE inventory.user_id = ? AND inventory.guild_id = ?""",
        (user_id, guild_id),
    ) as cursor:
        return await cursor.fetchall()
async def seed_quest_data():
    """Loads quest content from quest_data.py.

    Uses INSERT OR REPLACE (unlike the other seeders) so editing quest_data.py
    and restarting actually applies the change - that file is the source of
    truth for quest content.
    """
    from quest_data import QUESTS

    db = get_db()
    await db.executemany(
        """INSERT OR REPLACE INTO quests
           (quest_id, npc_id, category, title, description,
            condition_type, condition_target, condition_amount,
            reward_coins, reward_xp, reward_item_id, reward_item_qty, repeatable)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                q["quest_id"], q["npc_id"], q["category"], q["title"], q["description"],
                q["condition_type"], q["condition_target"], q["condition_amount"],
                q["reward_coins"], q["reward_xp"], q["reward_item_id"],
                q["reward_item_qty"], int(q["repeatable"]),
            )
            for q in QUESTS
        ],
    )

    # Delete quests that were removed from quest_data.py, so taking a quest out
    # of the file actually takes it out of the game. Also clears any player rows
    # pointing at them, otherwise they'd linger as un-turn-in-able active quests
    # taking up slots against the cap.
    keep = [q["quest_id"] for q in QUESTS]
    placeholders = ",".join("?" * len(keep))
    await db.execute(f"DELETE FROM quests WHERE quest_id NOT IN ({placeholders})", keep)
    await db.execute(
        f"DELETE FROM player_quests WHERE quest_id NOT IN ({placeholders})", keep
    )
    await db.commit()


# Quests have enough columns that positional unpacking is a bug waiting to
# happen, so these return dicts instead of raw tuples.
QUEST_FIELDS = (
    "quest_id", "npc_id", "category", "title", "description",
    "condition_type", "condition_target", "condition_amount",
    "reward_coins", "reward_xp", "reward_item_id", "reward_item_qty", "repeatable",
)
_QUEST_SELECT = f"SELECT {', '.join(QUEST_FIELDS)} FROM quests"


def _quest_dict(row):
    return dict(zip(QUEST_FIELDS, row)) if row else None


async def get_quest(quest_id: str):
    db = get_db()
    async with db.execute(f"{_QUEST_SELECT} WHERE quest_id = ?", (quest_id,)) as cursor:
        return _quest_dict(await cursor.fetchone())


async def get_quests_for_npc(npc_id: str):
    db = get_db()
    async with db.execute(f"{_QUEST_SELECT} WHERE npc_id = ?", (npc_id,)) as cursor:
        return [_quest_dict(row) for row in await cursor.fetchall()]


async def get_quests_by_category(category: str):
    db = get_db()
    async with db.execute(f"{_QUEST_SELECT} WHERE category = ?", (category,)) as cursor:
        return [_quest_dict(row) for row in await cursor.fetchall()]


async def get_player_quest_status(user_id: int, guild_id: int, quest_id: str):
    """Returns 'available' if no row exists yet."""
    db = get_db()
    async with db.execute(
        "SELECT status FROM player_quests WHERE user_id = ? AND guild_id = ? AND quest_id = ?",
        (user_id, guild_id, quest_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else "available"


async def get_player_quests(user_id: int, guild_id: int, status: str = None):
    """Returns [(quest_id, status, progress)] - optionally filtered by status."""
    db = get_db()
    sql = "SELECT quest_id, status, progress FROM player_quests WHERE user_id = ? AND guild_id = ?"
    params = [user_id, guild_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    async with db.execute(sql, params) as cursor:
        return await cursor.fetchall()


async def count_active_quests(user_id: int, guild_id: int) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM player_quests WHERE user_id = ? AND guild_id = ? AND status = 'active'",
        (user_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def set_player_quest_status(user_id: int, guild_id: int, quest_id: str, status: str):
    """Stamps accepted_at on accept and completed_at on completion, so a real
    daily reset can be layered on later without another migration."""
    now = time.time()
    accepted_at = now if status == "active" else 0
    completed_at = now if status == "completed" else None

    db = get_db()
    await db.execute(
        """INSERT INTO player_quests (user_id, guild_id, quest_id, status, progress, accepted_at, completed_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)
           ON CONFLICT(user_id, guild_id, quest_id) DO UPDATE SET
               status = excluded.status,
               completed_at = excluded.completed_at,
               -- accepting resets the counter so a re-run starts from zero
               progress = CASE WHEN excluded.status = 'active' THEN 0 ELSE player_quests.progress END""",
        (user_id, guild_id, quest_id, status, accepted_at, completed_at),
    )
    await db.commit()


async def get_quest_progress(user_id: int, guild_id: int, quest_id: str) -> int:
    """Stored counter for quests that can't be derived from current state
    (e.g. "gamble 100 coins" - nothing in the DB remembers that otherwise)."""
    db = get_db()
    async with db.execute(
        "SELECT progress FROM player_quests WHERE user_id = ? AND guild_id = ? AND quest_id = ?",
        (user_id, guild_id, quest_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def add_quest_progress(user_id: int, guild_id: int, condition_type: str, amount: int):
    """Bumps progress on every ACTIVE quest using this condition type.
    One statement, so adding a gambling quest costs nothing at runtime."""
    db = get_db()
    await db.execute(
        """UPDATE player_quests SET progress = progress + ?
           WHERE user_id = ? AND guild_id = ? AND status = 'active'
             AND quest_id IN (SELECT quest_id FROM quests WHERE condition_type = ?)""",
        (amount, user_id, guild_id, condition_type),
    )
    await db.commit()


async def clear_player_quest(user_id: int, guild_id: int, quest_id: str):
    """Removes the row entirely so a repeatable quest becomes available again."""
    db = get_db()
    await db.execute(
        "DELETE FROM player_quests WHERE user_id = ? AND guild_id = ? AND quest_id = ?",
        (user_id, guild_id, quest_id),
    )
    await db.commit()




async def get_npc_flavor_lines(npc_id: str):
    db = get_db()
    async with db.execute(
        "SELECT line FROM npc_flavor WHERE npc_id = ?", (npc_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


# --- Housing ---

async def get_houses():
    """All buyable houses, cheapest tier first."""
    db = get_db()
    async with db.execute(
        "SELECT house_id, name, tier, price, storage_slots, description FROM houses ORDER BY tier"
    ) as cursor:
        return await cursor.fetchall()


async def get_house(house_id: str):
    db = get_db()
    async with db.execute(
        "SELECT house_id, name, tier, price, storage_slots, description FROM houses WHERE house_id = ?",
        (house_id,),
    ) as cursor:
        return await cursor.fetchone()


async def get_house_by_tier(tier: int):
    db = get_db()
    async with db.execute(
        "SELECT house_id, name, tier, price, storage_slots, description FROM houses WHERE tier = ?",
        (tier,),
    ) as cursor:
        return await cursor.fetchone()


async def get_player_house(user_id: int, guild_id: int):
    """Returns (house_id, name, tier, price, storage_slots, description,
    purchased_at, upgraded_at) or None if they're homeless."""
    db = get_db()
    async with db.execute(
        """SELECT houses.house_id, houses.name, houses.tier, houses.price,
                  houses.storage_slots, houses.description,
                  player_houses.purchased_at, player_houses.upgraded_at
           FROM player_houses
           JOIN houses ON houses.house_id = player_houses.house_id
           WHERE player_houses.user_id = ? AND player_houses.guild_id = ?""",
        (user_id, guild_id),
    ) as cursor:
        return await cursor.fetchone()


async def set_player_house(user_id: int, guild_id: int, house_id: str, is_upgrade: bool = False):
    """Buys or upgrades into a house. One house per player, so an upgrade
    overwrites the existing row and stamps upgraded_at."""
    db = get_db()
    now = time.time()
    if is_upgrade:
        await db.execute(
            """INSERT INTO player_houses (user_id, guild_id, house_id, purchased_at, upgraded_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, guild_id)
               DO UPDATE SET house_id = excluded.house_id, upgraded_at = excluded.upgraded_at""",
            (user_id, guild_id, house_id, now, now),
        )
    else:
        await db.execute(
            """INSERT INTO player_houses (user_id, guild_id, house_id, purchased_at, upgraded_at)
               VALUES (?, ?, ?, ?, NULL)
               ON CONFLICT(user_id, guild_id)
               DO UPDATE SET house_id = excluded.house_id, purchased_at = excluded.purchased_at""",
            (user_id, guild_id, house_id, now),
        )
    await db.commit()


async def remove_player_house(user_id: int, guild_id: int):
    db = get_db()
    await db.execute(
        "DELETE FROM player_houses WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    )
    await db.commit()


async def get_house_storage(user_id: int, guild_id: int):
    """Same shape as get_inventory() so both can share a renderer."""
    db = get_db()
    async with db.execute(
        """SELECT house_storage.item_id, items.name, house_storage.quantity FROM house_storage
           JOIN items ON items.item_id = house_storage.item_id
           WHERE house_storage.user_id = ? AND house_storage.guild_id = ?""",
        (user_id, guild_id),
    ) as cursor:
        return await cursor.fetchall()


async def get_house_storage_used(user_id: int, guild_id: int) -> int:
    """Total item count stored - a slot holds one item, not one stack."""
    db = get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM house_storage WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def add_item_to_house_storage(user_id: int, guild_id: int, item_id: str, quantity: int = 1):
    db = get_db()
    await db.execute(
        """INSERT INTO house_storage (user_id, guild_id, item_id, quantity)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, guild_id, item_id)
           DO UPDATE SET quantity = quantity + excluded.quantity""",
        (user_id, guild_id, item_id, quantity),
    )
    await db.commit()


async def remove_item_from_house_storage(user_id: int, guild_id: int, item_id: str, quantity: int = 1):
    db = get_db()

    async with db.execute(
        "SELECT quantity FROM house_storage WHERE user_id = ? AND guild_id = ? AND item_id = ?",
        (user_id, guild_id, item_id),
    ) as cursor:
        row = await cursor.fetchone()

    stored = row[0] if row else 0
    if stored < quantity:
        return False

    if stored == quantity:
        await db.execute(
            "DELETE FROM house_storage WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (user_id, guild_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE house_storage SET quantity = quantity - ? WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (quantity, user_id, guild_id, item_id),
        )

    await db.commit()
    return True


def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized - call init_db() first")
    return _db


async def ensure_user(user_id: int, guild_id: int):
    "uhh basically checks the user is in db, if not adds them"
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


async def set_balance(user_id: int, guild_id: int, amount: int):
    """Sets balance to an exact value. Used by the dev tools - normal gameplay
    should go through update_balance so it stays relative."""
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        "UPDATE users SET balance = ? WHERE user_id = ? AND guild_id = ?",
        (amount, user_id, guild_id),
    )
    await db.commit()
    return await get_balance(user_id, guild_id)


async def set_xp(user_id: int, guild_id: int, amount: int):
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        "UPDATE users SET xp = ? WHERE user_id = ? AND guild_id = ?",
        (amount, user_id, guild_id),
    )
    await db.commit()


async def reset_cooldowns(user_id: int, guild_id: int):
    """Zeroes every cooldown so /daily and /work are immediately usable again."""
    await ensure_user(user_id, guild_id)
    db = get_db()
    await db.execute(
        """UPDATE users SET last_daily = 0, last_work = 0, last_message_xp = 0
           WHERE user_id = ? AND guild_id = ?""",
        (user_id, guild_id),
    )
    await db.commit()


async def get_all_items():
    db = get_db()
    async with db.execute(
        "SELECT item_id, name, price FROM items ORDER BY name"
    ) as cursor:
        return await cursor.fetchall()


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
