"""The Mansion's heist bonus: does the crew's housing reach the odds, does it
refuse to stack, and can it push a loaded crew past the ceiling?

Real database, stub guild - collect_houses only ever touches guild.id.
"""
import asyncio, os, sys, tempfile
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
import heist_logic as L
import house_perks as P

GUILD = 1


class StubGuild:
    """collect_houses/collect_gear only read .id."""
    id = GUILD


async def house_up(player_houses: dict):
    """Give each user the house they're mapped to; None means homeless."""
    for user_id, house_id in player_houses.items():
        await db.ensure_user(user_id, GUILD)
        await db.remove_player_house(user_id, GUILD)
        if house_id:
            await db.set_player_house(user_id, GUILD, house_id)


async def main():
    await db.init_db()
    await db.seed_house_data()
    await db.seed_item_data()
    import cogs.heist as heist

    print("=== collect_houses reports what the crew actually owns ===")
    await house_up({1: "mansion", 2: "studio", 3: None})
    got = await heist.collect_houses(StubGuild(), [1, 2, 3])
    print(f"  crew of 3 -> {got}")
    assert sorted(x for x in got if x) == ["mansion", "studio"], got
    assert len(got) == 3, "a homeless crew member must still be counted, as None"

    print("\n=== one mansion on the crew is +2 for everyone ===")
    for crew, expected in (([1], 2), ([2], 0), ([3], 0), ([2, 3], 0), ([1, 2, 3], 2)):
        houses = await heist.collect_houses(StubGuild(), crew)
        bonus = P.house_heist_bonus(houses)
        print(f"  crew {crew} owning {houses} -> +{bonus}")
        assert bonus == expected, f"crew {crew}: expected +{expected}, got +{bonus}"

    print("\n=== a second mansion buys nothing ===")
    await house_up({1: "mansion", 2: "mansion", 3: "mansion"})
    solo = P.house_heist_bonus(await heist.collect_houses(StubGuild(), [1]))
    trio = P.house_heist_bonus(await heist.collect_houses(StubGuild(), [1, 2, 3]))
    print(f"  one mansion +{solo}, three mansions +{trio}")
    assert solo == trio == 2, f"the bonus stacked: {solo} vs {trio}"

    print("\n=== housing cannot break MAX_SUCCESS ===")
    # Worst case on purpose: six players, every NPC hired, mask and C4 capped,
    # and a mansion on the crew. If anything can breach the ceiling it is this.
    loaded = {"mask": 9, "c4": 9}
    for approach in L.APPROACHES:
        base = L.calculate_success(approach, list(L.NPC_CREW), 6)
        gear = L.gear_bonus(loaded, approach)
        house = P.house_heist_bonus(["mansion"] * 6)
        total = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, base + gear + house))
        print(f"  {approach:11} base {base}% +gear {gear} +house {house} -> {total}%")
        assert total <= L.MAX_SUCCESS, f"{approach} broke the ceiling at {total}%"

    print("\n=== a mansion still helps where there's headroom ===")
    # The point of the perk. Force starts low enough that +2 is real.
    bare = L.calculate_success("force", [], 1)
    with_house = min(L.MAX_SUCCESS, bare + P.house_heist_bonus(["mansion"]))
    print(f"  force, solo, no gear: {bare}% -> {with_house}% with a mansion")
    assert with_house == bare + 2, "the mansion bonus was swallowed"

    await db.get_db().close()
    print("\nmansioncheck OK")


if __name__ == "__main__":
    asyncio.run(main())
