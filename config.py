import os
from dotenv import load_dotenv

load_dotenv()

# --- Bot config ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = "!"  # only used for legacy text commands, we're mainly using slash commands

# Your Discord user ID. Set OWNER_ID in .env to lock /dev commands to exactly
# one account. If it's unset we fall back to whoever owns the bot application,
# which Discord tells us at runtime. Never hardcode this here - .env is gitignored.
_raw_owner_id = os.getenv("OWNER_ID")
OWNER_ID = int(_raw_owner_id) if _raw_owner_id and _raw_owner_id.isdigit() else None

# Set DEV_NO_COOLDOWN=1 in .env to start the bot with the owner already
# exempt from every cooldown, so a restart mid-testing doesn't put them back
# on a 30-minute heist timer. Toggle it live with /dev nocooldown.
DEV_NO_COOLDOWN = os.getenv("DEV_NO_COOLDOWN", "").strip().lower() in ("1", "true", "yes")

# --- Database ---
DB_PATH = "data/bot.db"
SELL_PRICE_RATIO = 0.75

# --- Economy constants ---
STARTING_BALANCE = 100
DAILY_REWARD = 200
WORK_MIN_REWARD = 50
WORK_MAX_REWARD = 150
WORK_COOLDOWN_SECONDS = 30      # 30 secs
DAILY_COOLDOWN_SECONDS = 60 * 60 * 24    # 24 hours

# --- Blackjack / games constants ---
MIN_BET = 10

# --- Heist constants ---
HEIST_COOLDOWN_SECONDS = 60 * 30   # one job per 30 minutes
HEIST_SHOT_SECONDS = 60 * 10       # how long "getting shot" locks you out
HEIST_BASE_PAYOUT_MIN = 15000
HEIST_BASE_PAYOUT_MAX = 20000
HEIST_STAGE_SECONDS = 25   # how long the crew gets to vote on each call
HEIST_COP_SECONDS = 20     # the shootout is meant to feel rushed - keep it short
HEIST_LOBBY_SECONDS = 60   # how long the doors stay open for people to join
HEIST_BUY_IN = 1500        # what each member puts in. Also the anti-alt-farming
                           # measure: joining has to cost something real.
                           # Scaled with HEIST_BASE_PAYOUT - at the old 400 against
                           # a 15-20k score the stake was a rounding error and no
                           # outcome could ever lose you money.
HEIST_MAX_CREW = 6         # humans, not counting hired NPCs
# Commands you can't use while shot. Everything not listed stays available so
# a locked-out player can still look at their stuff - a blocklist beats an
# allowlist here because over-blocking is the worse failure.
SHOT_BLOCKED_COMMANDS = {"work", "daily", "coinflip", "slots", "blackjack", "heist"}

# --- Quest constants ---
# How many quests can be on your plate at once. When the daily reset lands this
# becomes a per-day accept cap instead (player_quests.accepted_at is already
# being stamped for exactly that).
MAX_ACTIVE_QUESTS = 5

# --- Gun Man constants ---
# He won't deal with anyone below this. Doubles as the reason a fresh account
# can't walk out with a 7500 coin sidearm on day one.
GUNMAN_LEVEL_REQUIREMENT = 5

# --- Housing constants ---
HOUSE_SELL_RATIO = 0.55   
HOUSE_LEVEL_REQUIREMENTS = {
    1: 3,    # Studio
    2: 10,   # Apartment
    3: 25,   # Mansion
}

# --- Leveling constants ---
XP_PER_MESSAGE_MIN = 5
XP_PER_MESSAGE_MAX = 15
XP_MESSAGE_COOLDOWN_SECONDS = 30  # prevents XP farming by spamming messages

# TODO (Czar): tweak any of these numbers to taste once the bot is running
