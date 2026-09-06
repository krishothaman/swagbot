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

from config import GUNMAN_LEVEL_REQUIREMENT
from cogs.gunman import gunman_intro, GUNMAN_ID, GUN_IDS

USER, GUILD = 4242, 1


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()   # items live in item_data.py now, not in seed_npc_data
    await db.seed_house_data()

    print("=== the NPC exists ===")
    npc = await db.get_npc(GUNMAN_ID)
    assert npc, "gun_man was not seeded"
    print(f"  {npc[1]} ({npc[2]})")

    print("\n=== his stock ===")
    items = await db.get_items_for_npc(GUNMAN_ID)
    assert len(items) == 3, f"expected 3 items, got {len(items)}"
    for item_id, name, price, desc in sorted(items, key=lambda i: i[2]):
        print(f"  {name:12} {price:5} coins  ({item_id})")
    prices = {i[0]: i[2] for i in items}
    assert prices == {"p250": 5000, "five_seven": 7500, "c4": 3000}, prices
    print("  prices match spec")

    print("\n=== flavor lines ===")
    lines = await db.get_npc_flavor_lines(GUNMAN_ID)
    assert lines, "no flavor lines seeded"
    print(f"  {len(lines)} lines, e.g. {lines[0]!r}")

    print(f"\n=== level gate (needs {GUNMAN_LEVEL_REQUIREMENT}) ===")
    await db.ensure_user(USER, GUILD)
    await db.set_level(USER, GUILD, GUNMAN_LEVEL_REQUIREMENT - 1)
    embed, view = await gunman_intro(USER, GUILD)
    assert view is None, "he served an under-levelled player!"
    print(f"  at level {GUNMAN_LEVEL_REQUIREMENT - 1}: turned away -> {embed.footer.text}")

    await db.set_level(USER, GUILD, GUNMAN_LEVEL_REQUIREMENT)
    embed, view = await gunman_intro(USER, GUILD)
    assert view is not None, "he refused a qualifying player!"
    print(f"  at level {GUNMAN_LEVEL_REQUIREMENT}: let in")

    print("\n=== greeting changes once you're carrying ===")
    unarmed = embed.description
    await db.add_item_to_inventory(USER, GUILD, "p250", 1)
    from cogs.gunman import GREETINGS_ARMED, GREETINGS_UNARMED
    armed_embed, _ = await gunman_intro(USER, GUILD)
    # pools are random, so check membership rather than a specific line
    assert any(armed_embed.description.startswith(g[:25]) for g in GREETINGS_ARMED), \
        "still using the unarmed greeting while holding a gun"
    print("  owning a P250 switches him to the armed greeting pool")

    print("\n=== the money actually moves ===")
    await db.set_balance(USER, GUILD, 10000)
    before = await db.get_balance(USER, GUILD)
    item = await db.get_item("five_seven")
    await db.update_balance(USER, GUILD, -item[2])
    await db.add_item_to_inventory(USER, GUILD, "five_seven", 1)
    after = await db.get_balance(USER, GUILD)
    assert after == before - 7500, f"{before} -> {after}"
    inv = {i[0] for i in await db.get_inventory(USER, GUILD)}
    assert "five_seven" in inv and "p250" in inv
    print(f"  {before} -> {after} after buying a Five-seveN, both guns held")

    print("\n=== seeding twice must not duplicate or wipe anything ===")
    await db.seed_npc_data()
    items_again = await db.get_items_for_npc(GUNMAN_ID)
    assert len(items_again) == 3, f"duplicated to {len(items_again)}"
    inv_after = {i[0] for i in await db.get_inventory(USER, GUILD)}
    assert inv_after == inv, "re-seeding disturbed a player's inventory"
    print("  re-seed is clean (3 items, inventory intact)")

    print("\n=== old items still there ===")
    merch = await db.get_items_for_npc("shady_merchant")
    print(f"  shady_merchant still sells {len(merch)}: {[m[1] for m in merch]}")
    assert len(merch) == 4

    print("\nGUN MAN CHECKS PASSED")


asyncio.run(main())
