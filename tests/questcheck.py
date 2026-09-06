import asyncio, os, shutil, sqlite3, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

# The quest embeds carry emoji and this console is cp1252, which can't encode
# them - printing one raised UnicodeEncodeError and read as a test failure.

import database as db
tmp = tempfile.mkdtemp()
db.DB_PATH = os.path.join(tmp, "t.db")

from cogs.quests import (
    accept_quest, turn_in_quest, check_progress, build_quest_embed, record_event,
)
from config import MAX_ACTIVE_QUESTS

U, G = 1, 2


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_house_data()
    await db.seed_quest_data()
    # get_inventory joins the items table, so without this every bag reads as
    # empty and the item assertions below pass or fail for the wrong reason.
    await db.seed_item_data()
    await db.ensure_user(U, G)

    q = await db.get_quest("first_errand")
    print("quest loaded as dict:", q["title"], "|", q["condition_type"], q["condition_target"], q["condition_amount"])

    # --- THE BUG THAT EXISTED BEFORE: turn in without doing anything ---
    print("\naccept:", await accept_quest(U, G, "first_errand"))
    msg = await turn_in_quest(U, G, "first_errand")
    print("turn in with nothing done:", msg)
    assert "Not done" in msg, "EXPLOIT: paid out without meeting condition!"
    bal = await db.get_balance(U, G)
    assert bal == 100, f"EXPLOIT: balance changed to {bal} on a failed turn-in"

    # --- now actually satisfy it ---
    # first_errand is work_count 3 these days. It used to be "deliver a
    # lockpick", which is why this block used to add one to the inventory -
    # the quest was re-authored in quest_data.py and the check didn't follow.
    for _ in range(q["condition_amount"]):
        await record_event(U, G, "work_count", 1)
    cur, req, complete = await check_progress(U, G, q)
    print("progress after three shifts:", cur, "/", req, "complete:", complete)
    assert complete, f"work_count didn't reach the target: {cur}/{req}"
    msg = await turn_in_quest(U, G, "first_errand")
    print("turn in:", msg)
    assert "complete" in msg.lower()
    print("balance after reward:", await db.get_balance(U, G))
    assert await db.get_balance(U, G) == 100 + q["reward_coins"], "reward coins not paid"

    # non-repeatable can't be redone
    print("re-accept one-shot:", await accept_quest(U, G, "first_errand"))
    assert "already" in (await accept_quest(U, G, "first_errand")).lower()

    # --- deliver_item must CONSUME ---
    # No shipped quest uses deliver_item any more, so this drives a synthetic
    # one. The engine still supports the condition (CONSUMING_CONDITIONS in
    # cogs/quests.py); leaving the consuming path uncovered just because no
    # content happens to use it today is how it quietly rots.
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT OR REPLACE INTO quests (quest_id,npc_id,category,title,description,"
                 "condition_type,condition_target,condition_amount,reward_coins,reward_xp,"
                 "reward_item_id,reward_item_qty,repeatable) VALUES "
                 "('courier',NULL,'daily','Courier','x','deliver_item','lockpick',1,0,0,NULL,0,0)")
    conn.commit(); conn.close()
    await db.add_item_to_inventory(U, G, "lockpick", 1)
    await accept_quest(U, G, "courier")
    print("\ndeliver_item turn in:", await turn_in_quest(U, G, "courier"))
    inv = await db.get_inventory(U, G)
    assert not any(i[0] == "lockpick" for i in inv), "deliver_item did NOT consume the item"
    print("lockpick consumed:", inv)

    # --- have_item must NOT consume ---
    await db.add_item_to_inventory(U, G, "lucky_coin", 1)
    await accept_quest(U, G, "collector")
    print("\nhave_item turn in:", await turn_in_quest(U, G, "collector"))
    inv = await db.get_inventory(U, G)
    assert any(i[0] == "lucky_coin" for i in inv), "have_item wrongly consumed the item"
    print("lucky_coin kept:", inv)

    # --- item reward is granted ---
    await db.set_balance(U, G, 5000)
    await accept_quest(U, G, "prove_yourself")
    print("\ncoins quest:", await turn_in_quest(U, G, "prove_yourself"))
    inv = await db.get_inventory(U, G)
    assert any(i[0] == "fake_id" for i in inv), "reward item not granted"
    print("got reward item:", inv)

    # --- house-tier condition ties into housing ---
    from cogs.housing import purchase_house
    await db.set_level(U, G, 5)
    await db.set_balance(U, G, 99999)
    await accept_quest(U, G, "settle_down")
    print("\nbefore house:", await turn_in_quest(U, G, "settle_down"))
    await purchase_house(U, G, 1)
    print("after house:", await turn_in_quest(U, G, "settle_down"))

    # --- active quest cap ---
    await db.set_balance(U, G, 100)
    # daily_grind was renamed daily_gamble in quest_data.py. Accepting a
    # quest_id that doesn't exist silently does nothing, so this loop was
    # filling one slot fewer than it looked like it was.
    for qid in ("daily_hustle", "daily_gamble", "daily_stash", "moving_up"):
        await accept_quest(U, G, qid)
    n = await db.count_active_quests(U, G)
    print("\nactive quests:", n, "/", MAX_ACTIVE_QUESTS)
    over = await accept_quest(U, G, "first_errand")
    print("accept beyond cap:", over)
    assert n <= MAX_ACTIVE_QUESTS, f"cap exceeded: {n}"

    # --- repeatable resets ---
    await db.set_balance(U, G, 5000)
    print("\nrepeatable turn in:", await turn_in_quest(U, G, "daily_hustle"))
    st = await db.get_player_quest_status(U, G, "daily_hustle")
    print("status after repeatable turn-in:", st)
    # This used to assert "available", i.e. the row was DELETED on turn-in.
    # That deletion WAS the daily-quest exploit: with no record it had been
    # done, a "hold 500 coins" daily could be re-run forever without ever
    # spending anything. It's now recorded completed and gated on the reset.
    assert st == "completed", f"repeatable didn't record its completion: {st}"
    again = await accept_quest(U, G, "daily_hustle")
    print("re-accept same day:", again)
    assert "already done" in again.lower(), "EXPLOIT: repeatable re-runnable same day"

    # --- unknown condition type must fail closed, not pay out ---
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT OR REPLACE INTO quests (quest_id,npc_id,category,title,description,"
                 "condition_type,condition_target,condition_amount,reward_coins,reward_xp,"
                 "reward_item_id,reward_item_qty,repeatable) VALUES "
                 "('broken',NULL,'daily','Broken','x','nonsense_type',NULL,1,9999,0,NULL,0,0)")
    conn.commit(); conn.close()
    await accept_quest(U, G, "broken")
    bal_before = await db.get_balance(U, G)
    msg = await turn_in_quest(U, G, "broken")
    print("\nunknown condition:", msg)
    assert await db.get_balance(U, G) == bal_before, "EXPLOIT: unknown condition paid out!"

    embed = await build_quest_embed(U, G)
    print("\n/quests embed fields:", [(f.name, f.value[:60]) for f in embed.fields])

    await db.get_db().close()
    print("\nALL QUEST CHECKS PASSED")

asyncio.run(main())
