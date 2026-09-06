import random, sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401
import heist_logic as L

print("=== what a displayed 80% actually meant, per choice ===")
chance = 80
for i, stage in enumerate(L.STAGES):
    print(f"\n{stage['name']} (crew odds showing {chance}%)")
    for key, data in stage["choices"].items():
        odds = L.choice_odds(chance, i, key)
        band = L.stage_rough_band(i)
        print(f"  {data['label']:22} rolls at {odds:3}%  -> {L.blown_chance(odds, band):2}% blown, "
              f"{min(100, 100 - odds) - L.blown_chance(odds, band):2}% rough  (band {band})")

print("\n=== the displayed number must equal the number rolled ===")
# resolve_stage applies its own clamp; choice_odds has to reproduce it exactly
# or the UI is lying again in a new way.
rng = random.Random(5)
for _ in range(20000):
    base = rng.randint(-30, 130)
    i = rng.randrange(len(L.STAGES))
    key = rng.choice(list(L.STAGES[i]["choices"]))
    shown = L.choice_odds(base, i, key)

    # exactly what cogs/heist.py hands to resolve_stage
    raw = base + L.stage_bonus(i) + L.stage_choice(i, key)["success"]
    clamped_by_resolve = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, raw))
    assert shown == clamped_by_resolve, f"display {shown} != rolled {clamped_by_resolve}"

print("  display matches the rolled chance across 20k random states")

print("\n=== blown_chance must match observed failure rate ===")
for shown in (5, 20, 35, 50, 65, 80):
    rng = random.Random(shown)
    N = 200000
    blown = sum(1 for _ in range(N) if L.resolve_stage(shown, rng)[0] == L.STAGE_BLOWN)
    predicted = L.blown_chance(shown)
    observed = blown / N * 100
    print(f"  at {shown:3}%: predicted {predicted:2}% blown, observed {observed:5.2f}%")
    assert abs(observed - predicted) < 0.5, f"blown_chance wrong at {shown}"

print("\n=== so: was getting blown at 80% actually possible? ===")
rng = random.Random(1)
N = 200000
best = 80  # MAX_SUCCESS, the highest the crew odds can ever display
safe_escape = L.choice_odds(best, 2, "light")
risky_escape = L.choice_odds(best, 2, "heavy")
print(f"  showing {best}%, safe escape rolls {safe_escape}% -> {L.blown_chance(safe_escape)}% blown")
print(f"  showing {best}%, risky escape rolls {risky_escape}% -> {L.blown_chance(risky_escape)}% blown")
assert L.blown_chance(safe_escape) > 0, "max odds should still carry real risk"

print("\nODDS CHECKS PASSED")
