# Discord Economy/Game Bot (v2)

## Setup

1. `python -m venv venv` then activate it (`venv\Scripts\activate` on Windows, `source venv/bin/activate` on Mac/Linux)
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and paste your bot token in
4. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → your bot → Bot tab → enable **Message Content Intent** and **Server Members Intent** (bot.py requests both)
5. `python bot.py`

## Structure

- `bot.py` — entry point, loads all cogs, syncs slash commands
- `config.py` — token, cooldowns, reward amounts (tweak freely)
- `database.py` — all DB logic, shared by every cog (fully wired, don't need to touch)
- `cogs/economy.py` — `/balance` `/daily` `/work` `/transfer` `/leaderboard` — **TODO**
- `cogs/blackjack.py` — `/blackjack` with Hit/Stand buttons — **TODO**
- `cogs/games.py` — `/coinflip` `/slots` — **TODO**
- `cogs/leveling.py` — XP on message, `/rank`, `/rank_leaderboard` — **TODO**

## What's already wired for you

- Database schema + all get/set helper functions (balance, cooldowns, xp, level, leaderboard)
- Bot startup, cog loading, slash command syncing
- Blackjack deck creation + hand value calculation (Ace high/low handled)

## What you need to fill in

Every `# TODO (Czar):` comment in the cogs. Each one has step-by-step guidance
on what to call and what to check, but the actual command logic is yours to write.
Start with `cogs/economy.py` — it's the simplest and everything else builds on
the same balance/cooldown patterns.

## Git

```
git init
git add .
git commit -m "v2 skeleton"
```
Do this now before you write anything else, so you never lose this again.
