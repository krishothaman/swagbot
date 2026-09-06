import asyncio, os, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import database as db
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")

from cogs.housing import purchase_house, sell_house  # also proves cogs import
import cogs.npc  # proves no circular import

U, G = 1, 2


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_house_data()

    await db.ensure_user(U, G)
    print("no house ->", await db.get_player_house(U, G))

    print("broke+lowlevel:", await purchase_house(U, G, 1))

    await db.set_level(U, G, 3)
    print("lowbal:", await purchase_house(U, G, 1))

    await db.update_balance(U, G, 5000)
    print("buy studio:", await purchase_house(U, G, 1))
    print("owns:", await db.get_player_house(U, G))
    print("bal:", await db.get_balance(U, G))

    print("rebuy same:", await purchase_house(U, G, 1))
    print("upgrade too low lvl:", await purchase_house(U, G, 2))

    # storage
    await db.add_item_to_inventory(U, G, "lockpick", 3)
    await db.add_item_to_house_storage(U, G, "lockpick", 2)
    print("storage:", await db.get_house_storage(U, G), "used:", await db.get_house_storage_used(U, G))
    print("sell blocked:", await sell_house(U, G))
    print("withdraw:", await db.remove_item_from_house_storage(U, G, "lockpick", 2))
    print("used now:", await db.get_house_storage_used(U, G))
    print("sell:", await sell_house(U, G))
    print("owns after sell:", await db.get_player_house(U, G))

    # upgrade path
    await db.set_level(U, G, 25)
    await db.update_balance(U, G, 100000)
    print("buy studio:", await purchase_house(U, G, 1))
    print("upgrade->mansion:", await purchase_house(U, G, 3))
    h = await db.get_player_house(U, G)
    print("owns:", h[1], "upgraded_at set:", h[7] is not None)
    print("downgrade:", await purchase_house(U, G, 1))
    print("flavor:", await db.get_npc_flavor_lines("shady_merchant"))

asyncio.run(main())
