"""The Casino Owner: does he exist, does /talk reach him, and do his tables
pay exactly what the slash commands pay?

The hub runs the games itself, so the risk this guards is drift - the button
and the command quietly becoming two different games.
"""
import asyncio, os, random, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

tmp = os.path.join(tempfile.mkdtemp(), "test.db")
import config
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp
import casino_logic as C
from config import MIN_BET

U, G = 11, 4
SEED = 777


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()
    await db.seed_quest_data()
    await db.ensure_user(U, G)

    import cogs.casino as casino

    print("=== the Casino Owner is a real seeded NPC ===")
    row = await db.get_npc(casino.CASINO_ID)
    assert row is not None, f"{casino.CASINO_ID} was never seeded into npcs"
    npc_id, name, role, greeting = row
    print(f"  {npc_id} | {name} | {role}")
    print(f"  greeting: {greeting[:70]}")
    assert name and greeting, "the owner needs a name and something to say"

    flavor = await db.get_npc_flavor_lines(casino.CASINO_ID)
    print(f"  flavor lines: {len(flavor)}")
    assert len(flavor) >= 3, "give him at least three lines so he doesn't loop"

    print("\n=== /talk offers him ===")
    from cogs.npc import NPC
    choices = {c.value for c in NPC.talk.parameters[0].choices}
    print(f"  /talk choices: {sorted(choices)}")
    assert casino.CASINO_ID in choices, "/talk has no casino_owner option"

    print("\n=== his hub opens, with a table for each game ===")
    embed, view = await casino.casino_intro(U, G)
    assert embed is not None and view is not None, "the casino never opens"
    labels = [c.label for c in view.children if hasattr(c, "label")]
    print(f"  buttons: {labels}")
    for wanted in ("Coinflip", "Slots", "Blackjack"):
        assert any(wanted.lower() in (l or "").lower() for l in labels), \
            f"no {wanted} table in the casino"

    print("\n=== his coinflip pays exactly what /coinflip pays ===")
    for trial in range(5):
        await db.set_balance(U, G, 50_000)
        before = await db.get_balance(U, G)

        random.seed(SEED + trial)
        expected_result = C.coinflip_flip(random)
        expected = C.coinflip_payout(400, won=expected_result == "heads")

        random.seed(SEED + trial)
        message = await casino.play_coinflip(U, G, 400, "heads")
        actual = await db.get_balance(U, G) - before

        print(f"  {expected_result:6} -> expected {expected:+6}, got {actual:+6}")
        assert actual == expected, f"the hub's coinflip pays differently: {actual:+} vs {expected:+}"
        assert message, "the table said nothing"

    print("\n=== his slots pay exactly what /slots pays ===")
    for trial in range(5):
        await db.set_balance(U, G, 50_000)
        before = await db.get_balance(U, G)

        random.seed(SEED + trial)
        expected_reel = C.spin(random)
        expected, kind = C.slots_payout(expected_reel, 400)

        random.seed(SEED + trial)
        await casino.play_slots(U, G, 400)
        actual = await db.get_balance(U, G) - before

        print(f"  {expected_reel} {kind:8} -> expected {expected:+6}, got {actual:+6}")
        assert actual == expected, f"the hub's slots pay differently: {actual:+} vs {expected:+}"

    print("\n=== the house rules are the same at his tables ===")
    for bet, why in ((MIN_BET - 1, "under the minimum"), (0, "zero"), (-5, "negative")):
        await db.set_balance(U, G, 10_000)
        before = await db.get_balance(U, G)
        message = await casino.play_coinflip(U, G, bet, "heads")
        assert await db.get_balance(U, G) == before, f"a {why} bet moved the balance"
        print(f"  bet {bet:>4} ({why:18}) -> {message[:40]!r}")

    await db.set_balance(U, G, 50)
    before = await db.get_balance(U, G)
    message = await casino.play_slots(U, G, 5_000)
    assert await db.get_balance(U, G) == before, "betting more than you own moved the balance"
    print(f"  betting 5,000 on a 50 balance -> {message[:45]!r}")

    print("\n=== his tables feed the gamble_coins quest counter too ===")
    await db.set_balance(U, G, 50_000)
    await db.set_player_quest_status(U, G, "daily_gamble", "active")
    before_progress = await db.get_quest_progress(U, G, "daily_gamble")
    await casino.play_coinflip(U, G, 300, "heads")
    after_progress = await db.get_quest_progress(U, G, "daily_gamble")
    print(f"  gamble_coins {before_progress} -> {after_progress}")
    assert after_progress == before_progress + 300, \
        "gambling at the casino doesn't count toward gambling quests"

    print("\n=== a house doesn't boost his tables either ===")
    await db.set_player_house(U, G, "mansion")
    for trial in range(3):
        await db.set_balance(U, G, 50_000)
        before = await db.get_balance(U, G)
        random.seed(SEED + trial)
        expected = C.coinflip_payout(1_000, won=C.coinflip_flip(random) == "heads")
        random.seed(SEED + trial)
        await casino.play_coinflip(U, G, 1_000, "heads")
        actual = await db.get_balance(U, G) - before
        print(f"  mansion owner -> expected {expected:+7}, got {actual:+7}")
        assert actual == expected, "the house boost reached the casino"

    print("\n=== he has quests, and they use condition types the engine knows ===")
    from cogs.quests import CONDITION_CHECKERS, accept_quest, turn_in_quest
    quests = await db.get_quests_for_npc(casino.CASINO_ID)
    print(f"  {len(quests)} quests")
    assert len(quests) >= 2, "the casino owner has nothing to offer"
    for q in quests:
        print(f"    {q['quest_id']:16} {q['condition_type']:14} "
              f"{q['condition_amount']:>6}  pays {q['reward_coins']}  rep={bool(q['repeatable'])}")
        assert q["condition_type"] in CONDITION_CHECKERS, \
            f"{q['quest_id']} uses an unknown condition {q['condition_type']!r}"

    print("\n=== a gambling quest completes by actually gambling at his tables ===")
    gambling = [q for q in quests if q["condition_type"] == "gamble_coins"]
    assert gambling, "none of his quests are about gambling, which is his whole thing"
    quest = gambling[0]

    await db.set_balance(U, G, 500_000)
    await db.clear_player_quest(U, G, quest["quest_id"])
    accepted = await accept_quest(U, G, quest["quest_id"])
    print(f"  accept: {accepted}")

    # Nothing wagered yet, so it must refuse.
    refused = await turn_in_quest(U, G, quest["quest_id"])
    print(f"  turn in at 0: {refused}")
    assert "Not done" in refused, "EXPLOIT: paid out before any gambling"

    target = quest["condition_amount"]
    staked = 0
    while staked < target:
        bet = min(1_000, target - staked)
        await casino.play_coinflip(U, G, bet, "heads")
        staked += bet
    print(f"  staked {staked:,} at his tables")

    before = await db.get_balance(U, G)
    done = await turn_in_quest(U, G, quest["quest_id"])
    print(f"  turn in: {done}")
    assert "complete" in done.lower(), f"quest wouldn't turn in: {done}"
    assert await db.get_balance(U, G) > before, "the quest paid nothing"

    await db.get_db().close()
    print("\ncasinonpccheck OK")


if __name__ == "__main__":
    asyncio.run(main())
