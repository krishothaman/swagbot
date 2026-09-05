"""What owning a house actually gets you.

Houses used to buy storage slots and nothing else, which made the 500,000 coin
Mansion a trophy rather than an investment. Every tier now pays two ways:

  rent   - a flat daily amount you claim with /house collect
  boost  - a percentage added to everything you earn (/work, /daily, quests)

and the Mansion additionally lends the crew a small flat bonus on heist odds.

--- WHY THE PERKS LIVE HERE AND NOT IN THE DATABASE ---

The obvious home for these numbers is extra columns on the `houses` table. It
isn't worth it: `db.get_player_house()` returns a positional 8-tuple that three
different call sites in cogs/housing.py unpack by hand, so widening that row
means touching all of them every time you want to tune a percentage. Keeping
the perks in a dict keyed by house_id means tuning is a one-line edit here and
a restart, matching how item_data.py and quest_data.py already work.

The keys MUST match the house_ids seeded in database.seed_house_data(). A typo
gives that tier no perks at all, silently - rentcheck.py asserts the two stay
in sync against a real database.

Pure functions: no database, no discord, and no reading the clock unless asked.
`now` is injectable so the seven-day cap is testable without waiting a week.
"""

SECONDS_PER_DAY = 86400

# How many days of rent can pile up while you're not playing. Uncollected rent
# accrues so logging in every day isn't compulsory, but it stops at a week -
# past that, an inactive account isn't meaningfully "earning" anything and the
# cap is what keeps a dormant mansion from being a savings account.
RENT_CAP_DAYS = 7

HOUSE_PERKS = {
    "studio":    {"rent": 50,   "boost": 0.05, "heist": 0},
    "apartment": {"rent": 250,  "boost": 0.10, "heist": 0},
    "mansion":   {"rent": 1500, "boost": 0.20, "heist": 2},
}


def _perks(house_id) -> dict:
    """Never raises. No house, or a house_id this file has never heard of,
    reads as "no perks" rather than blowing up a payout mid-command."""
    return HOUSE_PERKS.get(house_id) or {}


def boost_percent(house_id) -> int:
    """The earnings boost as a whole percent, for both math and display."""
    return round(_perks(house_id).get("boost", 0) * 100)


def apply_boost(amount: int, house_id) -> int:
    """`amount` plus the house's cut, floored.

    Integer math on purpose. Doing this as `int(amount * 1.05)` in floating
    point can land a fraction under a whole number and quietly shave a coin
    off; coins are integers, so the percentage is applied as one.
    """
    if amount <= 0:
        return amount
    return amount + (amount * boost_percent(house_id)) // 100


def rent_rate(house_id) -> int:
    """Coins per day this house pays out."""
    return _perks(house_id).get("rent", 0)


def days_accrued(last_collect, now: float = None) -> int:
    """Whole days of rent owed since `last_collect`, capped at RENT_CAP_DAYS.

    A `last_collect` of 0 or None means the ledger was never stamped, which is
    the column default. Treating that as "elapsed since 1970" would pay the
    full cap the instant anyone bought a house, so it reads as zero and the
    caller stamps the ledger instead. A stamp in the future (clock skew) is
    zero for the same reason: no free money from a bad clock.
    """
    if not last_collect or last_collect <= 0:
        return 0
    if now is None:
        import time
        now = time.time()
    elapsed = now - last_collect
    if elapsed <= 0:
        return 0
    return min(int(elapsed // SECONDS_PER_DAY), RENT_CAP_DAYS)


def rent_owed(house_id, last_collect, now: float = None) -> int:
    """Coins waiting to be collected. Zero if you don't own anything."""
    return rent_rate(house_id) * days_accrued(last_collect, now)


def seconds_until_next_day(last_collect, now: float = None) -> int:
    """How long until one more day of rent lands, for the "come back later"
    line. Meaningless once you're at the cap, so the caller checks that first."""
    if not last_collect or last_collect <= 0:
        return SECONDS_PER_DAY
    if now is None:
        import time
        now = time.time()
    whole_days = max(0, int((now - last_collect) // SECONDS_PER_DAY))
    return max(0, int(last_collect + (whole_days + 1) * SECONDS_PER_DAY - now))


def house_heist_bonus(house_ids) -> int:
    """Success bonus the crew's housing lends the job.

    Flat and non-stacking - the best house on the crew is what counts, and a
    second Mansion owner adds nothing. Same reasoning as MASK_CAP in
    heist_logic.py: gear and property are a floor under a bad approach, not a
    thing you stack six deep. A crew of six mansion owners would otherwise be
    walking in with +12 before they'd bought a single item.
    """
    return max((_perks(h).get("heist", 0) for h in house_ids), default=0)
