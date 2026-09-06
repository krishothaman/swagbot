"""Cooldown countdowns. One helper renders every "come back in X" in the game,
so it has to stay readable from a few seconds up to a full week.

/weekly is what forced days into this: a fresh weekly cooldown rendered as
"167h 59m", which is technically correct and useless to read.
"""
import sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

from ui import format_seconds

MINUTE, HOUR, DAY = 60, 3600, 86400

CASES = [
    (0,                    "0s"),
    (45,                   "45s"),
    (90,                   "1m 30s"),
    (15 * MINUTE,          "15m 0s"),
    (HOUR,                 "1h 0m"),
    (5 * HOUR + 30 * MINUTE, "5h 30m"),
    (23 * HOUR,            "23h 0m"),
    (DAY,                  "1d 0h"),
    (DAY + 5 * HOUR,       "1d 5h"),
    (6 * DAY + 23 * HOUR,  "6d 23h"),
    (7 * DAY,              "7d 0h"),
]


def main():
    print("=== every cooldown length reads like something a person would say ===")
    for seconds, expected in CASES:
        actual = format_seconds(seconds)
        print(f"  {seconds:>7}s -> {actual}")
        assert actual == expected, f"{seconds}s rendered {actual!r}, expected {expected!r}"

    print("\n=== the units never run away ===")
    for seconds in (DAY, 3 * DAY, 7 * DAY, 30 * DAY):
        rendered = format_seconds(seconds)
        assert "h" in rendered and rendered.count(" ") == 1, \
            f"{seconds}s rendered {rendered!r} - a countdown should be two units, not a list"
        hours = int(rendered.split()[1].rstrip("h"))
        assert hours < 24, f"{rendered!r} reports {hours} hours, which should have been a day"

    print("\n=== a float doesn't break it ===")
    print(f"  {format_seconds(90.7)}")
    assert format_seconds(90.7) == "1m 30s", "a fractional second leaked into the output"

    print("\nformatcheck OK")


main()
