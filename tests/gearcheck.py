"""Masks and C4: do they help, are they capped, and is C4 actually consumed?"""
import asyncio, os, random, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import config
config.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
import database as db
db.DB_PATH = config.DB_PATH
import heist_logic as L
from config import (HEIST_BASE_PAYOUT_MIN as LO, HEIST_BASE_PAYOUT_MAX as HI,
                    HEIST_BUY_IN)

GUILD = 1


def main_sync():
    print("=== masks: +1 each, hard cap +3 ===")
    for n in (0, 1, 2, 3, 5, 9):
        b = L.gear_bonus({"mask": n}, "force")
        print(f"  {n} masks -> +{b}")
    assert L.gear_bonus({"mask": 3}, "force") == 3
    assert L.gear_bonus({"mask": 9}, "force") == 3, "mask cap leaks"

    print("\n=== C4 depends on the approach ===")
    for approach in L.APPROACHES:
        row = [L.gear_bonus({"c4": n}, approach) for n in (0, 1, 2, 5)]
        print(f"  {approach:11} 0/1/2/5 C4 -> {row}")
    assert L.gear_bonus({"c4": 5}, "stealth") == 0, "C4 must do nothing on stealth"
    assert L.gear_bonus({"c4": 1}, "force") > L.gear_bonus({"c4": 1}, "inside_job")

    print("\n=== guns give NO general odds bonus (they're ammo, not luck) ===")
    for gun in L.GUN_SHOTS:
        assert L.gear_bonus({gun: 3}, "force") == 0, f"{gun} leaked into gear_bonus"
        print(f"  {gun:11} -> +0 odds, {L.GUN_SHOTS[gun]} shots")

    print("\n=== you only burn C4 that actually did something ===")
    for approach in L.APPROACHES:
        for held in (0, 1, 3, 10):
            spent = L.c4_spent({"c4": held}, approach)
            bonus = L.gear_bonus({"c4": held}, approach)
            assert spent <= held, "spent more C4 than the crew owned"
            if bonus == 0:
                assert spent == 0, f"burned {spent} C4 on {approach} for +0"
        print(f"  {approach:11} holding 10 -> burns {L.c4_spent({'c4': 10}, approach)}")

    print("\n=== gear can't break the success ceiling ===")
    loaded = {"mask": 9, "c4": 9}
    for approach in L.APPROACHES:
        base = L.calculate_success(approach, list(L.NPC_CREW), 6)
        total = min(L.MAX_SUCCESS, base + L.gear_bonus(loaded, approach))
        print(f"  {approach:11} {base}% -> {total}% fully kitted")
        assert total <= L.MAX_SUCCESS, "gear broke MAX_SUCCESS"

    print("\n=== a fully kitted crew must STILL be able to lose money ===")

    def simulate(approach, npcs, n, policy, gear, rng):
        chance = L.calculate_success(approach, npcs, n)
        chance = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, chance + L.gear_bonus(gear, approach)))
        gross = L.calculate_take(approach, LO, HI, n, rng)
        cost = L.per_player_cost(HEIST_BUY_IN, npcs, n)
        loot = 1.0
        for i in range(len(L.STAGES)):
            keys = list(L.STAGES[i]["choices"])
            ck = keys[0] if policy == "safe" else keys[1]
            choice = L.stage_choice(i, ck)
            sc = chance + L.stage_bonus(i) + choice["success"]
            result, _ = L.resolve_stage(sc, rng, band=L.stage_rough_band(i))
            if result == L.STAGE_BLOWN:
                take = L.blown_take(i, int(gross * loot * choice["loot"]))
                net, _ = L.apply_npc_cuts(take, npcs)
                return L.split_between_players(net, n) - cost
            loot *= choice["loot"]
            chance = (max(L.MIN_SUCCESS, sc - 10) if result == L.STAGE_ROUGH
                      else min(L.MAX_SUCCESS, sc))
            if result == L.STAGE_ROUGH:
                loot *= 0.85
            if i == len(L.STAGES) - 2:
                cops = L.cop_count(n)
                res = L.cop_result(cops, 0, cops)
                loot *= L.cop_loot_multiplier(res)
                chance = max(L.MIN_SUCCESS,
                             min(L.MAX_SUCCESS, chance + L.cop_escape_modifier(res, False)))
        net, _ = L.apply_npc_cuts(int(gross * loot), npcs)
        return L.split_between_players(net, n) - cost

    rng = random.Random(77)
    worst = min(simulate("force", list(L.NPC_CREW), 1, "risky", loaded, rng)
                for _ in range(20000))
    print(f"  worst run, fully kitted: {worst:,} coins")
    assert worst < 0, "gear made the heist risk-free - there is no downside left"

    N = 8000
    print("\n=== what gear is worth per person (EV) ===")
    print(f"{'approach':11} {'crew':>5} {'bare':>9} {'kitted':>9} {'delta':>8}")
    for approach in L.APPROACHES:
      for crew_n in (1, 4):
        # ONE rng for the whole run. Constructing random.Random(seed) inside the
        # comprehension reseeds every iteration, so all N runs come out identical
        # and the "average" is really a single deterministic run.
        r1 = random.Random(3)
        bare = sum(simulate(approach, [], crew_n, "safe", {}, r1) for _ in range(N)) / N
        r2 = random.Random(3)
        kit = sum(simulate(approach, [], crew_n, "safe", loaded, r2) for _ in range(N)) / N
        base_pct = L.calculate_success(approach, [], crew_n)
        kit_pct = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, base_pct + L.gear_bonus(loaded, approach)))
        print(f"{approach:11} {crew_n:5} {bare:9.0f} {kit:9.0f} {kit-bare:+8.0f}"
              f"   ({base_pct}% -> {kit_pct}%)")


async def main_db():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()

    print("\n=== the mask is a real, buyable item ===")
    row = await db.get_item("mask")
    assert row, "mask was not seeded"
    print(f"  {row[1]} - {row[2]} coins, sold by {row[3]}")

    print("\n=== C4 is consumed, guns never are ===")
    from cogs.heist import collect_gear, spend_c4

    class G:
        id = GUILD

    crew = [101, 102]
    for pid in crew:
        await db.ensure_user(pid, GUILD)
        await db.add_item_to_inventory(pid, GUILD, "mask", 1)
        await db.add_item_to_inventory(pid, GUILD, "c4", 2)
    await db.add_item_to_inventory(crew[0], GUILD, "p250", 1)

    counts = await collect_gear(G, crew)
    print(f"  crew carrying: {counts}")
    assert counts["mask"] == 2 and counts["c4"] == 4 and counts["p250"] == 1

    spent = L.c4_spent(counts, "force")
    await spend_c4(G, crew, spent)
    after = await collect_gear(G, crew)
    print(f"  after burning {spent}: {after}")
    assert after["c4"] == counts["c4"] - spent, "C4 count is wrong after the job"
    assert after["mask"] == 2, "masks were consumed - they must be permanent"
    assert after["p250"] == 1, "a gun was consumed - guns are permanent"

    print("\n=== stealth burns nothing ===")
    before = (await collect_gear(G, crew))["c4"]
    await spend_c4(G, crew, L.c4_spent(await collect_gear(G, crew), "stealth"))
    assert (await collect_gear(G, crew))["c4"] == before, "stealth ate the C4"
    print(f"  still holding {before} C4")

    await db.get_db().close()


main_sync()
asyncio.run(main_db())
print("\nGEAR CHECKS PASSED")
