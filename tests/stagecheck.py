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

print("stages:", [s["name"] for s in L.STAGES])
assert len(L.STAGES) == 3


def simulate(approach, npc_ids, policy, rng, hesitate=False):
    """policy: 'safe' | 'risky'. Returns (outcome, player_take, got_shot)."""
    chance = L.calculate_success(approach, npc_ids)
    gross = L.calculate_take(approach, LO, HI, 1, rng)
    loot = 1.0
    for i in range(len(L.STAGES)):
        stage = L.STAGES[i]
        if hesitate:
            ckey = L.HESITATE
        else:
            keys = list(stage["choices"])
            ckey = keys[0] if policy == "safe" else keys[1]
        choice = L.stage_choice(i, ckey)
        sc = chance + L.stage_bonus(i) + choice["success"]
        result, roll = L.resolve_stage(sc, rng, band=L.stage_rough_band(i))
        if result == L.STAGE_BLOWN:
            sev = L.blown_severity(i, roll, sc)
            take = L.blown_take(i, int(gross * loot * choice["loot"]))
            net, _ = L.apply_npc_cuts(take, npc_ids)
            return sev, net, sev == L.BAD_FAILURE
        loot *= choice["loot"]
        if result == L.STAGE_ROUGH:
            chance = max(L.MIN_SUCCESS, sc - 10)
            loot *= 0.85
        else:
            chance = min(L.MAX_SUCCESS, sc)
    net, _ = L.apply_npc_cuts(int(gross * loot), npc_ids)
    return L.SUCCESS, net, False


N = 30000
print(f"\n{'approach':11} {'crew':4} {'policy':7} {'win%':>6} {'shot%':>6} {'EV':>8} {'maxpay':>7}")
for approach in L.APPROACHES:
    for npcs in ([], list(L.NPC_CREW)):
        for policy in ("safe", "risky"):
            rng = random.Random(11)
            wins = shots = total = 0
            best = 0
            cost = L.hire_cost(npcs)
            for _ in range(N):
                out, take, shot = simulate(approach, npcs, policy, rng)
                wins += out == L.SUCCESS
                shots += shot
                total += take - cost
                best = max(best, take)
            print(f"{approach:11} {len(npcs):4} {policy:7} {wins/N*100:5.1f}% "
                  f"{shots/N*100:5.1f}% {total/N:8.0f} {best:7}")

print("\n--- nothing may be a sure thing ---")
_r = random.Random(4242)
_blown = sum(1 for _ in range(100000)
             if L.resolve_stage(L.MAX_SUCCESS, _r, L.ROUGH_BAND, L.BLOWN_FLOOR)[0]
             == L.STAGE_BLOWN)
assert _blown > 0, "blown outcome is unreachable at max odds"
print(f"at max odds a stage still blows {100*_blown/100000:.2f}% of the time")
rng = random.Random(3)
best_combo = simulate  # best possible: stealth, full crew, all-safe
wins = sum(1 for _ in range(N) if simulate("stealth", list(L.NPC_CREW), "safe", rng)[0] == L.SUCCESS)
print(f"best possible configuration win rate: {wins/N*100:.1f}%")
assert wins < N, "a configuration wins 100% of the time"
assert wins/N < 0.95, f"best config wins {wins/N*100:.1f}% - too safe to be a gamble"

print("\n--- freezing up every stage must be clearly bad ---")
for approach in ("stealth", "force"):
    rng = random.Random(5)
    wins = sum(1 for _ in range(N) if simulate(approach, [], "safe", rng, hesitate=True)[0] == L.SUCCESS)
    rng = random.Random(5)
    wins_safe = sum(1 for _ in range(N) if simulate(approach, [], "safe", rng)[0] == L.SUCCESS)
    print(f"{approach:9} frozen={wins/N*100:5.1f}%  played={wins_safe/N*100:5.1f}%")
    assert wins < wins_safe, "hesitating is not punished!"

print("\n--- sanity: no negative payouts, no runaway jackpots ---")
rng = random.Random(99)
worst, best = 10**9, 0
for _ in range(200000):
    a = rng.choice(list(L.APPROACHES))
    out, take, _ = simulate(a, rng.sample(list(L.NPC_CREW), rng.randint(0, 3)), rng.choice(["safe","risky"]), rng)
    worst, best = min(worst, take), max(best, take)
assert worst >= 0, f"negative payout: {worst}"
print(f"payout range across 200k runs: {worst} .. {best}")
# Relative to the configured payout, not a hardcoded number - the old fixed
# 20000 bound silently became wrong the moment the base payout was raised.
# Ceiling is HI * best approach mult (1.4) * compounding risky loot (~1.87).
ceiling = HI * 3
assert best < ceiling, f"runaway payout {best} vs ceiling {ceiling} - compounding too hard"
print(f"max single payout {best} is within the {ceiling} ceiling")

print("\nSTAGE CHECKS PASSED")
