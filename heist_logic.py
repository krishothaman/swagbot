#bunch of heist math

import random

# --- Outcomes -----------------------------------------------------------

SUCCESS = "success"
MINOR_FAILURE = "minor_failure"
BAD_FAILURE = "bad_failure"


MINOR_FAILURE_BAND = 20 #chances of failure



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


#  Hireable NPC crew 

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
#
# MAX_SUCCESS must leave room above ROUGH_BAND or "blown" becomes unreachable:
# a stage is blown when roll > chance + ROUGH_BAND, so with chance 90 and a
# band of 15 the threshold lands at 105 and a d100 can never beat it. That bug
# made a full-crew stealth run win 100% of the time. Keep
# MAX_SUCCESS + ROUGH_BAND comfortably under 100.
MIN_SUCCESS = 5
MAX_SUCCESS = 80

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


# How much bigger the score gets per extra human on the job.
#
# Close to linear on purpose. It looks generous but isn't: everyone burns their
# own 30-minute cooldown either way, so four people running one job together
# must not out-earn the same four running solo jobs - and at 0.85 it comes in
# slightly under. Drop this much below linear and grouping up pays worse per
# head than soloing, which kills the whole multiplayer feature.
PLAYER_TAKE_SCALING = 0.85


def calculate_take(approach_key: str, base_min: int, base_max: int,
                   player_count: int = 1, rng=random) -> int:
    """The gross score before anyone takes a cut."""
    base = rng.randint(base_min, base_max)
    take = base * APPROACHES[approach_key]["payout"]
    take *= 1 + PLAYER_TAKE_SCALING * max(0, player_count - 1)
    return int(take)


def tally_votes(votes: dict, choice_keys: list) -> str:
    """Majority wins. Ties break toward the FIRST option, which is always the
    safer one - a split crew shouldn't get dragged into the risky play. Nobody
    voting means the crew froze."""
    if not votes:
        return HESITATE
    counts = {key: 0 for key in choice_keys}
    for choice in votes.values():
        if choice in counts:
            counts[choice] += 1
    best = max(counts.values())
    if best == 0:
        return HESITATE
    for key in choice_keys:  # iteration order = declaration order = safest first
        if counts[key] == best:
            return key
    return choice_keys[0]


def per_player_cost(buy_in: int, npc_ids: list, player_count: int) -> int:
    """Buy-in plus an even share of the crew's fee. Splitting the hire cost is
    what makes a big crew affordable for a big group."""
    if player_count <= 0:
        return buy_in
    return buy_in + hire_cost(npc_ids) // player_count


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


# --- Stages -------------------------------------------------------------
# A job runs three stages. Each one asks for a call under a clock, rolls, and
# either goes clean, goes rough (penalty, keep going) or gets blown (job over).
#
# choices: success is added to the running chance, loot multiplies the take.
# The shape is always "safer but poorer" vs "riskier but richer" so there's a
# genuine decision instead of an obvious best answer.

STAGE_CLEAN = "clean"
STAGE_ROUGH = "rough"
STAGE_BLOWN = "blown"

ROUGH_BAND = 15          # missing by this much or less = rough, not blown
CATASTROPHIC_MARGIN = 40  # missing by this much is bad news at ANY stage

# What a timeout costs you. Freezing up is always the worst option - it should
# never be the smart play to just let the clock run.
HESITATE = "hesitate"
HESITATE_CHOICE = {
    "label": "Froze up",
    "success": -20,
    "loot": 0.9,
    "flavour": "You stood there too long.",
}

# Per-stage tuning. A stage may override:
#   bonus       flat success added before the choice modifier
#   rough_band  how far a miss can be and still only go rough
#
# The entry stage is deliberately forgiving on both. Losing the whole job at
# the front door - before anything has happened, before anyone has touched the
# vault - reads as "why did I bother" rather than "that was tense", and Force
# especially was getting wiped at the door most of the time. A bad entry now
# usually means you're INSIDE but rattled, carrying a worse chance into the
# stages that can actually end you.
#
# Consequence, on purpose: with a wide enough band a high-odds crew can't be
# blown at the entry at all. The "nothing is a sure thing" rule applies to the
# job as a whole, not to every stage of it - the vault and the escape both
# keep the standard band and can still end the run outright.
STAGES = [
    {
        "key": "entry",
        "name": "Getting In",
        "prompt": "You're at the doors. How do you want to do this?",
        "bonus": 10,
        "rough_band": 35,
        "choices": {
            "quiet": {"label": "Slip through the side", "success": 5, "loot": 1.0,
                      "flavour": "Side door. Nobody looks up."},
            "loud": {"label": "Kick the front door", "success": -10, "loot": 1.15,
                     "flavour": "The front door folds inward."},
        },
    },
    {
        "key": "vault",
        "name": "Cracking the Vault",
        "prompt": "The vault's in front of you. Clock's running.",
        "choices": {
            "careful": {"label": "Take your time", "success": 8, "loot": 0.9,
                        "flavour": "Slow hands. Steady tumblers."},
            "fast": {"label": "Drill it", "success": -12, "loot": 1.3,
                     "flavour": "Metal screams. It opens."},
        },
    },
    {
        "key": "escape",
        "name": "Getting Out",
        "prompt": "Sirens. Decide what's coming with you.",
        "choices": {
            "light": {"label": "Ditch some of it", "success": 12, "loot": 0.75,
                      "flavour": "Bags lighter, legs faster."},
            "heavy": {"label": "Take everything", "success": -15, "loot": 1.25,
                      "flavour": "Every bag. No arguments."},
        },
    },
]


def get_stage(index: int) -> dict:
    return STAGES[index]


def stage_bonus(index: int) -> int:
    """Flat success this stage grants before the crew's choice is applied."""
    return STAGES[index].get("bonus", 0)


def stage_rough_band(index: int) -> int:
    """How far a miss can land past the chance and still only go rough."""
    return STAGES[index].get("rough_band", ROUGH_BAND)


def stage_choice(index: int, choice_key: str) -> dict:
    if choice_key == HESITATE:
        return HESITATE_CHOICE
    return STAGES[index]["choices"][choice_key]


def resolve_stage(chance: int, rng=random, band: int = ROUGH_BAND):
    """Rolls one stage. Returns (result, roll).

    `band` is the stage's rough band - pass stage_rough_band(index) so the
    entry stage's wider band applies.
    """
    chance = max(MIN_SUCCESS, min(MAX_SUCCESS, chance))
    roll = rng.randint(1, 100)
    if roll <= chance:
        return STAGE_CLEAN, roll
    if roll <= chance + band:
        return STAGE_ROUGH, roll
    return STAGE_BLOWN, roll


def choice_odds(chance: int, stage_index: int, choice_key: str) -> int:
    """The success chance this call actually rolls at.

    Every stage choice shifts the odds, and resolve_stage clamps the result -
    so this applies the exact same clamp. The number shown to players has to
    be the number that gets rolled, or the display is lying to them.
    """
    shifted = chance + stage_bonus(stage_index) + stage_choice(stage_index, choice_key)["success"]
    return max(MIN_SUCCESS, min(MAX_SUCCESS, shifted))


def blown_chance(effective_chance: int, band: int = ROUGH_BAND) -> int:
    """Percent chance this call blows the job outright.

    Not the same as 100 - success: a miss inside the stage's rough band only
    goes rough and the job continues. This is the part players actually need
    to see, so pass the stage's own band.
    """
    return max(0, 100 - min(100, effective_chance + band))


def blown_severity(stage_index: int, roll: int, chance: int) -> str:
    """How badly a blown stage hurts.

    Getting caught on the way OUT is the worst case - you were holding
    everything. A catastrophic miss is bad news at any stage, which is what
    keeps Force genuinely dangerous the whole way through.
    """
    if stage_index == len(STAGES) - 1:
        return BAD_FAILURE
    if roll - chance > CATASTROPHIC_MARGIN:
        return BAD_FAILURE
    return MINOR_FAILURE


# Getting blown at a later stage means you were holding more when it went bad.
#
# These are fractions of the full score, so they scale with the payout - which
# is exactly the trap they fell into. At the old 3.5-5k score, 15% was a small
# consolation; at 15-20k the same 15% pays more than a clean run used to, and
# a blown job stopped being a loss at all. Keep these low enough that a failed
# heist still costs more than the buy-in.
BLOWN_STAGE_TAKE = {0: 0.0, 1: 0.08, 2: 0.20}


def blown_take(stage_index: int, full_take: int) -> int:
    return int(full_take * BLOWN_STAGE_TAKE.get(stage_index, 0.0))


def describe_odds(approach_key: str, npc_ids: list, player_count: int = 1) -> str:
    chance = calculate_success(approach_key, npc_ids, player_count)
    crew = ", ".join(NPC_CREW[n]["name"] for n in npc_ids if n in NPC_CREW) or "nobody"
    return f"{chance}% — crew: {crew}"


# --- The cops -------------------------------------------------------------
# Fires between the vault and the escape, when the crew is holding everything.
#
# This is a SEPARATE contest from the stage rolls, and that's the whole point.
# Stage success is clamped at MAX_SUCCESS (80), and stealth already starts at
# 75 - so a flat "+N% success per gun" would be swallowed by the ceiling and
# an expensive gun would do visibly nothing. Here there's no ceiling in the
# way, so gun tier has room to matter.

# The board is 4 rows of 5. The 5th row is reserved for Take Cover, since a
# Discord message caps out at 25 components total.
GRID_ROWS = 4
GRID_COLS = 5
GRID_CELLS = GRID_ROWS * GRID_COLS

CELL_EMPTY = "empty"
CELL_COP = "cop"
CELL_BYSTANDER = "bystander"

# What each gun is worth in a firefight. This is the authoritative list of
# what counts as a gun - cogs/gunman.py reads it so the two can't drift.
GUN_SHOTS = {
    "p250": 3,
    "five_seven": 5,
}

BYSTANDERS = 4          # civilians on the board. Hitting one costs you.
BYSTANDER_COST = 1      # counts against you as if a cop got through

COP_CLEAN = "clean"      # every cop down
COP_HELD = "held"        # most of them
COP_PUSHED = "pushed"    # they got the better of it
COP_OVERRUN = "overrun"  # you barely fired

# What surviving the cops does to your escape odds. Holding them off buys you
# a clean run at the door; getting pushed back means you're leaving hot.
COP_ESCAPE_MODIFIER = {
    COP_CLEAN: 25,
    COP_HELD: 10,
    COP_PUSHED: -10,
    COP_OVERRUN: -25,
}

# Taking a hit makes the escape worse on top of the tier modifier.
SHOT_ESCAPE_PENALTY = 10

# How much of the haul survives each outcome.
COP_LOOT_MULTIPLIER = {
    COP_CLEAN: 1.0,
    COP_HELD: 0.85,
    COP_PUSHED: 0.55,
    COP_OVERRUN: 0.3,
}

# Only the worst outcome puts someone down, and never more than one person -
# a wipe would end the run for a whole crew on one bad stage, which is the
# opposite of the "you get out, someone's bleeding" tone this is going for.
MAX_CASUALTIES = 1


def cop_count(player_count: int) -> int:
    """How many cops turn up. Scales with the crew or a big group would walk
    through the same four officers a solo player struggles with."""
    return min(3 + max(1, player_count), GRID_CELLS - BYSTANDERS)


def shots_for(item_ids) -> int:
    """Total shots a player gets from what they're carrying. No gun, no shots -
    they can still Take Cover, they just can't contribute."""
    return sum(GUN_SHOTS.get(item_id, 0) for item_id in item_ids)


def build_grid(player_count: int, rng=random) -> list:
    """Lays out the board: cops, bystanders, and empty space, shuffled."""
    cops = cop_count(player_count)
    cells = ([CELL_COP] * cops
             + [CELL_BYSTANDER] * BYSTANDERS
             + [CELL_EMPTY] * (GRID_CELLS - cops - BYSTANDERS))
    rng.shuffle(cells)
    return cells


def cop_result(cops_down: int, bystanders_hit: int, cops_total: int) -> str:
    """Grades the firefight. Hitting civilians counts against you, so mashing
    every button is not a winning strategy."""
    if cops_total <= 0:
        return COP_CLEAN
    effective = max(0, cops_down - bystanders_hit * BYSTANDER_COST)
    ratio = effective / cops_total
    if cops_down >= cops_total and bystanders_hit == 0:
        return COP_CLEAN
    if ratio >= 0.6:
        return COP_HELD
    if ratio >= 0.3:
        return COP_PUSHED
    return COP_OVERRUN


def cop_escape_modifier(result: str, someone_shot: bool) -> int:
    modifier = COP_ESCAPE_MODIFIER.get(result, 0)
    if someone_shot:
        modifier -= SHOT_ESCAPE_PENALTY
    return modifier


def cop_loot_multiplier(result: str) -> float:
    return COP_LOOT_MULTIPLIER.get(result, 1.0)


def cop_casualties(result: str, exposed: list, rng=random) -> list:
    """Who takes a hit. At most MAX_CASUALTIES, and only when it goes badly.

    `exposed` is everyone who didn't take cover - which is what makes the
    Take Cover button worth pressing for a player with no gun to fire.
    """
    if result != COP_OVERRUN or not exposed:
        return []
    return rng.sample(list(exposed), min(MAX_CASUALTIES, len(exposed)))


# --- Betrayal -------------------------------------------------------------
# Only offered at the final (escape) stage, and only pays off if the crew
# actually gets out clean or rough - if the whole job gets blown nobody is
# escaping with anything, betrayer included, so there's nothing to resolve.
#
# The roll itself is deliberately unaided: no crew bonus, no player-count
# bonus. Betraying is something you do alone, improvising, while everyone
# else is still following the plan.
BETRAY_CHANCE_PENALTY = 25
BETRAY_BONUS_PCT = 0.20   # skimmed off the top of the pot per successful betrayer
BETRAY_KEEP_PCT = 0.20    # what a caught betrayer keeps of their own normal share


def betray_chance(approach_key: str) -> int:
    base = APPROACHES[approach_key]["success"]
    return max(MIN_SUCCESS, base - BETRAY_CHANCE_PENALTY)


def roll_betrayal(approach_key: str, rng=random) -> bool:
    chance = betray_chance(approach_key)
    return rng.randint(1, 100) <= chance


def resolve_payouts(after_cuts: int, player_ids: list, betrayals: dict) -> dict:
    """Splits the post-NPC-cut pot, accounting for anyone who tried to betray
    the crew at the escape stage.

    betrayals: {user_id: True/False} - True means they got away with it,
    False means they got caught. Anyone not in the dict played it straight.

    A successful betrayer skims BETRAY_BONUS_PCT of the whole pot for
    themselves, on top of a normal split of what's left - so a loyal crew's
    share quietly shrinks without them knowing why. A caught betrayer keeps
    only BETRAY_KEEP_PCT of what their normal share would have been; the rest
    is handed ONLY to the loyal crew, split evenly on top of their own share.
    Nothing is minted or destroyed - it's always somebody's original slice
    moving to somebody else, modulo the same rounding-down every split here
    already accepts.
    """
    count = len(player_ids)
    if count == 0:
        return {}

    successful = {p for p, ok in betrayals.items() if ok is True}
    failed = {p for p, ok in betrayals.items() if ok is False}
    loyal = [p for p in player_ids if p not in betrayals]

    bonus_each = int(after_cuts * BETRAY_BONUS_PCT)
    total_skim = min(bonus_each * len(successful), after_cuts)
    # base_share is what everyone's "normal" cut is worth once successful
    # betrayers have already skimmed their bonus off the top - a failed
    # betrayer's own reference share has to come from this, not the
    # pre-skim pot, or the two calculations disagree about how much money
    # actually exists and payouts can exceed the pot.
    base_share = (after_cuts - total_skim) // count if count else 0

    keep_each = int(base_share * BETRAY_KEEP_PCT)
    forfeit_each = base_share - keep_each
    total_forfeit = forfeit_each * len(failed)
    # If nobody stayed loyal, the forfeit has nowhere to go - lost, same as
    # any other rounding remainder in this system.
    forfeit_bonus = total_forfeit // len(loyal) if loyal else 0

    payouts = {}
    for pid in player_ids:
        if pid in successful:
            payouts[pid] = base_share + bonus_each
        elif pid in failed:
            payouts[pid] = keep_each
        else:
            payouts[pid] = base_share + forfeit_bonus
    return payouts
