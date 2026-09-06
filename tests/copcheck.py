import random, sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401
import heist_logic as L
from config import (HEIST_BASE_PAYOUT_MIN as LO, HEIST_BASE_PAYOUT_MAX as HI,
                    HEIST_BUY_IN, WORK_MIN_REWARD, WORK_MAX_REWARD, DAILY_REWARD)

print("=== the board fits inside Discord's limits ===")
for n in (1, 6):
    cells = L.build_grid(n)
    assert len(cells) == L.GRID_CELLS, len(cells)
    components = L.GRID_CELLS + 1  # + Take Cover
    assert components <= 25, f"{components} components, Discord allows 25"
    cops = sum(1 for c in cells if c == L.CELL_COP)
    civs = sum(1 for c in cells if c == L.CELL_BYSTANDER)
    print(f"  {n} player(s): {cops} cops, {civs} civilians, "
          f"{L.GRID_CELLS - cops - civs} empty, {components} components")
assert L.GRID_ROWS * L.GRID_COLS + 1 <= 25

print("\n=== cops scale with the crew ===")
for n in (1, 2, 4, 6):
    print(f"  {n} players -> {L.cop_count(n)} cops")
assert L.cop_count(6) > L.cop_count(1)

print("\n=== shots come from what you carry ===")
for loadout, label in (([], "unarmed"), (["p250"], "P250"),
                       (["five_seven"], "Five-seveN"), (["p250", "five_seven"], "both")):
    print(f"  {label:12} -> {L.shots_for(loadout)} shots")
assert L.shots_for([]) == 0
assert L.shots_for(["five_seven"]) > L.shots_for(["p250"]), "the 7500 gun must beat the 5000 one"

print("\n=== grading the firefight ===")
total = 6
for down, civ in ((6, 0), (6, 1), (4, 0), (2, 0), (0, 0), (3, 3)):
    print(f"  {down}/{total} cops, {civ} civilians hit -> {L.cop_result(down, civ, total)}")
assert L.cop_result(6, 0, 6) == L.COP_CLEAN
assert L.cop_result(6, 1, 6) != L.COP_CLEAN, "hitting a civilian must cost the clean rating"
assert L.cop_result(0, 0, 6) == L.COP_OVERRUN

print("\n=== NOBODY dies except on overrun, and never more than one ===")
rng = random.Random(1)
crew = [1, 2, 3, 4, 5, 6]
for result in (L.COP_CLEAN, L.COP_HELD, L.COP_PUSHED):
    for _ in range(500):
        assert L.cop_casualties(result, crew, rng) == [], f"{result} put someone down"
print("  clean/held/pushed: nobody hit")

for _ in range(2000):
    hit = L.cop_casualties(L.COP_OVERRUN, crew, rng)
    assert len(hit) <= L.MAX_CASUALTIES, f"{len(hit)} casualties - max is {L.MAX_CASUALTIES}"
print(f"  overrun: never more than {L.MAX_CASUALTIES} casualty across 2000 rolls")

covered_crew = []
assert L.cop_casualties(L.COP_OVERRUN, covered_crew, rng) == [], \
    "someone got hit when the whole crew was behind cover"
print("  a fully covered crew takes no casualties")

print("\n=== surviving the cops helps the escape, getting hurt hurts it ===")
for result in (L.COP_CLEAN, L.COP_HELD, L.COP_PUSHED, L.COP_OVERRUN):
    clean = L.cop_escape_modifier(result, False)
    shot = L.cop_escape_modifier(result, True)
    print(f"  {result:8} escape {clean:+3}  (with a casualty: {shot:+3})  "
          f"loot x{L.cop_loot_multiplier(result):.2f}")
assert L.cop_escape_modifier(L.COP_CLEAN, False) > 0
assert L.cop_escape_modifier(L.COP_OVERRUN, False) < 0
assert L.cop_escape_modifier(L.COP_CLEAN, True) < L.cop_escape_modifier(L.COP_CLEAN, False)


def simulate(approach, npcs, n, policy, cop_skill, rng):
    """Full pipeline including the cop stage. cop_skill 0..1 = fraction of
    cops the crew manages to drop."""
    chance = L.calculate_success(approach, npcs, n)
    gross = L.calculate_take(approach, LO, HI, n, rng)
    cost = L.per_player_cost(HEIST_BUY_IN, npcs, n)
    loot = 1.0
    for i in range(len(L.STAGES)):
        keys = list(L.STAGES[i]["choices"])
        ck = keys[0] if policy == "safe" else keys[1]
        choice = L.stage_choice(i, ck)
        sc = chance + L.stage_bonus(i) + choice["success"]
        result, roll = L.resolve_stage(sc, rng, band=L.stage_rough_band(i))
        if result == L.STAGE_BLOWN:
            take = L.blown_take(i, int(gross * loot * choice["loot"]))
            net, _ = L.apply_npc_cuts(take, npcs)
            return L.split_between_players(net, n) - cost
        loot *= choice["loot"]
        chance = (max(L.MIN_SUCCESS, sc - 10) if result == L.STAGE_ROUGH
                  else min(L.MAX_SUCCESS, sc))
        if result == L.STAGE_ROUGH:
            loot *= 0.85

        if i == len(L.STAGES) - 2:   # cops, after the vault
            cops = L.cop_count(n)
            down = int(cops * cop_skill)
            res = L.cop_result(down, 0, cops)
            loot *= L.cop_loot_multiplier(res)
            chance = max(L.MIN_SUCCESS,
                         min(L.MAX_SUCCESS, chance + L.cop_escape_modifier(res, False)))
    net, _ = L.apply_npc_cuts(int(gross * loot), npcs)
    return L.split_between_players(net, n) - cost


N = 20000
print("\n=== EV per person, full pipeline with the new payout ===")
print(f"{'approach':11} {'players':>7} {'cops down':>10} {'EV/person':>10}")
for approach in L.APPROACHES:
    for n in (1, 4):
        for skill, label in ((1.0, "all"), (0.6, "most"), (0.0, "none")):
            rng = random.Random(21)
            ev = sum(simulate(approach, [], n, "safe", skill, rng) for _ in range(N)) / N
            print(f"{approach:11} {n:7} {label:>10} {ev:10.0f}")

print("\n=== how the heist compares to everything else ===")
rng = random.Random(5)
def _ev(a, npcs, p, n=5000):
    # One rng for the whole sample. Re-seeding inside the comprehension makes
    # every iteration identical, which turns this average into a single run.
    r = random.Random(9)
    return sum(simulate(a, npcs, 1, p, 1.0, r) for _ in range(n)) / n


best_ev = max(_ev(a, npcs, p)
              for a in L.APPROACHES for npcs in ([], list(L.NPC_CREW))
              for p in ("safe", "risky"))
work_avg = (WORK_MIN_REWARD + WORK_MAX_REWARD) / 2
print(f"  best solo heist EV : {best_ev:,.0f} coins")
print(f"  one /work          : {work_avg:,.0f} coins   ({best_ev/work_avg:.0f}x a work)")
print(f"  one /daily         : {DAILY_REWARD:,.0f} coins   ({best_ev/DAILY_REWARD:.0f}x a daily)")
print(f"  buy-in             : {HEIST_BUY_IN:,} coins   "
      f"({best_ev/HEIST_BUY_IN:.0f}x the stake)")
print(f"  Mansion (tier 3)   : 60,000 coins  ({60000/best_ev:.1f} heists)")
print(f"  Five-seveN         : 7,500 coins   ({7500/best_ev:.1f} heists)")

print("\n=== a losing run must still actually lose money ===")
rng = random.Random(77)
worst = min(simulate("force", list(L.NPC_CREW), 1, "risky", 0.0, rng) for _ in range(20000))
print(f"  worst single run: {worst:,} coins")
assert worst < 0, "no run ever loses money - there is no risk left"

print("\nCOP + PAYOUT CHECKS PASSED")
