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
    HEIST_COOLDOWN_SECONDS, HEIST_SHOT_SECONDS,
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
        result = await run_heist(self.user_id, self.guild_id, self.approach, self.npc_ids)
        await interaction.response.edit_message(embed=result, view=None)

    @discord.ui.button(label="Call it off", style=discord.ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.edit_message(
            content="Maybe next time.", embed=None, view=None
        )


async def run_heist(user_id: int, guild_id: int, approach_key: str, npc_ids: list) -> discord.Embed:
    """Validates, charges, rolls, and applies consequences. Returns the result
    embed. All the actual maths is in heist_logic."""
    approach = logic.APPROACHES[approach_key]

    # Re-check the cooldown here, not just at /heist - the setup view sits open
    # for up to two minutes and a lot can happen in that window.
    last = await db.get_cooldown(user_id, guild_id, "last_heist")
    elapsed = time.time() - last
    if elapsed < HEIST_COOLDOWN_SECONDS:
        remaining = HEIST_COOLDOWN_SECONDS - elapsed
        return discord.Embed(
            title="Too soon",
            description=f"Heat's still on. Try again in **{format_seconds(remaining)}**.",
            color=discord.Color.greyple(),
        )

    if approach["requires_item"]:
        inventory = await db.get_inventory(user_id, guild_id)
        if not any(item_id == approach["requires_item"] for item_id, _, _ in inventory):
            return discord.Embed(
                title="Can't pull that off",
                description=f"**{approach['name']}** needs a `{approach['requires_item']}`.",
                color=discord.Color.greyple(),
            )

    cost = logic.hire_cost(npc_ids)
    balance = await db.get_balance(user_id, guild_id)
    if balance < cost:
        return discord.Embed(
            title="Crew wants paying",
            description=f"You need **{cost}** coins up front. You have **{balance}**.",
            color=discord.Color.greyple(),
        )

    # Committed from here: charge, stamp the cooldown, roll.
    if cost:
        await db.update_balance(user_id, guild_id, -cost)
    await db.set_cooldown(user_id, guild_id, "last_heist")

    chance = logic.calculate_success(approach_key, npc_ids)
    outcome, roll = logic.roll_outcome(chance)
    gross = logic.calculate_take(
        approach_key, HEIST_BASE_PAYOUT_MIN, HEIST_BASE_PAYOUT_MAX
    )

    if outcome == logic.SUCCESS:
        after_cuts, npc_take = logic.apply_npc_cuts(gross, npc_ids)
        new_balance = await db.update_balance(user_id, guild_id, after_cuts)
        embed = discord.Embed(
            title="Clean getaway",
            description=f"Rolled **{roll}** against **{chance}%**.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Score", value=f"{gross} coins", inline=True)
        embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)
        embed.add_field(name="Your take", value=f"**+{after_cuts}**", inline=True)
        embed.set_footer(text=f"Balance: {new_balance}")
        return embed

    if outcome == logic.MINOR_FAILURE:
        scraps = logic.minor_failure_take(gross)
        after_cuts, npc_take = logic.apply_npc_cuts(scraps, npc_ids)
        new_balance = await db.update_balance(user_id, guild_id, after_cuts)
        embed = discord.Embed(
            title="Messy, but you're out",
            description=f"Rolled **{roll}** against **{chance}%**. Alarm went early — "
                        "you grabbed what you could.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Got away with", value=f"{scraps} coins", inline=True)
        embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)
        embed.add_field(name="Your take", value=f"**+{after_cuts}**", inline=True)
        embed.set_footer(text=f"Balance: {new_balance}")
        return embed

    # Bad failure: no money, you get shot, and you may drop something.
    await db.set_incapacitated(user_id, guild_id, HEIST_SHOT_SECONDS)

    lost_line = "Nothing on you worth taking."
    inventory = await db.get_inventory(user_id, guild_id)
    if inventory:
        item_id, name, _ = random.choice(inventory)
        if await db.remove_item_from_inventory(user_id, guild_id, item_id, 1):
            lost_line = f"You dropped **{name}**."

    embed = discord.Embed(
        title="It went bad",
        description=f"Rolled **{roll}** against **{chance}%**. You got shot on the way out.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Take", value="Nothing.", inline=True)
    embed.add_field(name="Lost", value=lost_line, inline=True)
    embed.add_field(
        name="Out of action",
        value=f"**{format_seconds(HEIST_SHOT_SECONDS)}**",
        inline=False,
    )
    if cost:
        embed.set_footer(text=f"The crew kept their {cost} coins.")
    return embed


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
                f"Heat's still on. Next job in **{format_seconds(remaining)}**.",
                ephemeral=True,
            )
            return

        view = HeistSetupView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=view.build_embed(), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Heist(bot))
