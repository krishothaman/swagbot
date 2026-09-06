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
                    HEIST_BUY_IN)

print("=== vote tallying ===")
keys = ["quiet", "loud"]
assert L.tally_votes({}, keys) == L.HESITATE, "no votes should mean frozen"
assert L.tally_votes({1: "loud"}, keys) == "loud"
assert L.tally_votes({1: "loud", 2: "loud", 3: "quiet"}, keys) == "loud"
# tie must break to the SAFER (first) option
assert L.tally_votes({1: "loud", 2: "quiet"}, keys) == "quiet", "tie didn't break safe"
assert L.tally_votes({1: "garbage"}, keys) == L.HESITATE, "junk vote not ignored"
print("majority, safe tie-break, junk ignored, empty=frozen: OK")

print("\n=== per-player cost (crew fee splits) ===")
for n in (1, 2, 4, 6):
    for npcs in ([], list(L.NPC_CREW)):
        c = L.per_player_cost(HEIST_BUY_IN, npcs, n)
        print(f"  players={n} crew={len(npcs)} -> {c} each")
assert L.per_player_cost(HEIST_BUY_IN, list(L.NPC_CREW), 6) < \
       L.per_player_cost(HEIST_BUY_IN, list(L.NPC_CREW), 1), "bigger group should split the fee"


def simulate(approach, npcs, n_players, policy, rng):
    chance = L.calculate_success(approach, npcs, n_players)
    gross = L.calculate_take(approach, LO, HI, n_players, rng)
    cost = L.per_player_cost(HEIST_BUY_IN, npcs, n_players)
    loot = 1.0
    for i in range(len(L.STAGES)):
        stage = L.STAGES[i]
        ck = list(stage["choices"])[0 if policy == "safe" else 1]
        choice = L.stage_choice(i, ck)
        sc = chance + L.stage_bonus(i) + choice["success"]
        result, roll = L.resolve_stage(sc, rng, band=L.stage_rough_band(i))
        if result == L.STAGE_BLOWN:
            take = L.blown_take(i, int(gross * loot * choice["loot"]))
            net, _ = L.apply_npc_cuts(take, npcs)
            return L.split_between_players(net, n_players) - cost
        loot *= choice["loot"]
        if result == L.STAGE_ROUGH:
            chance = max(L.MIN_SUCCESS, sc - 10); loot *= 0.85
        else:
            chance = min(L.MAX_SUCCESS, sc)
    net, _ = L.apply_npc_cuts(int(gross * loot), npcs)
    return L.split_between_players(net, n_players) - cost


N = 20000
print("\n=== EV PER PERSON by crew size (safe play, full NPC crew) ===")
print(f"{'approach':11} {'players':>7} {'EV/person':>10} {'group total':>12}")
for approach in L.APPROACHES:
    for n in (1, 2, 4, 6):
        rng = random.Random(21)
        total = sum(simulate(approach, list(L.NPC_CREW), n, "safe", rng) for _ in range(N))
        ev = total / N
        print(f"{approach:11} {n:7} {ev:10.0f} {ev*n:12.0f}")

print("\n=== the key check: does grouping beat everyone soloing OPTIMALLY? ===")
# Baseline must be the best solo play available, not solo-with-a-full-crew
# (which is a trap config nobody picks - one person eating the whole crew fee).
best_solo, best_cfg = -10**9, None
for approach in L.APPROACHES:
    for npcs in ([], ["wheelman"], ["wheelman", "muscle"], list(L.NPC_CREW)):
        for policy in ("safe", "risky"):
            rng = random.Random(33)
            ev = sum(simulate(approach, npcs, 1, policy, rng) for _ in range(N)) / N
            if ev > best_solo:
                best_solo, best_cfg = ev, (approach, len(npcs), policy)
print(f"best solo play: {best_cfg} -> {best_solo:.0f}/heist")

print("(a mild grouping premium is fine and intended; runaway is not)")
worst_ratio = 0
for approach in L.APPROACHES:
    for n in (2, 4, 6):
        rng = random.Random(33)
        each = sum(simulate(approach, list(L.NPC_CREW), n, "safe", rng) for _ in range(N)) / N
        group_total, solo_total = each * n, best_solo * n
        ratio = group_total / solo_total
        worst_ratio = max(worst_ratio, ratio)
        flag = "OK" if ratio <= 1.3 else "INFLATION RISK"
        print(f"  {approach:11} n={n}: group={group_total:7.0f} vs {n}x best solo={solo_total:7.0f} "
              f"({ratio:4.2f}x) {flag}")
print(f"worst grouping premium: {worst_ratio:.2f}x")
assert worst_ratio <= 1.4, f"grouping mints coins at {worst_ratio:.2f}x best solo"

print("\n=== and is joining actually worth it? ===")
for approach in L.APPROACHES:
    rng = random.Random(44)
    solo = sum(simulate(approach, [], 1, "safe", rng) for _ in range(N)) / N
    rng = random.Random(44)
    four = sum(simulate(approach, [], 4, "safe", rng) for _ in range(N)) / N
    verdict = "worth joining" if four > solo * 0.8 else "JOINING IS BAD"
    print(f"  {approach:11} solo={solo:6.0f}  in a 4-crew={four:6.0f}  {verdict}")

print("\nLOBBY CHECKS PASSED")
