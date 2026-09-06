import random, sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401
import heist_logic as L
from config import HEIST_BASE_PAYOUT_MIN as LO, HEIST_BASE_PAYOUT_MAX as HI

print("=== chance of the job dying AT THE DOOR (stage 1), solo, no crew ===")
print(f"{'approach':11} {'choice':22} {'rolls at':>9} {'blown':>7}")
for approach in L.APPROACHES:
    base = L.calculate_success(approach, [], 1)
    for key, data in L.STAGES[0]["choices"].items():
        odds = L.choice_odds(base, 0, key)
        blown = L.blown_chance(odds, L.stage_rough_band(0))
        print(f"{approach:11} {data['label']:22} {odds:8}% {blown:6}%")

print("\n=== same for the stages that are SUPPOSED to be able to kill you ===")
for i in (1, 2):
    print(f"\n{L.STAGES[i]['name']} (band {L.stage_rough_band(i)})")
    for approach in L.APPROACHES:
        base = L.calculate_success(approach, [], 1)
        for key, data in L.STAGES[i]["choices"].items():
            odds = L.choice_odds(base, i, key)
            print(f"  {approach:11} {data['label']:22} {odds:3}% -> "
                  f"{L.blown_chance(odds, L.stage_rough_band(i)):2}% blown")


def simulate(approach, npcs, policy, rng):
    """Returns (outcome, stage_it_died_at or None)."""
    chance = L.calculate_success(approach, npcs, 1)
    gross = L.calculate_take(approach, LO, HI, 1, rng)
    loot = 1.0
    for i in range(len(L.STAGES)):
        keys = list(L.STAGES[i]["choices"])
        ck = keys[0] if policy == "safe" else keys[1]
        choice = L.stage_choice(i, ck)
        sc = chance + L.stage_bonus(i) + choice["success"]
        result, roll = L.resolve_stage(sc, rng, band=L.stage_rough_band(i))
        if result == L.STAGE_BLOWN:
            return L.blown_severity(i, roll, sc), i
        loot *= choice["loot"]
        if result == L.STAGE_ROUGH:
            chance = max(L.MIN_SUCCESS, sc - 10); loot *= 0.85
        else:
            chance = min(L.MAX_SUCCESS, sc)
    return L.SUCCESS, None


N = 40000
print("\n=== where do runs actually die now? ===")
print(f"{'approach':11} {'policy':7} {'win%':>6} {'die@entry':>10} {'die@vault':>10} {'die@escape':>11}")
for approach in L.APPROACHES:
    for policy in ("safe", "risky"):
        rng = random.Random(11)
        wins = 0
        died = {0: 0, 1: 0, 2: 0}
        for _ in range(N):
            out, stage = simulate(approach, [], policy, rng)
            if out == L.SUCCESS:
                wins += 1
            else:
                died[stage] += 1
        print(f"{approach:11} {policy:7} {wins/N*100:5.1f}% {died[0]/N*100:9.1f}% "
              f"{died[1]/N*100:9.1f}% {died[2]/N*100:10.1f}%")

print("\n=== the job as a whole must still be losable ===")
rng = random.Random(3)
wins = sum(1 for _ in range(N)
           if simulate("stealth", list(L.NPC_CREW), "safe", rng)[0] == L.SUCCESS)
print(f"  best configuration (stealth, full crew, all-safe) wins {wins/N*100:.1f}%")
assert wins < N, "a configuration never loses"
assert wins / N < 0.95, f"best config wins {wins/N*100:.1f}% - not a gamble anymore"

print("\n=== the LATER stages must still be able to end a run outright ===")
# The entry is deliberately exempt; these two are not. Measured rather than
# derived from the constants: resolve_stage now squeezes the rough band to keep
# blown reachable, so "MAX_SUCCESS + ROUGH_BAND < 100" is no longer what
# guarantees it. Rolling it out is the test that can't go stale.
for i in (1, 2):
    r = random.Random(500 + i)
    band, floor = L.stage_rough_band(i), L.stage_blown_floor(i)
    blown = sum(1 for _ in range(100000)
                if L.resolve_stage(L.MAX_SUCCESS, r, band, floor)[0] == L.STAGE_BLOWN)
    pct = 100 * blown / 100000
    assert pct > 0, f"stage {i} ({L.STAGES[i]['name']}) can never be blown at max odds"
    print(f"  stage {i} ({L.STAGES[i]['name']}) still blows {pct:.2f}% at max odds")

print("\n=== hesitating must still be punished at the entry ===")
frozen = L.choice_odds(50, 0, L.HESITATE)
safe = L.choice_odds(50, 0, "quiet")
assert frozen < safe, "freezing up is not worse than playing"
print(f"  at 50% base: froze={frozen}% vs played safe={safe}%")

print("\nENTRY TUNING CHECKS PASSED")
