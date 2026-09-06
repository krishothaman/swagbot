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

from cogs.quests import accept_quest, turn_in_quest, check_progress, record_event

U, G = 5, 2
QID = "daily_gamble"


async def rewind_completion(days: float):
    """Pretend the turn-in happened `days` ago, so the midnight-UTC reset has
    been and gone. Cheaper than waiting for tomorrow, and it exercises the
    real code path - daily_reset reads completed_at, nothing else."""
    import time
    d = db.get_db()
    await d.execute(
        "UPDATE player_quests SET completed_at = ? "
        "WHERE user_id = ? AND guild_id = ? AND quest_id = ?",
        (time.time() - days * 86400, U, G, QID),
    )
    await d.commit()


async def main():
    await db.init_db()
    await db.seed_npc_data(); await db.seed_house_data(); await db.seed_quest_data()
    await db.ensure_user(U, G)
    q = await db.get_quest(QID)
    print("quest:", q["title"], "|", q["condition_type"], q["condition_amount"])

    # Gambling BEFORE accepting must not count toward it.
    await record_event(U, G, "gamble_coins", 500)
    print("\naccept:", await accept_quest(U, G, QID))
    cur, req, done = await check_progress(U, G, q)
    print("progress right after accept:", cur, "/", req)
    assert cur == 0, f"pre-accept gambling leaked into progress: {cur}"

    # Not done yet -> must refuse
    msg = await turn_in_quest(U, G, QID)
    print("turn in at 0:", msg)
    assert "Not done" in msg
    bal_before = await db.get_balance(U, G)

    # Partial bet
    await record_event(U, G, "gamble_coins", 40)
    cur, req, done = await check_progress(U, G, q)
    print("after betting 40:", cur, "/", req, "complete:", done)
    assert cur == 40 and not done
    msg = await turn_in_quest(U, G, QID)
    assert "Not done" in msg, "paid out early!"
    assert await db.get_balance(U, G) == bal_before, "balance moved on failed turn-in"

    # Crossing the threshold
    await record_event(U, G, "gamble_coins", 60)
    cur, req, done = await check_progress(U, G, q)
    print("after betting 60 more:", cur, "/", req, "complete:", done)
    assert done, "should be complete at 100"

    print("turn in:", await turn_in_quest(U, G, QID))
    print("balance:", await db.get_balance(U, G))
    assert await db.get_balance(U, G) == bal_before + 200

    # --- Repeatable, but not until the reset ---------------------------
    #
    # This used to assert that re-accepting immediately reset the counter to
    # 0. That was the pre-daily-reset behaviour, where turning in a repeatable
    # DELETED its player_quests row and you could pick it straight back up.
    # That deletion was the daily-quest exploit: it erased the only record the
    # quest had been done. Turning in now marks it 'completed' with a
    # timestamp, so a same-day re-accept is refused outright.
    msg = await accept_quest(U, G, QID)
    print("\nre-accept, same day:", msg)
    assert "already done" in msg.lower(), f"re-accepted a daily the same day: {msg}"

    # The counter is still sitting at 100 while it waits out the cooldown.
    # That's harmless only as long as it can't be spent - the quest is
    # 'completed', not 'active', so a turn-in has to refuse. If this ever
    # passes, a daily pays out twice for one night of gambling.
    msg = await turn_in_quest(U, G, QID)
    print("turn in while on cooldown:", msg)
    assert "not on that quest" in msg.lower(), f"turned in a quest on cooldown: {msg}"
    assert await db.get_balance(U, G) == bal_before + 200, "EXPLOIT: paid out twice"

    # Once the reset boundary has passed the quest comes back, and it's the
    # accept that zeroes the counter (set_player_quest_status does it in SQL).
    await rewind_completion(days=2)
    msg = await accept_quest(U, G, QID)
    print("re-accept after the reset:", msg)
    assert "accepted" in msg.lower(), f"quest never came back after the reset: {msg}"

    cur, req, done = await check_progress(U, G, q)
    print("progress after a real re-accept:", cur, "/", req)
    assert cur == 0, f"counter did not reset on re-accept: {cur}"
    assert not done, "instantly completable after re-accept - exploit!"

    # A non-gambling event type must not touch it
    await record_event(U, G, "have_coins", 999)
    cur, _, _ = await check_progress(U, G, q)
    assert cur == 0, "unrelated event bumped the counter"

    await db.get_db().close()
    print("\nGAMBLE QUEST CHECKS PASSED")

asyncio.run(main())
