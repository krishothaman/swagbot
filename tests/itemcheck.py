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

import item_data

USER, GUILD = 999, 1


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()

    print("=== all six items seeded ===")
    for i in item_data.ITEMS:
        row = await db.get_item(i["item_id"])
        assert row, f"{i['item_id']} missing"
        print(f"  {row[1]:12} {row[2]:5} coins  ({row[3]})")
    assert len(item_data.ITEMS) == 7   # 4 merchant + 3 gun man

    print("\n=== THE POINT: editing a price applies on reseed ===")
    original = item_data.ITEMS[0]["price"]
    item_id = item_data.ITEMS[0]["item_id"]
    item_data.ITEMS[0]["price"] = 999
    await db.seed_item_data()
    row = await db.get_item(item_id)
    assert row[2] == 999, f"price edit did NOT apply: still {row[2]}"
    print(f"  {item_id}: {original} -> {row[2]} after editing the file and reseeding")
    item_data.ITEMS[0]["price"] = original
    await db.seed_item_data()

    print("\n=== player property survives a reseed ===")
    await db.ensure_user(USER, GUILD)
    await db.add_item_to_inventory(USER, GUILD, "p250", 1)
    await db.add_item_to_inventory(USER, GUILD, "c4", 3)
    before = sorted(await db.get_inventory(USER, GUILD))
    await db.seed_item_data()
    after = sorted(await db.get_inventory(USER, GUILD))
    assert before == after, f"reseed disturbed inventory:\n{before}\n{after}"
    print(f"  {[(n, q) for _, n, q in after]} intact after reseed")

    print("\n=== removing an item from the file removes it everywhere ===")
    removed = [i for i in item_data.ITEMS if i["item_id"] == "c4"][0]
    item_data.ITEMS.remove(removed)
    await db.seed_item_data()

    assert await db.get_item("c4") is None, "c4 still in the catalog"
    inv = {i[0] for i in await db.get_inventory(USER, GUILD)}
    assert "c4" not in inv, "player still holds a deleted item"
    assert "p250" in inv, "removing c4 took the P250 with it!"
    print(f"  c4 gone from catalog and inventory; p250 untouched -> {inv}")

    item_data.ITEMS.append(removed)
    await db.seed_item_data()
    assert await db.get_item("c4") is not None
    print("  re-adding it to the file brings it back")

    print("\n=== npc shop listings still correct ===")
    for npc_id, expected in (("shady_merchant", 4), ("gun_man", 3)):
        rows = await db.get_items_for_npc(npc_id)
        assert len(rows) == expected, f"{npc_id} has {len(rows)}, expected {expected}"
        print(f"  {npc_id:15} {[r[1] for r in rows]}")

    print("\nITEM SEEDING CHECKS PASSED")


asyncio.run(main())
