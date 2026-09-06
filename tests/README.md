# Checks

Standalone assert scripts that pin down the game's rules. No pytest, no
fixtures - each file is a program you can run on its own and read top to
bottom.

```bash
python tests/run_all.py          # all 32
python tests/run_all.py house    # just the ones with "house" in the name
python tests/perkcheck.py        # one, with its full narration
```

`run_all.py` exits with the number of failures, so a shell can branch on it.

## What these actually protect

They are less about coverage than about a handful of rules that are expensive
to get wrong and easy to break by accident:

- **`casinocheck`** computes the expected value of the slot table from the odds
  and refuses anything player-positive. `/slots` once paid **+56% per spin** on
  a command with no cooldown - it was the best income source in the game and
  made every other economy number meaningless. Pair frequency is `3(n-1)/n²`,
  so the length of `SLOT_SYMBOLS` is itself a balance number: add a symbol and
  the whole table re-tunes.
- **`perkcheck`** pins the 7-day rent cap and the `last_collect_at = 0` case.
  That column defaults to 0, so a naive `now - 0` reads as ~54 years of back
  rent the instant anybody buys a house.
- **`boostcheck` / `gamescheck`** pin that the house earnings boost reaches
  `/work`, `/daily` and quest rewards but *never* gambling - a Mansion owner
  laundering coins through a coinflip at +20% would beat every honest job.
- **`ceilingcheck` / `gearcheck`** pin that a fully kitted crew plus a Mansion
  still lands under `MAX_SUCCESS`.
- **`migratecheck`** opens a DB created before the newest columns existed and
  proves `init_db` upgrades it without eating existing rows.

## Writing a new one

Copy the header from any existing check. It resolves the repo from `__file__`
(so the script runs from anywhere), forces stdout to utf-8 (a stock Windows
console is cp1252 and these scripts print emoji), and imports `_harness`.

Point `config.DB_PATH` and `database.DB_PATH` at a file in a fresh `tempfile`
directory before importing anything that touches the database, seed what you
need, and end with `asyncio.run(main())`.

Prefer assertions that say what rule broke - `"the 7-day cap leaks"` beats
`assert x == y`. When one fires months from now, that string is the entire
explanation you get.

## Two traps that make a passing check look like a failing one

**A check that hangs after printing PASSED.** aiosqlite's worker thread is not
a daemon, so an unclosed connection keeps the process alive forever. `_harness`
handles this by wrapping `asyncio.run` to close the connection when `main()`
returns - importing it is not optional. This mattered more than it sounds: nine
of these scripts spent weeks scored as passing by a sweep that killed them on a
timeout and then grepped the output for `AssertionError`, finding none.

**A check that passes vacuously.** `questcheck` once never called
`seed_item_data()`, so every inventory lookup returned an empty list and every
item assertion was true about nothing. If a check has never failed, break the
rule it guards on purpose and confirm it goes red.
