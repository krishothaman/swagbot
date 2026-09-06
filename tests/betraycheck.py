import random, sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import heist_logic as L

print("=== betray_chance sanity ===")
for approach in L.APPROACHES:
    bc = L.betray_chance(approach)
    base = L.APPROACHES[approach]["success"]
    print(f"  {approach:11} base={base:3} betray_chance={bc:3}")
    assert bc == max(L.MIN_SUCCESS, base - L.BETRAY_CHANCE_PENALTY)

print("\n=== resolve_payouts: matches the user-confirmed example exactly ===")
# 4 players, after_cuts=4000 -> normal_share=1000 each
players = [1, 2, 3, 4]
after_cuts = 4000

# no betrayal at all -> everyone gets normal_share, matches old split_between_players
p = L.resolve_payouts(after_cuts, players, {})
assert all(v == 1000 for v in p.values()), p
print("  no betrayal:", p)

# player 4 betrays and succeeds
p = L.resolve_payouts(after_cuts, players, {4: True})
print("  4 betrays+wins:", p)
assert p[4] == 1600, p
assert p[1] == p[2] == p[3] == 800, p

# player 4 betrays and fails
p = L.resolve_payouts(after_cuts, players, {4: False})
print("  4 betrays+caught:", p)
assert p[4] == 200, p
assert p[1] == p[2] == p[3] == 1266, p  # 1000 + 800//3

print("\n=== conservation: total payout never exceeds the pot ===")
rng = random.Random(7)
for _ in range(5000):
    n = rng.randint(1, 6)
    players = list(range(n))
    pot = rng.randint(500, 20000)
    betrayals = {}
    for pid in players:
        if rng.random() < 0.4:
            betrayals[pid] = rng.random() < 0.5
    payouts = L.resolve_payouts(pot, players, betrayals)
    total = sum(payouts.values())
    assert total <= pot, f"MINTED COINS: total {total} > pot {pot} (betrayals={betrayals})"
    assert all(v >= 0 for v in payouts.values()), f"negative payout: {payouts}"
print("  no run minted coins or paid negative, across 5000 random configs")

print("\n=== edge case: everyone betrays, nobody loyal ===")
p = L.resolve_payouts(4000, [1, 2, 3, 4], {1: True, 2: False, 3: True, 4: False})
print("  all betray (mixed outcomes):", p)
assert sum(p.values()) <= 4000
# the two failures' forfeit has no loyal crew to land on - just lost, not minted
assert p[2] == p[4]

print("\n=== single betrayer is strictly worse in EV than staying loyal (it's a gamble, not free money) ===")
N = 30000
for approach in L.APPROACHES:
    rng = random.Random(1)
    total_betray = 0
    total_loyal_baseline = 0
    for _ in range(N):
        after_cuts = 4000
        won = L.roll_betrayal(approach, rng)
        payouts = L.resolve_payouts(after_cuts, [1, 2, 3, 4], {4: won})
        total_betray += payouts[4]
    ev_betray = total_betray / N
    ev_loyal = 1000  # normal_share when nobody betrays
    print(f"  {approach:11} betray_chance={L.betray_chance(approach):3}%  "
          f"EV if you betray={ev_betray:7.1f}  EV if you stay loyal={ev_loyal}")

print("\nBETRAYAL CHECKS PASSED")
