"""/coinflip and /slots must pay exactly what casino_logic says.

The point of casino_logic is that the Casino Owner hub and the slash commands
can't drift apart. That only holds if the commands actually route through it -
a second copy of the payout table left behind in cogs/games.py would pass
casinocheck.py and still be wrong in the game.

Also pins the rule that gambling wins are NOT boosted by your house.
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

U, G = 3, 9
SEED = 4242


class Response:
    def __init__(self):
        self.content = None
        self.embed = None

    async def send_message(self, content=None, embed=None, **kw):
        self.content, self.embed = content, embed


class Interaction:
    def __init__(self):
        self.user = type("U", (), {"id": U})()
        self.guild = type("G", (), {"id": G})()
        self.response = Response()


class Choice:
    def __init__(self, value):
        self.value = value


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()
    await db.seed_quest_data()

    from cogs.games import Games
    games = Games(None)
    await db.ensure_user(U, G)

    print("=== /slots pays exactly what casino_logic.slots_payout says ===")
    for trial in range(6):
        await db.set_balance(U, G, 100_000)
        before = await db.get_balance(U, G)

        # Same seed on both sides: whatever reel the command spins, the table
        # is asked about that same reel.
        random.seed(SEED + trial)
        expected_reel = C.spin(random)
        expected_payout, kind = C.slots_payout(expected_reel, 500)

        random.seed(SEED + trial)
        i = Interaction()
        await Games.slots.callback(games, i, 500)
        actual = await db.get_balance(U, G) - before

        print(f"  {expected_reel} {kind:8} -> expected {expected_payout:+6}, got {actual:+6}")
        assert actual == expected_payout, (
            f"/slots paid {actual:+}, casino_logic says {expected_payout:+} "
            f"- the command has its own payout table"
        )

    print("\n=== /coinflip pays exactly what casino_logic says ===")
    for trial in range(6):
        await db.set_balance(U, G, 100_000)
        before = await db.get_balance(U, G)

        random.seed(SEED + trial)
        expected_result = C.coinflip_flip(random)
        expected_payout = C.coinflip_payout(500, won=expected_result == "heads")

        random.seed(SEED + trial)
        i = Interaction()
        await Games.coinflip.callback(games, i, 500, Choice("heads"))
        actual = await db.get_balance(U, G) - before

        print(f"  landed {expected_result:6} -> expected {expected_payout:+6}, got {actual:+6}")
        assert actual == expected_payout, f"/coinflip paid {actual:+}, wanted {expected_payout:+}"

    print("\n=== a bad bet is refused and moves nothing ===")
    for bet, why in ((MIN_BET - 1, "under the minimum"), (0, "zero"), (-100, "negative")):
        await db.set_balance(U, G, 10_000)
        before = await db.get_balance(U, G)
        i = Interaction()
        await Games.slots.callback(games, i, bet)
        after = await db.get_balance(U, G)
        print(f"  bet {bet:>5} ({why:18}) -> {i.response.content!r:45} balance {before}->{after}")
        assert after == before, f"a {why} bet moved the balance"
        assert i.response.content and "inimum" in i.response.content, f"wrong refusal for {why}: {i.response.content!r}"

    await db.set_balance(U, G, 100)
    before = await db.get_balance(U, G)
    i = Interaction()
    await Games.slots.callback(games, i, 5_000)
    assert await db.get_balance(U, G) == before, "betting more than you own moved the balance"
    print(f"  betting 5,000 on a 100 balance -> {i.response.content!r}")

    print("\n=== gambling still feeds the gamble_coins quest counter ===")
    await db.set_balance(U, G, 100_000)
    await db.set_player_quest_status(U, G, "daily_gamble", "active")
    before_progress = await db.get_quest_progress(U, G, "daily_gamble")
    i = Interaction()
    await Games.slots.callback(games, i, 250)
    after_progress = await db.get_quest_progress(U, G, "daily_gamble")
    print(f"  gamble_coins progress {before_progress} -> {after_progress}")
    assert after_progress == before_progress + 250, "the quest counter stopped being fed"

    print("\n=== a house does NOT boost gambling winnings ===")
    # Locked decision: the earnings boost covers work, dailies and quests.
    # Routing a win through it would let a Mansion owner launder coins through
    # a coinflip at +20%, which is a much better rate than any honest job.
    await db.set_player_house(U, G, "mansion")
    for trial in range(4):
        await db.set_balance(U, G, 100_000)
        before = await db.get_balance(U, G)

        random.seed(SEED + trial)
        expected_reel = C.spin(random)
        expected_payout, kind = C.slots_payout(expected_reel, 1_000)

        random.seed(SEED + trial)
        i = Interaction()
        await Games.slots.callback(games, i, 1_000)
        actual = await db.get_balance(U, G) - before

        print(f"  mansion owner, {kind:8} -> expected {expected_payout:+7}, got {actual:+7}")
        assert actual == expected_payout, (
            f"the house boost reached a gambling payout: {actual:+} vs {expected_payout:+}"
        )

    await db.get_db().close()
    print("\ngamescheck OK")


if __name__ == "__main__":
    asyncio.run(main())
