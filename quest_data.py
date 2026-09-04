"""Quest content lives here. This is the ONLY file you edit to add or tune quests.

Edit a quest, restart the bot, and the change applies immediately (quests are
seeded with INSERT OR REPLACE, so this file is the single source of truth -
editing quest rows directly in the DB will just get overwritten on next boot).

--- HOW A QUEST WORKS ---

Every quest has ONE condition. The engine checks it live whenever you view or
try to turn in the quest - there's no background tracking to get out of sync.

condition_type    condition_target   condition_amount   Completes when...
-------------------------------------------------------------------------------
have_item         item_id            N                  you hold N of that item
                                                        (NOT consumed on turn-in)
deliver_item      item_id            N                  you hold N of that item
                                                        (CONSUMED on turn-in)
reach_level       None               N                  your level >= N
have_coins        None               N                  your balance >= N
own_house_tier    None               N                  your house tier >= N
                                                        (1=Studio 2=Apartment 3=Mansion)
gamble_coins      None               N                  you've bet N coins total
                                                        since accepting the quest
                                                        (counts coinflip/slots/blackjack)
work_count        None               N                  you've run /work N times
                                                        since accepting the quest

Note: gamble_coins and work_count are COUNTED as you play rather than read from
your current state - nothing in the DB remembers you did those otherwise. Both
reset to 0 each time you accept the quest, and only count actions taken while
the quest is active.

Also note: removing a quest from this file DELETES it from the game on next
boot (along with any player progress on it). That's intentional - this file is
the source of truth.

To add a NEW condition type, add a checker function to CONDITION_CHECKERS in
cogs/quests.py. You don't need to touch the engine for new *content* though -
only for new *kinds* of condition.

--- FIELDS ---

quest_id          unique string id. Changing it creates a new quest.
npc_id            which NPC offers it. None = daily quest (offered in /quests).
category          "npc" or "daily". Daily quests show up in /quests directly.
title             shown in the quest list
description       flavour text
reward_coins      coins paid on turn-in (0 for none)
reward_xp         xp paid on turn-in (0 for none)
reward_item_id    item granted on turn-in (None for none)
reward_item_qty   how many of that item
repeatable        True  = can be re-accepted after turning in (use for dailies)
                  False = one and done
"""

QUESTS = [
   
    # SHADY MERCHANT - npc quests
    
    {
        "quest_id": "first_errand",
        "npc_id": "shady_merchant",
        "category": "npc",
        "title": "Earn It First",
        "description": "go do three honest shifts before you come asking me for anything.",
        "condition_type": "work_count",
        "condition_target": None,
        "condition_amount": 3,
        "reward_coins": 300,
        "reward_xp": 75,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": False,
    },
    {
        "quest_id": "prove_yourself",
        "npc_id": "shady_merchant",
        "category": "npc",
        "title": "Prove You're Not Broke",
        "description": "i dont deal with broke people. show me you got 5000 on you.",
        "condition_type": "have_coins",
        "condition_target": None,
        "condition_amount": 5000,
        "reward_coins": 0,
        "reward_xp": 150,
        "reward_item_id": "fake_id",
        "reward_item_qty": 1,
        "repeatable": False,
    },
    {
        "quest_id": "collector",
        "npc_id": "shady_merchant",
        "category": "npc",
        "title": "The Collector",
        "description": "hold onto a lucky coin for me. dont spend it. i'll know.",
        "condition_type": "have_item",
        "condition_target": "lucky_coin",
        "condition_amount": 1,
        "reward_coins": 750,
        "reward_xp": 100,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": False,
    },

  
    # LANDLORD - npc quests
   
    {
        "quest_id": "settle_down",
        "npc_id": "landlord",
        "category": "npc",
        "title": "Settle Down",
        "description": "Get a roof over your head. Any roof. The building prefers it.",
        "condition_type": "own_house_tier",
        "condition_target": None,
        "condition_amount": 1,
        "reward_coins": 500,
        "reward_xp": 200,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": False,
    },
    {
        "quest_id": "moving_up",
        "npc_id": "landlord",
        "category": "npc",
        "title": "Moving Up",
        "description": "The higher floors were always going to be yours. Reach the Apartment.",
        "condition_type": "own_house_tier",
        "condition_target": None,
        "condition_amount": 2,
        "reward_coins": 2000,
        "reward_xp": 400,
        "reward_item_id": "lucky_coin",
        "reward_item_qty": 1,
        "repeatable": False,
    },


    # DAILY QUESTS - no npc
   
    {
        "quest_id": "daily_hustle",
        "npc_id": None,
        "category": "daily",
        "title": "Daily Hustle",
        "description": "Stack 500 coins. Doesn't matter how you got it.",
        "condition_type": "have_coins",
        "condition_target": None,
        "condition_amount": 500,
        "reward_coins": 250,
        "reward_xp": 75,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": True,
    },
    {
        "quest_id": "daily_gamble",
        "npc_id": None,
        "category": "daily",
        "title": "Feeling Lucky",
        "description": "Bet 100 coins. Win or lose, doesn't matter.",
        "condition_type": "gamble_coins",
        "condition_target": None,
        "condition_amount": 100,
        "reward_coins": 200,
        "reward_xp": 50,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": True,
    },
    {
        "quest_id": "daily_stash",
        "npc_id": None,
        "category": "daily",
        "title": "Build A Stash",
        "description": "Get your hands on 2 lockpicks. Keep them.",
        "condition_type": "have_item",
        "condition_target": "lockpick",
        "condition_amount": 2,
        "reward_coins": 300,
        "reward_xp": 60,
        "reward_item_id": None,
        "reward_item_qty": 0,
        "repeatable": True,
    },
]

