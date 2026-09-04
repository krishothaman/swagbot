"""Heist - step 1: solo job with a hireable NPC crew.

All the money math lives in heist_logic.py so it can be tested without Discord.
This file only collects the player's choices and reports what happened.

Multiplayer lobby, staged runs (get in / crack the vault / escape) and betrayal
are later steps. The logic module already takes a player_count argument so the
crew maths won't need rewriting when the lobby lands.
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
import heist_logic as logic
from config import (
    HEIST_COOLDOWN_SECONDS, HEIST_SHOT_SECONDS, HEIST_STAGE_SECONDS,
    HEIST_BASE_PAYOUT_MIN, HEIST_BASE_PAYOUT_MAX,
)
from cogs.economy import format_seconds


class HeistSetupView(discord.ui.View):
    """Pick a crew, pick an approach, watch the odds move, then commit."""

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.approach = "stealth"
        self.npc_ids = []

        crew_select = discord.ui.Select(
            placeholder="Hire crew (optional)",
            min_values=0,
            max_values=logic.MAX_NPC_CREW,
            options=[
                discord.SelectOption(
                    label=f"{data['name']} — {data['cost']} coins",
                    value=npc_id,
                    description=f"+{data['bonus']}% success, takes {data['cut']}% — {data['blurb']}"[:100],
                )
                for npc_id, data in logic.NPC_CREW.items()
            ],
        )
        crew_select.callback = self.on_crew
        self.add_item(crew_select)

        approach_select = discord.ui.Select(
            placeholder="Choose your approach",
            options=[
                discord.SelectOption(
                    label=f"{data['name']} — {data['success']}% base",
                    value=key,
                    description=data["blurb"][:100],
                    default=(key == "stealth"),
                )
                for key, data in logic.APPROACHES.items()
            ],
        )
        approach_select.callback = self.on_approach
        self.add_item(approach_select)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your job.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        approach = logic.APPROACHES[self.approach]
        chance = logic.calculate_success(self.approach, self.npc_ids)
        cost = logic.hire_cost(self.npc_ids)
        _, npc_cut = logic.apply_npc_cuts(100, self.npc_ids)

        embed = discord.Embed(
            title="Planning a Job",
            description="Odds update as you pick. Nothing is charged until you go.",
            color=discord.Color.dark_red(),
        )
        embed.add_field(name="Approach", value=f"{approach['name']}\n*{approach['blurb']}*", inline=False)
        embed.add_field(name="Success", value=f"**{chance}%**", inline=True)
        embed.add_field(name="Upfront", value=f"{cost} coins", inline=True)
        embed.add_field(name="Crew takes", value=f"{npc_cut}% of the score", inline=True)

        if approach["requires_item"]:
            embed.add_field(
                name="Requires", value=f"`{approach['requires_item']}` in your inventory", inline=False
            )
        crew = ", ".join(logic.NPC_CREW[n]["name"] for n in self.npc_ids) or "flying solo"
        embed.set_footer(text=f"Crew: {crew}")
        return embed

    async def on_crew(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self.npc_ids = interaction.data["values"]
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_approach(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self.approach = interaction.data["values"][0]
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Go", style=discord.ButtonStyle.danger, row=2)
    async def go(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.stop()  # planning is over; the stage driver takes the message from here
        await run_heist(interaction, self.user_id, self.guild_id, self.approach, self.npc_ids)

    @discord.ui.button(label="Call it off", style=discord.ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.edit_message(
            content="Maybe next time.", embed=None, view=None
        )


class StageView(discord.ui.View):
    """One stage's choices under a clock. The driver awaits wait(); if that
    returns True nobody pressed anything and the player froze."""

    def __init__(self, user_id: int, stage: dict):
        super().__init__(timeout=HEIST_STAGE_SECONDS)
        self.user_id = user_id
        self.choice = None

        for key, data in stage["choices"].items():
            self.add_item(self.ChoiceButton(self, key, data["label"]))

    class ChoiceButton(discord.ui.Button):
        def __init__(self, parent_view, key: str, label: str):
            super().__init__(label=label, style=discord.ButtonStyle.primary)
            self.parent_view = parent_view
            self.key = key

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.user_id:
                await interaction.response.send_message("not your job.", ephemeral=True)
                return
            self.parent_view.choice = self.key
            # Ack without changing anything - the driver redraws the message.
            await interaction.response.defer()
            self.parent_view.stop()


def stage_embed(stage: dict, index: int, chance: int, loot_mult: float, log: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"{stage['name']}  ({index + 1}/{len(logic.STAGES)})",
        description=stage["prompt"],
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Odds", value=f"**{chance}%**", inline=True)
    embed.add_field(name="Haul", value=f"×{loot_mult:.2f}", inline=True)
    if log:
        embed.add_field(name="So far", value="\n".join(log), inline=False)
    embed.set_footer(text=f"{HEIST_STAGE_SECONDS}s to decide — freezing up costs you")
    return embed


async def run_heist(interaction: discord.Interaction, user_id: int, guild_id: int,
                    approach_key: str, npc_ids: list):
    """Validates, charges, then drives the three stages. All maths in heist_logic."""
    approach = logic.APPROACHES[approach_key]

    # Re-check the cooldown here, not just at /heist - the setup view sits open
    # for up to two minutes and a lot can happen in that window.
    async def refuse(title: str, body: str):
        await interaction.response.edit_message(
            embed=discord.Embed(title=title, description=body, color=discord.Color.greyple()),
            view=None,
        )

    last = await db.get_cooldown(user_id, guild_id, "last_heist")
    elapsed = time.time() - last
    if elapsed < HEIST_COOLDOWN_SECONDS:
        remaining = HEIST_COOLDOWN_SECONDS - elapsed
        await refuse("Too soon", f"Heat's still on. Try again in **{format_seconds(remaining)}**.")
        return

    if approach["requires_item"]:
        inventory = await db.get_inventory(user_id, guild_id)
        if not any(item_id == approach["requires_item"] for item_id, _, _ in inventory):
            await refuse("Can't pull that off",
                         f"**{approach['name']}** needs a `{approach['requires_item']}`.")
            return

    cost = logic.hire_cost(npc_ids)
    balance = await db.get_balance(user_id, guild_id)
    if balance < cost:
        await refuse("Crew wants paying",
                     f"You need **{cost}** coins up front. You have **{balance}**.")
        return

    # Committed from here: charge, stamp the cooldown, run the job.
    if cost:
        await db.update_balance(user_id, guild_id, -cost)
    await db.set_cooldown(user_id, guild_id, "last_heist")

    chance = logic.calculate_success(approach_key, npc_ids)
    gross = logic.calculate_take(approach_key, HEIST_BASE_PAYOUT_MIN, HEIST_BASE_PAYOUT_MAX)
    loot_mult = 1.0
    log = []

    await interaction.response.edit_message(
        embed=stage_embed(logic.get_stage(0), 0, chance, loot_mult, log), view=None
    )
    message = await interaction.original_response()

    for index in range(len(logic.STAGES)):
        stage = logic.get_stage(index)
        view = StageView(user_id, stage)
        await message.edit(embed=stage_embed(stage, index, chance, loot_mult, log), view=view)

        timed_out = await view.wait()
        choice_key = logic.HESITATE if timed_out else view.choice
        choice = logic.stage_choice(index, choice_key)

        stage_chance = chance + choice["success"]
        result, roll = logic.resolve_stage(stage_chance)

        if result == logic.STAGE_BLOWN:
            severity = logic.blown_severity(index, roll, stage_chance)
            take = logic.blown_take(index, int(gross * loot_mult * choice["loot"]))
            log.append(f"❌ **{stage['name']}** — {choice['label']}: it went wrong.")
            await finish_blown(message, user_id, guild_id, severity, take, npc_ids, cost, log)
            return

        # Survived. Rough stages still cost you.
        loot_mult *= choice["loot"]
        if result == logic.STAGE_ROUGH:
            chance = max(logic.MIN_SUCCESS, stage_chance - 10)
            loot_mult *= 0.85
            log.append(f"⚠️ **{stage['name']}** — {choice['label']}: close call.")
        else:
            chance = min(logic.MAX_SUCCESS, stage_chance)
            log.append(f"✅ **{stage['name']}** — {choice['flavour']}")

    # Made it through all three.
    final_take = int(gross * loot_mult)
    after_cuts, npc_take = logic.apply_npc_cuts(final_take, npc_ids)
    new_balance = await db.update_balance(user_id, guild_id, after_cuts)

    embed = discord.Embed(
        title="Clean getaway",
        description="\n".join(log),
        color=discord.Color.green(),
    )
    embed.add_field(name="Haul", value=f"{final_take} coins", inline=True)
    embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)
    embed.add_field(name="Your take", value=f"**+{after_cuts}**", inline=True)
    embed.set_footer(text=f"Balance: {new_balance}")
    await message.edit(embed=embed, view=None)


async def finish_blown(message, user_id: int, guild_id: int, severity: str,
                       take: int, npc_ids: list, cost: int, log: list):
    """Resolves a job that fell apart mid-run."""
    if severity == logic.MINOR_FAILURE:
        after_cuts, npc_take = logic.apply_npc_cuts(take, npc_ids)
        new_balance = await db.update_balance(user_id, guild_id, after_cuts)
        embed = discord.Embed(
            title="Blown — but you're breathing",
            description="\n".join(log),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Got away with", value=f"{take} coins", inline=True)
        embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)
        embed.add_field(name="Your take", value=f"**+{after_cuts}**", inline=True)
        embed.set_footer(text=f"Balance: {new_balance}")
        await message.edit(embed=embed, view=None)
        return

    # Bad failure: shot, and you drop something on the way down.
    await db.set_incapacitated(user_id, guild_id, HEIST_SHOT_SECONDS)

    lost_line = "Nothing on you worth taking."
    inventory = await db.get_inventory(user_id, guild_id)
    if inventory:
        item_id, name, _ = random.choice(inventory)
        if await db.remove_item_from_inventory(user_id, guild_id, item_id, 1):
            lost_line = f"You dropped **{name}**."

    embed = discord.Embed(
        title="It went bad",
        description="\n".join(log) + "\n\nYou got shot on the way out.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Take", value="Nothing.", inline=True)
    embed.add_field(name="Lost", value=lost_line, inline=True)
    embed.add_field(name="Out of action",
                    value=f"**{format_seconds(HEIST_SHOT_SECONDS)}**", inline=False)
    if cost:
        embed.set_footer(text=f"The crew kept their {cost} coins.")
    await message.edit(embed=embed, view=None)


class Heist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heist", description="Plan and pull off a heist")
    async def heist(self, interaction: discord.Interaction):
        last = await db.get_cooldown(interaction.user.id, interaction.guild.id, "last_heist")
        elapsed = time.time() - last
        if elapsed < HEIST_COOLDOWN_SECONDS:
            remaining = HEIST_COOLDOWN_SECONDS - elapsed
            await interaction.response.send_message(
                f"Cop's still on you. Next job in **{format_seconds(remaining)}**.",
                ephemeral=True,
            )
            return

        view = HeistSetupView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=view.build_embed(), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Heist(bot))
