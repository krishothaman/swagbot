"""Heist - a multiplayer job with hired NPC crew, staged runs and voting.

All the money math lives in heist_logic.py so it can be tested without Discord.
This file collects input, runs the clock, and reports what happened.

Flow: /heist opens a lobby -> people join and vote an approach -> three staged
votes under a clock -> payout or consequences. Nobody joining is fine; it just
runs solo, which is deliberate - on a small server a heist that needs a crowd
is a heist that never happens.

At the final stage a player can Betray instead of voting - a private roll that
either skims a bonus off the top or, if caught, costs them most of their own
share (handed to whoever stayed loyal). Only resolved if the crew actually
gets out; a blown job means nobody's escaping with anything either way.

Session state is in-memory on purpose: a lobby lives about a minute and a whole
job under five. Nothing here is worth a database table; only outcomes are
written. If the bot restarts mid-job the lobby evaporates, which is why nobody
is charged until the job actually starts.
"""

import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
import heist_logic as logic
from config import (
    HEIST_COOLDOWN_SECONDS, HEIST_SHOT_SECONDS, HEIST_STAGE_SECONDS,
    HEIST_LOBBY_SECONDS, HEIST_BUY_IN, HEIST_MAX_CREW,
    HEIST_BASE_PAYOUT_MIN, HEIST_BASE_PAYOUT_MAX, HEIST_COP_SECONDS,
)
from cogs.economy import format_seconds

# One lobby per guild - on a small server, splitting people across two
# simultaneous lobbies means neither one fills.
ACTIVE_HEISTS: dict[int, "HeistSession"] = {}
# Users currently in a job anywhere, so nobody joins two at once.
BUSY_USERS: set[int] = set()


class HeistSession:
    def __init__(self, guild_id: int, host_id: int):
        self.guild_id = guild_id
        self.host_id = host_id
        self.players = [host_id]
        self.npc_ids: list[str] = []
        self.approach_votes: dict[int, str] = {host_id: "stealth"}

    @property
    def approach(self) -> str:
        winner = logic.tally_votes(self.approach_votes, list(logic.APPROACHES))
        return "stealth" if winner == logic.HESITATE else winner

    def vote_summary(self) -> str:
        counts = {}
        for choice in self.approach_votes.values():
            counts[choice] = counts.get(choice, 0) + 1
        if not counts:
            return "no votes yet"
        return " · ".join(
            f"{logic.APPROACHES[k]['name']} {v}" for k, v in counts.items() if k in logic.APPROACHES
        )

    def release(self):
        ACTIVE_HEISTS.pop(self.guild_id, None)
        for player in self.players:
            BUSY_USERS.discard(player)


# --- Lobby --------------------------------------------------------------

class LobbyView(discord.ui.View):
    def __init__(self, session: HeistSession):
        super().__init__(timeout=HEIST_LOBBY_SECONDS)
        self.session = session
        self.started = False

        crew_select = discord.ui.Select(
            placeholder="Hire crew (host only)",
            min_values=0,
            max_values=logic.MAX_NPC_CREW,
            options=[
                discord.SelectOption(
                    label=f"{d['name']} — {d['cost']} coins",
                    value=npc_id,
                    description=f"+{d['bonus']}% success, takes {d['cut']}% — {d['blurb']}"[:100],
                )
                for npc_id, d in logic.NPC_CREW.items()
            ],
        )
        crew_select.callback = self.on_crew
        self.add_item(crew_select)

        approach_select = discord.ui.Select(
            placeholder="Vote the approach",
            options=[
                discord.SelectOption(
                    label=f"{d['name']} — {d['success']}% base",
                    value=key,
                    description=d["blurb"][:100],
                )
                for key, d in logic.APPROACHES.items()
            ],
        )
        approach_select.callback = self.on_vote
        self.add_item(approach_select)

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        session = self.session
        approach = logic.APPROACHES[session.approach]
        count = len(session.players)
        chance = logic.calculate_success(session.approach, session.npc_ids, count)
        cost = logic.per_player_cost(HEIST_BUY_IN, session.npc_ids, count)

        names = []
        for pid in session.players:
            member = guild.get_member(pid)
            label = member.display_name if member else f"user {pid}"
            names.append(f"**{label}**" + (" (host)" if pid == session.host_id else ""))

        embed = discord.Embed(
            title="Putting a crew together",
            description=f"Doors close in **{HEIST_LOBBY_SECONDS}s**. Press Join to get in on it.",
            color=discord.Color.dark_red(),
        )
        embed.add_field(name=f"Crew ({count}/{HEIST_MAX_CREW})", value="\n".join(names), inline=False)
        embed.add_field(name="Approach", value=f"{approach['name']}\n*{approach['blurb']}*", inline=False)
        embed.add_field(name="Odds", value=f"**{chance}%**", inline=True)
        embed.add_field(name="Costs you", value=f"{cost} coins", inline=True)
        embed.add_field(name="Votes", value=session.vote_summary(), inline=True)

        hired = ", ".join(logic.NPC_CREW[n]["name"] for n in session.npc_ids) or "none"
        embed.set_footer(text=f"Hired: {hired} — nothing is charged until the job starts")
        return embed

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=self.build_embed(interaction.guild), view=self
        )

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, row=2)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.session
        user_id = interaction.user.id

        if user_id in session.players:
            await interaction.response.send_message("You're already in.", ephemeral=True)
            return
        if user_id in BUSY_USERS:
            await interaction.response.send_message("You're already on another job.", ephemeral=True)
            return
        if len(session.players) >= HEIST_MAX_CREW:
            await interaction.response.send_message("Crew's full.", ephemeral=True)
            return

        remaining = await db.get_incapacitated_remaining(user_id, interaction.guild.id)
        if remaining > 0:
            await interaction.response.send_message(
                f"You're in no shape for this. {format_seconds(remaining)} left.", ephemeral=True
            )
            return

        last = await db.get_cooldown(user_id, interaction.guild.id, "last_heist")
        elapsed = time.time() - last
        if elapsed < HEIST_COOLDOWN_SECONDS:
            await interaction.response.send_message(
                f"You're too hot right now. {format_seconds(HEIST_COOLDOWN_SECONDS - elapsed)} left.",
                ephemeral=True,
            )
            return

        session.players.append(user_id)
        BUSY_USERS.add(user_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, row=2)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.session
        user_id = interaction.user.id
        if user_id == session.host_id:
            await interaction.response.send_message(
                "You're running this. Call it off instead.", ephemeral=True
            )
            return
        if user_id not in session.players:
            await interaction.response.send_message("You're not in this one.", ephemeral=True)
            return
        session.players.remove(user_id)
        session.approach_votes.pop(user_id, None)
        BUSY_USERS.discard(user_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Go now", style=discord.ButtonStyle.danger, row=2)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.host_id:
            await interaction.response.send_message("Only the host calls it.", ephemeral=True)
            return
        self.started = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Call it off", style=discord.ButtonStyle.secondary, row=3)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.host_id:
            await interaction.response.send_message("Only the host calls it.", ephemeral=True)
            return
        self.started = False
        self.cancelled = True
        await interaction.response.edit_message(
            content="Called off.", embed=None, view=None
        )
        self.stop()

    async def on_crew(self, interaction: discord.Interaction):
        if interaction.user.id != self.session.host_id:
            await interaction.response.send_message("The host does the hiring.", ephemeral=True)
            return
        self.session.npc_ids = interaction.data["values"]
        await self.refresh(interaction)

    async def on_vote(self, interaction: discord.Interaction):
        if interaction.user.id not in self.session.players:
            await interaction.response.send_message("Join first.", ephemeral=True)
            return
        self.session.approach_votes[interaction.user.id] = interaction.data["values"][0]
        await self.refresh(interaction)


# --- Stage voting -------------------------------------------------------

class StageVoteView(discord.ui.View):
    """Everyone on the crew votes. Stops early once all of them have.

    At the escape stage only, players get an extra private option: Betray.
    It doesn't join the group vote - it opts that player out of the crew's
    decision entirely and rolls their own fate separately once the crew's
    choice resolves.
    """

    def __init__(self, session: HeistSession, stage: dict, index: int, chance: int,
                 allow_betray: bool = False):
        super().__init__(timeout=HEIST_STAGE_SECONDS)
        self.session = session
        self.votes: dict[int, str] = {}
        self.betrayed: set[int] = set()

        # Label each call with the odds it actually rolls at, not the crew's
        # current odds - the two differ by the choice modifier, and hiding
        # that made a "80%" run look like it failed at 80% when the risky
        # call had quietly dropped it to 65%.
        for key, data in stage["choices"].items():
            odds = logic.choice_odds(chance, index, key)
            self.add_item(self.ChoiceButton(self, key, f"{data['label']} — {odds}%"))
        if allow_betray:
            self.add_item(self.BetrayButton(self))

    def _decided(self) -> int:
        return len(self.votes) + len(self.betrayed)

    class ChoiceButton(discord.ui.Button):
        def __init__(self, parent_view, key: str, label: str):
            super().__init__(label=label, style=discord.ButtonStyle.primary)
            self.parent_view = parent_view
            self.key = key

        async def callback(self, interaction: discord.Interaction):
            view = self.parent_view
            user_id = interaction.user.id
            if user_id not in view.session.players:
                await interaction.response.send_message("You're not on this job.", ephemeral=True)
                return
            if user_id in view.betrayed:
                await interaction.response.send_message(
                    "You already made your move.", ephemeral=True
                )
                return
            view.votes[user_id] = self.key
            await interaction.response.send_message(f"Voted: **{self.label}**", ephemeral=True)
            if view._decided() >= len(view.session.players):
                view.stop()

    class BetrayButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="Betray", style=discord.ButtonStyle.danger, row=1)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            view = self.parent_view
            user_id = interaction.user.id
            if user_id not in view.session.players:
                await interaction.response.send_message("You're not on this job.", ephemeral=True)
                return
            if user_id in view.votes:
                await interaction.response.send_message(
                    "You already made your move.", ephemeral=True
                )
                return
            view.betrayed.add(user_id)
            await interaction.response.send_message(
                "*You keep your plan to yourself.*", ephemeral=True
            )
            if view._decided() >= len(view.session.players):
                view.stop()


# --- The cop fight ------------------------------------------------------

class CopFightView(discord.ui.View):
    """The shootout grid. Everyone clicks the same board at the same time.

    Layout is 4 rows of 5 cells plus a Take Cover button on the last row -
    Discord allows 25 components per message and that is exactly 21, so the
    grid cannot grow without dropping something else.

    Shots are per player and come from what they're carrying. A player with no
    gun can only take cover, which is the point: cover is what keeps them from
    being the one who gets hit.
    """

    def __init__(self, session: HeistSession, cells: list, shots: dict):
        super().__init__(timeout=HEIST_COP_SECONDS)
        self.session = session
        self.cells = cells
        self.shots = dict(shots)          # user_id -> shots remaining
        self.covered: set[int] = set()
        self.down: set[int] = set()       # indexes of cells already resolved
        self.cops_down = 0
        self.bystanders_hit = 0
        self.cops_total = sum(1 for c in cells if c == logic.CELL_COP)

        for index, cell in enumerate(cells):
            self.add_item(self.Cell(self, index, cell))
        self.add_item(self.CoverButton(self))

    def _finished(self) -> bool:
        """Ends early once every cop is down, or nobody can do anything else."""
        if self.cops_down >= self.cops_total:
            return True
        active = [p for p in self.session.players if p not in self.covered]
        return all(self.shots.get(p, 0) <= 0 for p in active)

    class Cell(discord.ui.Button):
        def __init__(self, parent_view, index: int, cell: str):
            emoji = {logic.CELL_COP: "🚔",
                     logic.CELL_BYSTANDER: "🧍",
                     logic.CELL_EMPTY: "⬛"}[cell]
            super().__init__(
                emoji=emoji,
                style=(discord.ButtonStyle.danger if cell == logic.CELL_COP
                       else discord.ButtonStyle.secondary),
                row=index // logic.GRID_COLS,
            )
            self.parent_view = parent_view
            self.index = index
            self.cell = cell

        async def callback(self, interaction: discord.Interaction):
            view = self.parent_view
            user_id = interaction.user.id

            if user_id not in view.session.players:
                await interaction.response.send_message("You're not on this job.", ephemeral=True)
                return
            if user_id in view.covered:
                await interaction.response.send_message(
                    "You're behind cover. Stay there.", ephemeral=True
                )
                return
            if view.shots.get(user_id, 0) <= 0:
                await interaction.response.send_message(
                    "Empty. Nothing to shoot with.", ephemeral=True
                )
                return
            if self.index in view.down:
                await interaction.response.send_message("Already down.", ephemeral=True)
                return

            # Claim the cell before anything else so two people racing the same
            # button can't both score it.
            view.down.add(self.index)
            view.shots[user_id] -= 1
            self.disabled = True

            if self.cell == logic.CELL_COP:
                view.cops_down += 1
                self.style = discord.ButtonStyle.success
                note = "Down."
            elif self.cell == logic.CELL_BYSTANDER:
                view.bystanders_hit += 1
                self.style = discord.ButtonStyle.danger
                note = "That was a civilian. That's on you."
            else:
                note = "Missed. Wasted a round."

            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{note} ({view.shots[user_id]} left)", ephemeral=True
            )
            if view._finished():
                view.stop()

    class CoverButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="Take Cover", style=discord.ButtonStyle.primary,
                             row=logic.GRID_ROWS)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            view = self.parent_view
            user_id = interaction.user.id
            if user_id not in view.session.players:
                await interaction.response.send_message("You're not on this job.", ephemeral=True)
                return

            view.covered.add(user_id)
            await interaction.response.send_message(
                "You get your head down. You're out of the fight, but you're not the one bleeding.",
                ephemeral=True,
            )
            if view._finished():
                view.stop()


def cop_embed(session: HeistSession, view: "CopFightView", shots: dict,
              guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🚔 POLICE",
        description="They were waiting for you. Drop them or get behind something — "
                    f"**{HEIST_COP_SECONDS}s**.",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Cops", value=str(view.cops_total), inline=True)
    embed.add_field(name="Bystanders", value=f"{logic.BYSTANDERS} — don't", inline=True)

    loadout = []
    for pid in session.players:
        member = guild.get_member(pid)
        who = member.display_name if member else f"user {pid}"
        count = shots.get(pid, 0)
        loadout.append(f"**{who}** — {count} shot(s)" if count else f"**{who}** — unarmed")
    embed.add_field(name="Loadout", value="\n".join(loadout), inline=False)
    embed.set_footer(text="Every cop left standing makes the way out harder.")
    return embed


async def run_cop_fight(message: discord.Message, guild: discord.Guild,
                        session: HeistSession):
    """Returns (result, loot_multiplier, escape_modifier, casualties, log_line)."""
    shots = {}
    for pid in session.players:
        inventory = await db.get_inventory(pid, guild.id)
        shots[pid] = logic.shots_for([item_id for item_id, _, _ in inventory])

    cells = logic.build_grid(len(session.players))
    view = CopFightView(session, cells, shots)
    await message.edit(embed=cop_embed(session, view, shots, guild), view=view)
    await view.wait()

    result = logic.cop_result(view.cops_down, view.bystanders_hit, view.cops_total)
    exposed = [p for p in session.players if p not in view.covered]
    casualties = logic.cop_casualties(result, exposed)

    for pid in casualties:
        await db.set_incapacitated(pid, guild.id, HEIST_SHOT_SECONDS)

    modifier = logic.cop_escape_modifier(result, bool(casualties))
    headline = {
        logic.COP_CLEAN: "✅ **Police** — every last one of them down.",
        logic.COP_HELD: "✅ **Police** — held them off, mostly.",
        logic.COP_PUSHED: "⚠️ **Police** — they pushed you back.",
        logic.COP_OVERRUN: "❌ **Police** — they walked right through you.",
    }[result]
    if view.bystanders_hit:
        headline += f" *({view.bystanders_hit} civilian hit)*"

    return result, logic.cop_loot_multiplier(result), modifier, casualties, headline


def stage_embed(session: HeistSession, stage: dict, index: int,
                chance: int, loot_mult: float, log: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"{stage['name']}  ({index + 1}/{len(logic.STAGES)})",
        description=stage["prompt"],
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Haul", value=f"×{loot_mult:.2f}", inline=True)
    embed.add_field(name="Crew", value=str(len(session.players)), inline=True)

    # Spelled out per choice: a miss inside the rough band only costs you, a
    # miss past it ends the job. Showing one blended "odds" number is what
    # made a blown run at high odds feel like a bug.
    risk = []
    for key, data in stage["choices"].items():
        odds = logic.choice_odds(chance, index, key)
        blown = logic.blown_chance(odds, logic.stage_rough_band(index))
        risk.append(f"**{data['label']}** — {odds}% clean · {blown}% blown")
    embed.add_field(name="Your options", value="\n".join(risk), inline=False)

    if log:
        embed.add_field(name="So far", value="\n".join(log[-4:]), inline=False)
    embed.set_footer(text=f"{HEIST_STAGE_SECONDS}s to vote — majority wins, ties play it safe")
    return embed


# --- The job ------------------------------------------------------------

async def run_job(message: discord.Message, guild: discord.Guild, session: HeistSession):
    """Charges everyone, runs the stages, pays out. Caller handles cleanup."""
    approach_key = session.approach
    approach = logic.APPROACHES[approach_key]

    # Anyone who can't cover their share at go-time is left behind rather than
    # put into debt. Re-checked here because the lobby sat open for a minute.
    cost = logic.per_player_cost(HEIST_BUY_IN, session.npc_ids, len(session.players))
    paying = []
    for pid in session.players:
        if await db.get_balance(pid, guild.id) >= cost:
            paying.append(pid)

    if session.host_id not in paying:
        await message.edit(
            embed=discord.Embed(
                title="Job's off",
                description=f"The host can't cover their **{cost}** coin share.",
                color=discord.Color.greyple(),
            ),
            view=None,
        )
        return

    dropped = [p for p in session.players if p not in paying]
    session.players = paying

    if approach["requires_item"]:
        inventory = await db.get_inventory(session.host_id, guild.id)
        if not any(i == approach["requires_item"] for i, _, _ in inventory):
            await message.edit(
                embed=discord.Embed(
                    title="Can't pull that off",
                    description=f"**{approach['name']}** needs the host to hold a "
                                f"`{approach['requires_item']}`.",
                    color=discord.Color.greyple(),
                ),
                view=None,
            )
            return

    # Committed: charge everyone, stamp every cooldown.
    for pid in session.players:
        await db.update_balance(pid, guild.id, -cost)
        await db.set_cooldown(pid, guild.id, "last_heist")

    count = len(session.players)
    chance = logic.calculate_success(approach_key, session.npc_ids, count)
    gross = logic.calculate_take(
        approach_key, HEIST_BASE_PAYOUT_MIN, HEIST_BASE_PAYOUT_MAX, count
    )
    loot_mult = 1.0
    log = []
    betrayals: dict[int, bool] = {}
    if dropped:
        log.append(f"*{len(dropped)} couldn't cover their share and stayed behind.*")

    for index in range(len(logic.STAGES)):
        stage = logic.get_stage(index)
        is_escape = index == len(logic.STAGES) - 1
        view = StageVoteView(session, stage, index, chance, allow_betray=is_escape)
        await message.edit(
            embed=stage_embed(session, stage, index, chance, loot_mult, log), view=view
        )
        await view.wait()

        choice_key = logic.tally_votes(view.votes, list(stage["choices"]))
        choice = logic.stage_choice(index, choice_key)

        stage_chance = chance + logic.stage_bonus(index) + choice["success"]
        result, roll = logic.resolve_stage(
            stage_chance, band=logic.stage_rough_band(index)
        )

        if result == logic.STAGE_BLOWN:
            severity = logic.blown_severity(index, roll, stage_chance)
            take = logic.blown_take(index, int(gross * loot_mult * choice["loot"]))
            log.append(f"❌ **{stage['name']}** — {choice['label']}: it went wrong.")
            await finish_blown(message, guild, session, severity, take, cost, log)
            return

        loot_mult *= choice["loot"]
        if result == logic.STAGE_ROUGH:
            chance = max(logic.MIN_SUCCESS, stage_chance - 10)
            loot_mult *= 0.85
            log.append(f"⚠️ **{stage['name']}** — {choice['label']}: close call.")
        else:
            chance = min(logic.MAX_SUCCESS, stage_chance)
            log.append(f"✅ **{stage['name']}** — {choice['flavour']}")

        # The cops turn up once the vault is open and you're holding
        # everything - between the vault and the escape, never before.
        if index == len(logic.STAGES) - 2:
            (cop_result, cop_loot, cop_modifier,
             casualties, cop_line) = await run_cop_fight(message, guild, session)
            log.append(cop_line)
            loot_mult *= cop_loot
            chance = max(logic.MIN_SUCCESS,
                         min(logic.MAX_SUCCESS, chance + cop_modifier))
            for pid in casualties:
                member = guild.get_member(pid)
                who = member.display_name if member else str(pid)
                log.append(f"🩸 **{who}** took one. The crew keeps moving.")

        if is_escape and view.betrayed:
            for pid in view.betrayed:
                betrayals[pid] = logic.roll_betrayal(approach_key)

    final_take = int(gross * loot_mult)
    after_cuts, npc_take = logic.apply_npc_cuts(final_take, session.npc_ids)
    payouts = logic.resolve_payouts(after_cuts, session.players, betrayals)

    for pid, amount in payouts.items():
        await db.update_balance(pid, guild.id, amount)

    embed = discord.Embed(
        title="Clean getaway", description="\n".join(log), color=discord.Color.green()
    )
    embed.add_field(name="Haul", value=f"{final_take} coins", inline=True)
    embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)

    if betrayals:
        lines = []
        for pid in session.players:
            member = guild.get_member(pid)
            who = member.display_name if member else f"user {pid}"
            if pid in betrayals:
                tag = "🗡️ betrayed — got away with it" if betrayals[pid] else "🗡️ betrayed — got caught"
            else:
                tag = "stayed loyal"
            lines.append(f"**{who}**: +{payouts[pid]} ({tag})")
        embed.add_field(name="Payout", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Each", value=f"**+{payouts[session.players[0]]}**", inline=True)

    embed.set_footer(text=f"Split {len(session.players)} ways, after a {cost} buy-in each")
    await message.edit(embed=embed, view=None)


async def finish_blown(message: discord.Message, guild: discord.Guild, session: HeistSession,
                       severity: str, take: int, cost: int, log: list):
    if severity == logic.MINOR_FAILURE:
        after_cuts, npc_take = logic.apply_npc_cuts(take, session.npc_ids)
        share = logic.split_between_players(after_cuts, len(session.players))
        for pid in session.players:
            await db.update_balance(pid, guild.id, share)

        embed = discord.Embed(
            title="Blown — but you're breathing",
            description="\n".join(log),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Got away with", value=f"{take} coins", inline=True)
        embed.add_field(name="Crew cut", value=f"-{npc_take}", inline=True)
        embed.add_field(name="Each", value=f"**+{share}**", inline=True)
        embed.set_footer(text=f"Buy-in was {cost} each")
        await message.edit(embed=embed, view=None)
        return

    # Bad failure: the whole crew goes down.
    losses = []
    for pid in session.players:
        await db.set_incapacitated(pid, guild.id, HEIST_SHOT_SECONDS)
        inventory = await db.get_inventory(pid, guild.id)
        if inventory:
            item_id, name, _ = random.choice(inventory)
            if await db.remove_item_from_inventory(pid, guild.id, item_id, 1):
                member = guild.get_member(pid)
                who = member.display_name if member else str(pid)
                losses.append(f"{who} dropped **{name}**")

    embed = discord.Embed(
        title="It went bad",
        description="\n".join(log) + "\n\nShots fired. Everyone's down.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Take", value="Nothing.", inline=True)
    embed.add_field(name="Lost", value="\n".join(losses) or "Nothing worth taking.", inline=True)
    embed.add_field(name="Out of action",
                    value=f"**{format_seconds(HEIST_SHOT_SECONDS)}** each", inline=False)
    await message.edit(embed=embed, view=None)


class Heist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heist", description="Put a crew together and rob the place")
    async def heist(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        if guild_id in ACTIVE_HEISTS:
            await interaction.response.send_message(
                "There's already a job being put together. Go join it.", ephemeral=True
            )
            return
        if user_id in BUSY_USERS:
            await interaction.response.send_message("You're already on a job.", ephemeral=True)
            return

        last = await db.get_cooldown(user_id, guild_id, "last_heist")
        elapsed = time.time() - last
        if elapsed < HEIST_COOLDOWN_SECONDS:
            await interaction.response.send_message(
                f"Heat's still on. Next job in **{format_seconds(HEIST_COOLDOWN_SECONDS - elapsed)}**.",
                ephemeral=True,
            )
            return

        session = HeistSession(guild_id, user_id)
        ACTIVE_HEISTS[guild_id] = session
        BUSY_USERS.add(user_id)

        # try/finally is load-bearing: if anything in here raises, these players
        # would otherwise stay "busy" forever and could never heist again.
        try:
            view = LobbyView(session)
            await interaction.response.send_message(
                embed=view.build_embed(interaction.guild), view=view
            )
            message = await interaction.original_response()

            await view.wait()
            if getattr(view, "cancelled", False):
                return

            await run_job(message, interaction.guild, session)
        except Exception:
            try:
                await interaction.followup.send(
                    "Something went wrong and the job fell apart. Nobody's on cooldown for it.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass
            raise
        finally:
            session.release()


async def setup(bot: commands.Bot):
    await bot.add_cog(Heist(bot))
