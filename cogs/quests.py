"""Quest engine.

Content lives in quest_data.py - you shouldn't need to touch this file to add
quests, only to add a new KIND of condition.

Design note: conditions are checked live against the DB at view/turn-in time
rather than tracked incrementally. That means no background listeners, nothing
to get out of sync, and a quest can never end up in a state where the player
did the thing but the counter missed it. The `progress` column on player_quests
is reserved for future event-counted quests ("win 5 blackjack hands") which
genuinely can't be derived from current state.
"""

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import MAX_ACTIVE_QUESTS
from cogs.leveling import apply_level_up


# --- Condition checkers -------------------------------------------------
# Each returns (current, required). The engine derives completion from that,
# so a checker never decides "done" on its own - keeps the rule in one place.
# To add a new condition type: write a checker, register it below, then use
# its name as condition_type in quest_data.py.

async def _check_item_count(user_id: int, guild_id: int, quest: dict):
    inventory = await db.get_inventory(user_id, guild_id)
    held = next(
        (qty for item_id, name, qty in inventory if item_id == quest["condition_target"]),
        0,
    )
    return held, quest["condition_amount"]


async def _check_reach_level(user_id: int, guild_id: int, quest: dict):
    _, level = await db.get_xp_and_level(user_id, guild_id)
    return level, quest["condition_amount"]


async def _check_have_coins(user_id: int, guild_id: int, quest: dict):
    balance = await db.get_balance(user_id, guild_id)
    return balance, quest["condition_amount"]


async def _check_own_house_tier(user_id: int, guild_id: int, quest: dict):
    house = await db.get_player_house(user_id, guild_id)
    return (house[2] if house else 0), quest["condition_amount"]


async def _check_stored_progress(user_id: int, guild_id: int, quest: dict):
    """For things that can't be read off current state - the counter is bumped
    by record_event() when the player actually does the thing."""
    current = await db.get_quest_progress(user_id, guild_id, quest["quest_id"])
    return current, quest["condition_amount"]


CONDITION_CHECKERS = {
    "have_item": _check_item_count,
    "deliver_item": _check_item_count,   # same check - differs only at turn-in
    "reach_level": _check_reach_level,
    "have_coins": _check_have_coins,
    "own_house_tier": _check_own_house_tier,
    "gamble_coins": _check_stored_progress,
    "work_count": _check_stored_progress,
}

# Condition types counted by record_event() rather than read from live state.
EVENT_CONDITIONS = {"gamble_coins", "work_count"}


async def record_event(user_id: int, guild_id: int, condition_type: str, amount: int = 1):
    """Call from gameplay code when the player does something a quest counts.
    Safe to call always - it's a no-op if no active quest tracks this type."""
    if condition_type not in EVENT_CONDITIONS:
        return
    await db.add_quest_progress(user_id, guild_id, condition_type, amount)

# Condition types whose items are taken from the player on turn-in.
CONSUMING_CONDITIONS = {"deliver_item"}


async def check_progress(user_id: int, guild_id: int, quest: dict):
    """Returns (current, required, is_complete) for any quest."""
    checker = CONDITION_CHECKERS.get(quest["condition_type"])
    if checker is None:
        # Unknown condition type - fail closed rather than handing out rewards.
        return 0, quest["condition_amount"], False
    current, required = await checker(user_id, guild_id, quest)
    return current, required, current >= required


async def describe_progress(user_id: int, guild_id: int, quest: dict) -> str:
    current, required, complete = await check_progress(user_id, guild_id, quest)
    mark = "✅" if complete else "▫️"
    return f"{mark} {min(current, required)}/{required}"


def describe_rewards(quest: dict) -> str:
    parts = []
    if quest["reward_coins"]:
        parts.append(f"{quest['reward_coins']} coins")
    if quest["reward_xp"]:
        parts.append(f"{quest['reward_xp']} xp")
    if quest["reward_item_id"]:
        parts.append(f"{quest['reward_item_id']} x{quest['reward_item_qty']}")
    return ", ".join(parts) or "nothing"


# --- Accept / turn in ---------------------------------------------------

async def accept_quest(user_id: int, guild_id: int, quest_id: str) -> str:
    """Returns the message to show the player. Enforces the active-quest cap."""
    quest = await db.get_quest(quest_id)
    if not quest:
        return "That quest doesn't exist."

    status = await db.get_player_quest_status(user_id, guild_id, quest_id)
    if status == "active":
        return "You're already on that one."
    if status == "completed" and not quest["repeatable"]:
        return "You've already done that one."

    active = await db.count_active_quests(user_id, guild_id)
    if active >= MAX_ACTIVE_QUESTS:
        return (
            f"You're juggling too much already ({active}/{MAX_ACTIVE_QUESTS}). "
            "Finish something first."
        )

    await db.set_player_quest_status(user_id, guild_id, quest_id, "active")
    return f"Accepted **{quest['title']}**. Reward: {describe_rewards(quest)}"


async def turn_in_quest(user_id: int, guild_id: int, quest_id: str) -> str:
    """Verifies the condition, consumes items if required, pays out."""
    quest = await db.get_quest(quest_id)
    if not quest:
        return "That quest doesn't exist."

    status = await db.get_player_quest_status(user_id, guild_id, quest_id)
    if status != "active":
        return "You're not on that quest."

    current, required, complete = await check_progress(user_id, guild_id, quest)
    if not complete:
        return f"Not done yet — **{quest['title']}**: {min(current, required)}/{required}"

    # Take the items first: if this fails we haven't paid out yet.
    if quest["condition_type"] in CONSUMING_CONDITIONS:
        taken = await db.remove_item_from_inventory(
            user_id, guild_id, quest["condition_target"], quest["condition_amount"]
        )
        if not taken:
            return "You don't have the items any more."

    if quest["reward_coins"]:
        await db.update_balance(user_id, guild_id, quest["reward_coins"])
    if quest["reward_xp"]:
        xp, level = await db.add_xp(user_id, guild_id, quest["reward_xp"])
        await apply_level_up(user_id, guild_id, xp, level)
    if quest["reward_item_id"]:
        await db.add_item_to_inventory(
            user_id, guild_id, quest["reward_item_id"], quest["reward_item_qty"]
        )

    # Repeatables drop the row so they can be picked up again; one-shots are
    # marked completed so they stay done.
    if quest["repeatable"]:
        await db.clear_player_quest(user_id, guild_id, quest_id)
    else:
        await db.set_player_quest_status(user_id, guild_id, quest_id, "completed")

    return f"**{quest['title']}** complete. You got: {describe_rewards(quest)}"


async def build_quest_embed(user_id: int, guild_id: int) -> discord.Embed:
    """The /quests hub - active quests with live progress, plus open dailies."""
    active_rows = await db.get_player_quests(user_id, guild_id, status="active")
    active_ids = {quest_id for quest_id, status, progress in active_rows}

    embed = discord.Embed(title="Your Quests", color=discord.Color.blurple())

    if active_ids:
        lines = []
        for quest_id in active_ids:
            quest = await db.get_quest(quest_id)
            if not quest:
                continue  # content was removed from quest_data.py
            progress = await describe_progress(user_id, guild_id, quest)
            lines.append(f"{progress} **{quest['title']}** — {describe_rewards(quest)}")
        embed.add_field(name=f"Active ({len(active_ids)}/{MAX_ACTIVE_QUESTS})",
                        value="\n".join(lines), inline=False)
    else:
        embed.add_field(name=f"Active (0/{MAX_ACTIVE_QUESTS})",
                        value="Nothing on your plate.", inline=False)

    available = []
    for quest in await db.get_quests_by_category("daily"):
        status = await db.get_player_quest_status(user_id, guild_id, quest["quest_id"])
        if status == "active":
            continue
        if status == "completed" and not quest["repeatable"]:
            continue
        available.append(f"**{quest['title']}** — {quest['description']}")

    if available:
        embed.add_field(name="Available Dailies", value="\n".join(available), inline=False)

    embed.set_footer(text="NPC quests are offered when you /talk to them.")
    return embed


# --- UI -----------------------------------------------------------------

class QuestSelect(discord.ui.View):
    """Generic picker - `action` decides whether picking accepts or turns in."""

    def __init__(self, user_id: int, guild_id: int, quests: list, action):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.action = action

        options = [
            discord.SelectOption(
                label=quest["title"][:100],
                value=quest["quest_id"],
                description=quest["description"][:100],
            )
            for quest in quests[:25]
        ]
        select = discord.ui.Select(placeholder="Pick a quest", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your quest log.", ephemeral=True)
            return
        message = await self.action(self.user_id, self.guild_id, interaction.data["values"][0])
        await interaction.response.send_message(message, ephemeral=True)


class QuestHubView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your quest log.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept Daily", style=discord.ButtonStyle.primary)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        available = []
        for quest in await db.get_quests_by_category("daily"):
            status = await db.get_player_quest_status(self.user_id, self.guild_id, quest["quest_id"])
            if status == "active":
                continue
            if status == "completed" and not quest["repeatable"]:
                continue
            available.append(quest)

        if not available:
            await interaction.response.send_message("No dailies open right now.", ephemeral=True)
            return

        view = QuestSelect(self.user_id, self.guild_id, available, accept_quest)
        await interaction.response.send_message("Which one?", view=view, ephemeral=True)

    @discord.ui.button(label="Turn In", style=discord.ButtonStyle.success)
    async def turn_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        active = []
        for quest_id, status, progress in await db.get_player_quests(
            self.user_id, self.guild_id, status="active"
        ):
            quest = await db.get_quest(quest_id)
            if quest:
                active.append(quest)

        if not active:
            await interaction.response.send_message("You have no active quests.", ephemeral=True)
            return

        view = QuestSelect(self.user_id, self.guild_id, active, turn_in_quest)
        await interaction.response.send_message("Turning in what?", view=view, ephemeral=True)


class Quests(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="quests", description="View your active quests and available dailies")
    async def quests(self, interaction: discord.Interaction):
        embed = await build_quest_embed(interaction.user.id, interaction.guild.id)
        view = QuestHubView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quests(bot))
