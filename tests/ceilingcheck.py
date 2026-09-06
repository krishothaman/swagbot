"""Raising MAX_SUCCESS to 88: is blown still reachable, and do the shown odds
still match what actually gets rolled?"""
import random, sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401
import heist_logic as L

print(f"MAX_SUCCESS={L.MAX_SUCCESS}  ROUGH_BAND={L.ROUGH_BAND}  BLOWN_FLOOR={L.BLOWN_FLOOR}")

print("\n=== blown must stay reachable at ANY chance, on every scoring stage ===")
N = 200000
for index in range(len(L.STAGES)):
    band, floor = L.stage_rough_band(index), L.stage_blown_floor(index)
    rng = random.Random(index + 1)
    blown = sum(1 for _ in range(N)
                if L.resolve_stage(L.MAX_SUCCESS, rng, band, floor)[0] == L.STAGE_BLOWN)
    pct = 100 * blown / N
    name = L.STAGES[index]["name"]
    print(f"  stage {index} ({name:18}) band={band:2} floor={floor} -> blown {pct:5.2f}%")
    if floor > 0:
        assert pct > 0, f"stage {index} can never be blown - guaranteed-win bug is back"
        assert abs(pct - floor) < 1.0, f"blown {pct:.2f}% but floor says {floor}%"
    else:
        assert pct == 0, f"stage {index} opted out of the floor but blew {pct}%"

print("\n=== the number on the button must equal the real blown rate ===")
worst = 0
for index in range(len(L.STAGES)):
    band, floor = L.stage_rough_band(index), L.stage_blown_floor(index)
    for chance in range(L.MIN_SUCCESS, L.MAX_SUCCESS + 1, 7):
        shown = L.blown_chance(chance, band, floor)
        rng = random.Random(99)
        hits = sum(1 for _ in range(40000)
                   if L.resolve_stage(chance, rng, band, floor)[0] == L.STAGE_BLOWN)
        actual = 100 * hits / 40000
        worst = max(worst, abs(shown - actual))
        assert abs(shown - actual) < 1.5, (
            f"stage {index} at {chance}%: shows {shown}% blown, really {actual:.2f}%")
print(f"  worst display-vs-reality gap across every stage and chance: {worst:.2f}%")

print("\n=== mid-range odds are unchanged (the band only shrinks near the top) ===")
for chance in (30, 50, 70, 80, 88):
    band = min(L.ROUGH_BAND, max(0, 100 - L.BLOWN_FLOOR - chance))
    print(f"  {chance:3}% clean -> band {band:2} -> {L.blown_chance(chance)}% blown")
assert L.blown_chance(50) == 35, "mid-range blown rate moved - that wasn't the intent"
assert L.blown_chance(30) == 55

print("\n=== gear now actually does something on stealth ===")
loaded = {"mask": 9, "c4": 9}
for approach in L.APPROACHES:
    for n in (1, 4):
        base = L.calculate_success(approach, [], n)
        kit = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, base + L.gear_bonus(loaded, approach)))
        print(f"  {approach:11} crew {n}: {base}% -> {kit}%  (+{kit-base})")
assert L.calculate_success("stealth", [], 1) + 3 <= L.MAX_SUCCESS, \
    "masks are still swallowed by the ceiling on solo stealth"

print("\nCEILING CHECKS PASSED")
