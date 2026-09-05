"""The casino's odds and payouts, with no Discord in sight.

--- WHY THIS FILE EXISTS ---

The Casino Owner NPC runs the same games as /coinflip and /slots. A Discord
button cannot invoke a slash command, so the hub can't just call the command -
it has to play the game itself. That leaves two copies of the payout math one
edit apart from disagreeing, and "the slots pay differently depending on
whether you typed /slots or clicked the button" is a bug nobody would report
because it looks like luck.

So the odds live here, both doors call in, and the numbers are testable without
standing up a bot. Same split as heist_logic.py.

--- TUNING, AND THE MISTAKE TO NOT MAKE AGAIN ---

The reel length and the payouts are one system; you cannot tune either alone.

/slots used to run 6 symbols paying 10x on three of a kind and 2x on a pair.
That reads as reasonable and is not: with 6 symbols a pair lands 41.7% of the
time, so the pair payout alone dominates the whole table. The expected value
worked out to +0.56 per coin staked - the player made 56% per spin, on a
command with no cooldown. It was the best income source in the game by a wide
margin, and it made every other economy number meaningless.

The fix was to make pairs rarer rather than to make the payout stingy: at 8
symbols a pair is 32.8%, which leaves room for a generous jackpot and still
lands around -9%. Adding two symbols to this list changes the odds of every
row in the table below - it is not a cosmetic edit.

The check script computes the expected value from the table and refuses
anything player-positive. Run it after touching any of these four constants.
"""

import random

# Kept here rather than in cogs/games.py so the reel and the payout table sit
# next to each other - they only make sense together. LENGTH IS A BALANCE
# NUMBER: pair frequency is 3(n-1)/n², so a shorter reel makes pairs common
# enough to break the game.
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🍉", "⭐", "💎", "🔔", "🍀"]

SLOT_REELS = 3
SLOT_JACKPOT = 15   # all three match - 1.6% of spins
SLOT_PAIR = 1       # exactly two match - 32.8% of spins


def validate_bet(bet: int, balance: int) -> str | None:
    """The refusal to show, or None if the bet is good.

    All three games repeated this check with slightly different wording. One
    copy means one place to change the minimum, and no game can quietly forget
    to check that the player can actually cover the stake.
    """
    from config import MIN_BET

    if bet < MIN_BET:
        return f"Minimum bet is **{MIN_BET}** coins."
    if bet > balance:
        return f"You don't have enough coins. Your balance: **{balance}**"
    return None


def coinflip_flip(rng=random) -> str:
    return rng.choice(["heads", "tails"])


def coinflip_payout(bet: int, won: bool) -> int:
    """Even money. The change to the player's balance, so a loss is negative."""
    return bet if won else -bet


def spin(rng=random) -> list:
    return [rng.choice(SLOT_SYMBOLS) for _ in range(SLOT_REELS)]


def slots_payout(reels: list, bet: int) -> tuple:
    """(change to balance, what happened).

    Three of a kind pays SLOT_JACKPOT times the stake, any two pays SLOT_PAIR
    times, anything else loses it. Note the winning payouts are on top of
    keeping your stake, which is what makes the pair payout a win rather than
    a wash - that matches what /slots has always done.
    """
    if reels[0] == reels[1] == reels[2]:
        return bet * SLOT_JACKPOT, "jackpot"
    if reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        return bet * SLOT_PAIR, "pair"
    return -bet, "miss"
