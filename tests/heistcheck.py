import os, random, sys, tempfile, asyncio
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import heist_logic as L
from config import HEIST_BASE_PAYOUT_MIN as LO, HEIST_BASE_PAYOUT_MAX as HI

print("=== odds ===")
for key in L.APPROACHES:
    solo = L.calculate_success(key, [])
    full = L.calculate_success(key, list(L.NPC_CREW))
    print(f"{key:11} solo={solo:3}%  full crew={full:3}%")
    assert L.MIN_SUCCESS <= solo <= L.MAX_SUCCESS
    assert L.MIN_SUCCESS <= full <= L.MAX_SUCCESS
    assert full >= solo, "crew should never make it worse"

# odds are capped - stacking must not reach certainty
assert L.calculate_success("stealth", list(L.NPC_CREW), 10) <= L.MAX_SUCCESS
print("capped at", L.MAX_SUCCESS, "even with max crew + 10 players: OK")

print("\n=== payout bands (1000 sims each, solo) ===")
rng = random.Random(42)
for key in L.APPROACHES:
    takes = [L.calculate_take(key, LO, HI, 1, rng) for _ in range(1000)]
    print(f"{key:11} {min(takes):5} - {max(takes):5}  avg {sum(takes)//len(takes):5}")

print("\n=== npc cuts ===")
take = 5000
for combo in ([], ["wheelman"], ["wheelman", "hacker"], list(L.NPC_CREW)):
    left, cut = L.apply_npc_cuts(take, combo)
    assert left + cut == take, "cuts must not create or destroy coins"
    assert left >= 0
    print(f"crew={len(combo)} cost={L.hire_cost(combo):5} -> you keep {left:5}, crew takes {cut:5}")

print("\n=== the real question: is a full crew actually worth it? ===")
rng = random.Random(7)
for key in L.APPROACHES:
    for combo in ([], list(L.NPC_CREW)):
        chance = L.calculate_success(key, combo)
        cost = L.hire_cost(combo)
        total = 0
        N = 20000
        for _ in range(N):
            outcome, _ = L.roll_outcome(chance, rng)
            gross = L.calculate_take(key, LO, HI, 1, rng)
            if outcome == L.SUCCESS:
                net, _ = L.apply_npc_cuts(gross, combo)
            elif outcome == L.MINOR_FAILURE:
                net, _ = L.apply_npc_cuts(L.minor_failure_take(gross), combo)
            else:
                net = 0
            total += net - cost
        ev = total / N
        print(f"{key:11} crew={len(combo)} chance={chance:3}%  EV per heist = {ev:8.0f}")

print("\n=== outcome distribution (stealth solo, 100k) ===")
rng = random.Random(1)
chance = L.calculate_success("stealth", [])
counts = {}
for _ in range(100000):
    o, _ = L.roll_outcome(chance, rng)
    counts[o] = counts.get(o, 0) + 1
for k, v in sorted(counts.items()):
    print(f"  {k:14} {v/1000:5.1f}%")
assert abs(counts[L.SUCCESS] / 1000 - chance) < 1.0, "success rate doesn't match stated odds"
print("observed success matches advertised odds: OK")

print("\n=== split ===")
assert L.split_between_players(1000, 3) == 333
assert L.split_between_players(1000, 0) == 0
assert L.split_between_players(1000, 1) == 1000
print("splits round down, no coin minting: OK")

print("\nALL HEIST LOGIC CHECKS PASSED")
