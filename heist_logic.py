"""Heist math. Pure functions only - no Discord, no database.

Everything here is deterministic when you hand it a seeded RNG, which is the
whole point: a timing-based multiplayer feature is nearly impossible to test
through the UI, so all the rules that actually decide money live here instead.
cogs/heist.py is just the shell that collects input and displays results.

TUNING: the numbers in APPROACHES and NPC_CREW are the balance dials. Change
them here, nothing else needs to know.
"""

import random

# --- Outcomes -----------------------------------------------------------

SUCCESS = "success"
MINOR_FAILURE = "minor_failure"
BAD_FAILURE = "bad_failure"

# How far past the success threshold still counts as "scraped by". Roll beyond
# this and it's a bad night - items lost, and you get shot.
MINOR_FAILURE_BAND = 20


# --- Approaches ---------------------------------------------------------
# success: base chance before crew bonuses
# payout:  multiplier on the base take
# requires_item: item_id the player must hold (not consumed) - None for open

APPROACHES = {
    "stealth": {
        "name": "Stealth",
        "blurb": "In and out quiet. Safer, but you can't carry much.",
        "success": 75,
        "payout": 0.7,
        "requires_item": None,
    },
    "inside_job": {
        "name": "Inside Job",
        "blurb": "Walk in like you belong. Needs a Fake ID.",
        "success": 55,
        "payout": 1.0,
        "requires_item": "fake_id",
    },
    "force": {
        "name": "Force",
        "blurb": "Doors open either way. Loud, messy, and it pays.",
        "success": 35,
        "payout": 1.4,
        "requires_item": None,
    },
}


# --- Hireable NPC crew --------------------------------------------------
# cost:  coins up front
# bonus: percentage points added to success
# cut:   percent of the take they skim before players split
#
# The cut is what makes crew size a real decision instead of a free upgrade:
# more hands means better odds but a thinner slice each.

# Tuned against simulation (see the EV table in the heist notes): the crew has
# to be worth hiring for a risky approach and NOT worth it for a safe one.
# Earlier values made crew strictly negative EV everywhere, which turned the
# whole mechanic into a trap. If you retune these, re-run the EV sim - it is
# very easy to make crew pointless again.
NPC_CREW = {
    "wheelman": {
        "name": "The Wheelman",
        "blurb": "Engine's already running.",
        "cost": 250,
        "bonus": 8,
        "cut": 5,
    },
    "hacker": {
        "name": "The Hacker",
        "blurb": "Cameras loop, doors forget.",
        "cost": 400,
        "bonus": 14,
        "cut": 8,
    },
    "muscle": {
        "name": "The Muscle",
        "blurb": "Doesn't ask twice.",
        "cost": 300,
        "bonus": 10,
        "cut": 5,
    },
}

MAX_NPC_CREW = 3

# Odds never hit certainty in either direction - a heist is always a gamble.
MIN_SUCCESS = 5
MAX_SUCCESS = 90

# Each extra *human* on the crew. Small, because humans also split the pot.
PLAYER_BONUS = 6


def calculate_success(approach_key: str, npc_ids: list, player_count: int = 1) -> int:
    """Success chance as a whole percent, clamped so nothing is ever certain."""
    approach = APPROACHES[approach_key]
    chance = approach["success"]
    chance += sum(NPC_CREW[n]["bonus"] for n in npc_ids if n in NPC_CREW)
    chance += PLAYER_BONUS * max(0, player_count - 1)
    return max(MIN_SUCCESS, min(MAX_SUCCESS, chance))


def roll_outcome(success_chance: int, rng=random):
    """Rolls 1-100. Returns (outcome, roll).

    roll <= chance                     -> clean success
    within MINOR_FAILURE_BAND past it  -> scraped by, reduced take
    anything worse                     -> bad failure
    """
    roll = rng.randint(1, 100)
    if roll <= success_chance:
        return SUCCESS, roll
    if roll <= success_chance + MINOR_FAILURE_BAND:
        return MINOR_FAILURE, roll
    return BAD_FAILURE, roll


def calculate_take(approach_key: str, base_min: int, base_max: int,
                   player_count: int = 1, rng=random) -> int:
    """The gross score before anyone takes a cut."""
    base = rng.randint(base_min, base_max)
    take = base * APPROACHES[approach_key]["payout"]
    # A bigger crew hits a bigger target, but sub-linearly - otherwise stacking
    # bodies would be strictly correct and there'd be no decision to make.
    take *= 1 + 0.25 * max(0, player_count - 1)
    return int(take)


def minor_failure_take(full_take: int) -> int:
    """You got out, but most of it stayed behind."""
    return int(full_take * 0.25)


def apply_npc_cuts(take: int, npc_ids: list):
    """Returns (remaining_for_players, npc_take). NPCs skim off the top."""
    cut_percent = sum(NPC_CREW[n]["cut"] for n in npc_ids if n in NPC_CREW)
    cut_percent = min(cut_percent, 80)  # they never leave the crew with nothing
    npc_take = int(take * cut_percent / 100)
    return take - npc_take, npc_take


def hire_cost(npc_ids: list) -> int:
    return sum(NPC_CREW[n]["cost"] for n in npc_ids if n in NPC_CREW)


def split_between_players(amount: int, player_count: int) -> int:
    """Even split, rounded down. Remainder is lost to rounding - fine, and it
    keeps the arithmetic honest (nobody can mint coins by re-splitting)."""
    if player_count <= 0:
        return 0
    return amount // player_count


def describe_odds(approach_key: str, npc_ids: list, player_count: int = 1) -> str:
    chance = calculate_success(approach_key, npc_ids, player_count)
    crew = ", ".join(NPC_CREW[n]["name"] for n in npc_ids if n in NPC_CREW) or "nobody"
    return f"{chance}% — crew: {crew}"
