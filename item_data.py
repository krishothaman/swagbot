"""Item content lives here. This is the ONLY file you edit to add or tune items.

Change a price, restart the bot, and it applies immediately - items are seeded
with INSERT OR REPLACE, so this file wins over whatever is in the database.
Editing item rows directly in the DB will just get overwritten on next boot.

--- FIELDS ---

item_id      Permanent internal id. NEVER change this once players own the
             item - inventories reference it, and renaming it orphans them.
             Change `name` instead; that's the part players see.
name         Display name.
price        What the seller charges. Selling back gives SELL_PRICE_RATIO of it.
npc_id       Who stocks it. Must match a seeded NPC (shady_merchant, gun_man).
description  One line, shown in shop menus. Written in the seller's voice.

--- REMOVING AN ITEM ---

Deleting an entry from this file removes the item from the game on the next
boot, AND destroys every copy players are holding (inventory and house
storage both). That's deliberate - this file is the source of truth - but it
means deleting a line is a destructive act, not a cosmetic one. Comment it out
only if you want it gone for real.

Changing a `price` is always safe. Changing an `item_id` is not: it reads as
"delete the old item, add a new one", so anyone holding the old one loses it.
"""

ITEMS = [
    # --- Shady Merchant ---------------------------------------------------
    # The starter fence. Cheap, useful, no questions.
    {
        "item_id": "lockpick",
        "name": "Lockpick",
        "price": 150,
        "npc_id": "shady_merchant",
        "description": "yk what to do with it.",
    },
    {
        "item_id": "fake_id",
        "name": "Fake ID",
        "price": 300,
        "npc_id": "shady_merchant",
        # Required to run the Inside Job heist approach. Not consumed.
        "description": "you can use it for whatever the heck you want.",
    },
    {
        "item_id": "lucky_coin",
        "name": "Lucky Coin",
        "price": 500,
        "npc_id": "shady_merchant",
        "description": "hehe.",
    },

    # --- The Gun Man ------------------------------------------------------
    # Level-gated behind GUNMAN_LEVEL_REQUIREMENT. Guns are permanent once
    # bought; the C4 is meant to be spent.
    {
        "item_id": "p250",
        "name": "P250",
        "price": 5000,
        "npc_id": "gun_man",
        "description": "Everybody's first. Point it, it works. Boring? BORING. Never lied to me once.",
    },
    {
        "item_id": "five_seven",
        "name": "Five-seveN",
        "price": 7500,
        "npc_id": "gun_man",
        "description": "Twenty rounds and it goes through the thing behind the thing. Don't ask how I know.",
    },
    {
        "item_id": "c4",
        "name": "C4",
        "price": 3000,
        "npc_id": "gun_man",
        "description": "One door, one problem, one solution. You get to use it once, so pick the door.",
    },
]
