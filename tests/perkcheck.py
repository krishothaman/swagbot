"""House perks: does the boost math floor, does rent accrue and cap, and can a
never-collected ledger hand out free money?

Pure functions only - no database, no discord. `now` is injected everywhere so
the seven-day cap can be tested without waiting seven days.
"""
import sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import house_perks as P

DAY = 86400
NOW = 1_700_000_000.0   # arbitrary fixed clock


def main():
    print("=== the catalog covers every tier, and nothing else ===")
    assert set(P.HOUSE_PERKS) == {"studio", "apartment", "mansion"}, \
        f"perk table keys drifted: {sorted(P.HOUSE_PERKS)}"
    for house_id, perks in P.HOUSE_PERKS.items():
        print(f"  {house_id:10} rent {perks['rent']:>5}/day  "
              f"boost +{int(perks['boost'] * 100)}%  heist +{perks['heist']}")

    print("\n=== boost percentages are what was agreed ===")
    assert P.boost_percent("studio") == 5
    assert P.boost_percent("apartment") == 10
    assert P.boost_percent("mansion") == 20
    assert P.boost_percent(None) == 0, "no house must read as +0%, not a crash"
    assert P.boost_percent("cardboard_box") == 0, "unknown house must fail soft"

    print("\n=== apply_boost pays the base plus the cut, floored ===")
    for house_id, expected in (("studio", 105), ("apartment", 110), ("mansion", 120)):
        got = P.apply_boost(100, house_id)
        print(f"  100 coins in a {house_id:10} -> {got}")
        assert got == expected, f"{house_id}: expected {expected}, got {got}"

    assert P.apply_boost(100, None) == 100, "no house must pay exactly the base"
    assert P.apply_boost(0, "mansion") == 0, "zero stays zero"

    # Floors, never rounds up - a 55-coin /work in a studio is 57.75, not 58.
    assert P.apply_boost(55, "studio") == 57, "boost must floor, not round"
    assert isinstance(P.apply_boost(55, "studio"), int), "coins must stay whole"

    # Small payouts must never be *reduced* by the boost.
    for amount in range(0, 40):
        for house_id in (None, "studio", "apartment", "mansion"):
            assert P.apply_boost(amount, house_id) >= amount, \
                f"boost shrank {amount} in a {house_id}"

    print("\n=== rent accrues by whole elapsed days, capped at 7 ===")
    for days in (0, 0.9, 1, 3, 3.5, 7, 8, 30, 365):
        got = P.days_accrued(NOW - days * DAY, now=NOW)
        print(f"  {days:>5} days elapsed -> {got} day(s) owed")
        assert got == min(int(days), P.RENT_CAP_DAYS), f"{days} days -> {got}"

    assert P.days_accrued(NOW - 30 * DAY, now=NOW) == 7, "the 7-day cap leaks"

    print("\n=== a never-collected ledger owes NOTHING ===")
    # last_collect defaults to 0 in the database. `now - 0` is ~54 years, which
    # a naive implementation pays out as the full 7-day cap the instant anyone
    # buys a house. This is the whole reason days_accrued special-cases it.
    assert P.days_accrued(0, now=NOW) == 0, "an unstamped ledger paid out free rent"
    assert P.days_accrued(None, now=NOW) == 0, "a null ledger paid out free rent"
    assert P.rent_owed("mansion", 0, now=NOW) == 0, "unstamped mansion paid free rent"
    print("  stamp of 0    -> 0 days")
    print("  stamp of None -> 0 days")

    # Clock skew must not pay either.
    assert P.days_accrued(NOW + 5 * DAY, now=NOW) == 0, "a future stamp paid rent"
    print("  future stamp  -> 0 days")

    print("\n=== rent_owed is rate x days ===")
    for house_id in P.HOUSE_PERKS:
        rate = P.rent_rate(house_id)
        for days in (1, 3, 7, 99):
            owed = P.rent_owed(house_id, NOW - days * DAY, now=NOW)
            assert owed == rate * min(days, P.RENT_CAP_DAYS)
        print(f"  {house_id:10} 3 days -> {P.rent_owed(house_id, NOW - 3 * DAY, now=NOW):,} coins"
              f"   (max ever {rate * P.RENT_CAP_DAYS:,})")

    assert P.rent_owed(None, NOW - 3 * DAY, now=NOW) == 0, "the homeless collected rent"
    assert P.rent_rate(None) == 0

    print("\n=== collecting advances the ledger without eating the part-day ===")
    # After collecting, whatever fraction of a day hadn't matured yet must
    # still be on the clock - otherwise collecting at 3.5 days silently costs
    # you half a day, and a player who collects often is punished for it.
    for elapsed, expect_left in ((1.0, 0.0), (3.5, 0.5), (6.99, 0.99)):
        new_stamp = P.advance_stamp(NOW - elapsed * DAY, now=NOW)
        left = (NOW - new_stamp) / DAY
        print(f"  {elapsed:>5} days elapsed -> {left:.2f} days still on the clock")
        assert abs(left - expect_left) < 0.01, f"{elapsed}: carried {left:.2f}, wanted {expect_left}"
        assert new_stamp <= NOW, "the ledger was advanced into the future"

    # Past the cap the surplus is forfeited - that is what a cap means. The
    # ledger must land at ~now, or the uncollected days stay collectable and
    # the cap does nothing.
    for elapsed in (8, 30, 365):
        new_stamp = P.advance_stamp(NOW - elapsed * DAY, now=NOW)
        left = (NOW - new_stamp) / DAY
        print(f"  {elapsed:>5} days elapsed -> {left:.2f} days still on the clock (capped)")
        assert left < 1.0, f"{elapsed} days left {left:.2f} days collectable past the cap"
        assert P.days_accrued(new_stamp, now=NOW) == 0, "could collect again immediately"

    assert P.advance_stamp(0, now=NOW) == NOW, "an unstamped ledger must open at now"

    print("\n=== mansion heist bonus is flat and does NOT stack ===")
    cases = [
        ([], 0),
        ([None, None], 0),
        (["studio"], 0),
        (["studio", "apartment"], 0),
        (["mansion"], 2),
        (["mansion", "studio", None], 2),
        (["mansion", "mansion"], 2),
        (["mansion"] * 6, 2),
    ]
    for house_ids, expected in cases:
        got = P.house_heist_bonus(house_ids)
        print(f"  crew {str(house_ids):40} -> +{got}")
        assert got == expected, f"{house_ids}: expected +{expected}, got +{got}"

    print("\nperkcheck OK")


if __name__ == "__main__":
    main()
