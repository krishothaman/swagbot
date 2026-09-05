"""When a daily quest becomes available again.

Fixed reset: every daily unlocks together at midnight UTC, rather than 24 hours
after each player personally turned it in. A rolling timer punishes you for
playing slightly later each day - miss the window by an hour and your reset
drifts an hour later forever. A fixed boundary can't drift.

UTC, not local time, so the reset doesn't move when a server's timezone has
daylight saving. Players in different timezones all reset at the same instant;
that's the trade for it being predictable.

Pure functions - no database, no discord, no reading the clock unless asked.
`now` is always injectable so the boundary can be tested without waiting a day.
"""

import time

SECONDS_PER_DAY = 86400


def last_reset(now: float = None) -> float:
    """The most recent midnight-UTC timestamp at or before `now`."""
    if now is None:
        now = time.time()
    return now - (now % SECONDS_PER_DAY)


def next_reset(now: float = None) -> float:
    """The upcoming midnight UTC."""
    return last_reset(now) + SECONDS_PER_DAY


def seconds_until_reset(now: float = None) -> int:
    if now is None:
        now = time.time()
    return int(next_reset(now) - now)


def is_available(completed_at: float = None, now: float = None) -> bool:
    """Can a repeatable quest be picked up again?

    completed_at is None for a quest that has never been turned in, which is
    the common case and must read as available - a missing timestamp is not a
    reason to lock someone out.
    """
    if completed_at is None:
        return True
    return completed_at < last_reset(now)


def describe_wait(now: float = None) -> str:
    """Human-readable time until the next reset, for the refusal message."""
    remaining = seconds_until_reset(now)
    hours, seconds = divmod(max(0, remaining), 3600)
    minutes = seconds // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
