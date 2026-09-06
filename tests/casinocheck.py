"""The casino's payout math, kept away from Discord so it can be reasoned about.

The Casino Owner hub has to run the games itself - a button can't invoke a
slash command - so the odds have to live somewhere both the hub and the
existing /coinflip and /slots can call. If they ever drift, the same game pays
differently depending on which door you came through.

Pure functions, injected rng.
"""
import random
import sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import casino_logic as C
from config import MIN_BET


class FixedRng:
    """Deterministic stand-in for random - returns queued choices in order."""
    def __init__(self, *queued):
        self.queued = list(queued)

    def choice(self, seq):
        want = self.queued.pop(0)
        return want if want in seq else seq[0]


def main():
    print("=== a bet has to clear MIN_BET and be covered by the balance ===")
    cases = [
        (MIN_BET - 1, 10_000, False, "under the minimum"),
        (0,           10_000, False, "zero"),
        (-50,         10_000, False, "negative"),
        (MIN_BET,     10_000, True,  "exactly the minimum"),
        (500,         499,    False, "more than you have"),
        (500,         500,    True,  "exactly your whole balance"),
    ]
    for bet, balance, should_pass, why in cases:
        problem = C.validate_bet(bet, balance)
        print(f"  bet {bet:>6} against {balance:>6} -> "
              f"{'ok' if problem is None else repr(problem[:38])}   ({why})")
        assert (problem is None) == should_pass, f"{why}: got {problem!r}"

    print("\n=== coinflip is an even-money 50/50 ===")
    assert C.coinflip_payout(100, won=True) == 100, "a win must pay the stake"
    assert C.coinflip_payout(100, won=False) == -100, "a loss must cost the stake"
    assert C.coinflip_flip(FixedRng("heads")) == "heads"
    assert C.coinflip_flip(FixedRng("tails")) == "tails"

    # Over many flips the house edge must be zero - this is the game's whole
    # promise, and a silently rounded payout would break it.
    rng = random.Random(1234)
    net = sum(
        C.coinflip_payout(100, won=C.coinflip_flip(rng) == "heads")
        for _ in range(20_000)
    )
    print(f"  net over 20,000 flips of 100: {net:+,} (fair game, expect near 0)")
    assert abs(net) < 100_000, f"coinflip is not fair: {net:+}"

    print("\n=== slots pay on three of a kind, then on a pair ===")
    assert C.slots_payout(["7", "7", "7"], 100) == (1500, "jackpot"), "3-of-a-kind must pay 15x"
    assert C.slots_payout(["7", "7", "2"], 100) == (100, "pair"), "a pair must pay 1x"
    assert C.slots_payout(["7", "2", "7"], 100) == (100, "pair"), "split pair must still count"
    assert C.slots_payout(["2", "7", "7"], 100) == (100, "pair"), "trailing pair must count"
    assert C.slots_payout(["1", "2", "3"], 100) == (-100, "miss"), "no match must cost the stake"

    for spin, bet in ((["7", "7", "7"], 10), (["7", "7", "2"], 10), (["1", "2", "3"], 10)):
        payout, kind = C.slots_payout(spin, bet)
        print(f"  {spin} at {bet} -> {payout:+} ({kind})")

    print("\n=== the slot reel is what the game actually spins ===")
    reel = C.spin(random.Random(7))
    print(f"  a spin: {reel}")
    assert len(reel) == 3, "a spin is three reels"
    assert all(s in C.SLOT_SYMBOLS for s in reel), f"spun a symbol off the reel: {reel}"

    print("\n=== the reel is long enough that pairs aren't the common case ===")
    # This is the whole reason the reel got longer. With 6 symbols a pair
    # lands 41.7% of the time, and at ANY payout above "give the stake back"
    # that alone makes slots profitable to sit on. Rarer pairs are what let
    # the payout stay generous without printing money.
    assert len(C.SLOT_SYMBOLS) >= 8, f"reel too short: {len(C.SLOT_SYMBOLS)} symbols"
    assert len(set(C.SLOT_SYMBOLS)) == len(C.SLOT_SYMBOLS), "duplicate symbol on the reel"

    n = len(C.SLOT_SYMBOLS)
    p_jackpot = 1 / n ** 2
    p_pair = 3 * (n - 1) / n ** 2
    p_miss = (n - 1) * (n - 2) / n ** 2
    assert abs(p_jackpot + p_pair + p_miss - 1) < 1e-9, "the odds don't sum to 1"
    print(f"  {n} symbols -> jackpot {p_jackpot:.2%}, pair {p_pair:.2%}, miss {p_miss:.2%}")

    print("\n=== slots keep a house edge (they are not a coinflip) ===")
    # The exact edge, from the table rather than a simulation.
    edge = p_jackpot * C.SLOT_JACKPOT + p_pair * C.SLOT_PAIR - p_miss
    print(f"  expected value per coin staked: {edge:+.4f}  ({edge:+.1%})")
    assert edge < 0, (
        f"slots pay out MORE than they take ({edge:+.1%} per spin) - with no "
        "cooldown that is an unlimited money printer"
    )
    assert edge > -0.25, f"house edge {edge:.1%} is punishing enough to feel broken"

    # And confirm the simulation agrees with the arithmetic.
    rng = random.Random(99)
    spins = 200_000
    net = sum(C.slots_payout(C.spin(rng), 100)[0] for _ in range(spins))
    per_spin = net / spins / 100
    print(f"  simulated over {spins:,} spins: {per_spin:+.1%} per spin")
    assert abs(per_spin - edge) < 0.02, f"simulation {per_spin:+.1%} != table {edge:+.1%}"
    assert net < 0, f"slots net positive for the player over {spins:,} spins ({net:+,})"

    print("\n=== payouts scale linearly with the stake ===")
    for spin in (["7", "7", "7"], ["7", "7", "2"], ["1", "2", "3"]):
        single = C.slots_payout(spin, 1)[0]
        assert C.slots_payout(spin, 100)[0] == single * 100, f"{spin} doesn't scale"
    assert C.coinflip_payout(1, won=True) * 100 == C.coinflip_payout(100, won=True)

    print("\ncasinocheck OK")


if __name__ == "__main__":
    main()
