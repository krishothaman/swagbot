import os
from dotenv import load_dotenv

load_dotenv()

# --- Bot config ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = "!"  # only used for legacy text commands, we're mainly using slash commands

# --- Database ---
DB_PATH = "data/bot.db"

# --- Economy constants ---
STARTING_BALANCE = 100
DAILY_REWARD = 200
WORK_MIN_REWARD = 50
WORK_MAX_REWARD = 150
WORK_COOLDOWN_SECONDS = 60 * 60          # 1 hour
DAILY_COOLDOWN_SECONDS = 60 * 60 * 24    # 24 hours

# --- Blackjack / games constants ---
MIN_BET = 10

# --- Leveling constants ---
XP_PER_MESSAGE_MIN = 5
XP_PER_MESSAGE_MAX = 15
XP_MESSAGE_COOLDOWN_SECONDS = 60  # prevents XP farming by spamming messages

# TODO (Czar): tweak any of these numbers to taste once the bot is running
