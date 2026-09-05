"""Owner-only debug tools.

Access is locked down by is_owner() below - the hard check, fails closed on
every path. Every response is also ephemeral, so nothing leaks into the
channel even for the one person who can see it.

Deliberately NOT gated by default_permissions(administrator=True): that gates
on the *server member's* permissions, not the bot owner's, so an owner without
Administrator on a given server would be locked out of their own tools. The
is_owner() check is the actual authority here regardless of server role.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import OWNER_ID, DEV_NO_COOLDOWN
from cogs.leveling import apply_level_up

log = logging.getLogger("bot")


async def is_owner(interaction: discord.Interaction) -> bool:
    """The single source of truth for who can run /dev.

    If OWNER_ID is set in .env, that account and nothing else is allowed.
    If it isn't set, we defer to whoever Discord says owns the application
    (which also covers team-owned bots). Anything unexpected denies access.
    """
    if OWNER_ID is not None:
        return interaction.user.id == OWNER_ID
    try:
        return await interaction.client.is_owner(interaction.user)
    except Exception:
        return False  # fail closed - never grant access on an error


def owner_only():
    return app_commands.check(is_owner)


class Dev(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    dev = app_commands.Group(
        name="dev",
        description="Owner-only debug tools",
        guild_only=True,
    )

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        """A denied /dev command gets a flat refusal and a log line, not a
        stack trace and not a hint that the command exists."""
        if isinstance(error, app_commands.CheckFailure):
            log.warning(
                f"Denied /dev to {interaction.user} (id: {interaction.user.id}) "
                f"in guild {interaction.guild_id}"
            )
            message = "You can't use this."
        else:
            log.error(f"/dev command error: {error!r}")
            message = f"Command failed: `{error}`"

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    def _target(self, interaction: discord.Interaction, member: discord.Member | None):
        return member or interaction.user

    # --- Economy ---

    @dev.command(name="addcoins", description="[owner] Give coins (negative to take)")
    @owner_only()
    @app_commands.describe(amount="How many coins (can be negative)", member="Defaults to you")
    async def addcoins(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        target = self._target(interaction, member)
        new_balance = await db.update_balance(target.id, interaction.guild.id, amount)
        await interaction.response.send_message(
            f"✅ `{amount:+}` coins → {target.display_name}. Balance: **{new_balance}**",
            ephemeral=True,
        )

    @dev.command(name="setbalance", description="[owner] Set a balance to an exact number")
    @owner_only()
    @app_commands.describe(amount="Exact balance to set", member="Defaults to you")
    async def setbalance(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        if amount < 0:
            await interaction.response.send_message("Balance can't be negative.", ephemeral=True)
            return
        target = self._target(interaction, member)
        new_balance = await db.set_balance(target.id, interaction.guild.id, amount)
        await interaction.response.send_message(
            f"✅ {target.display_name}'s balance set to **{new_balance}**", ephemeral=True
        )

    # --- Leveling ---

    @dev.command(name="setlevel", description="[owner] Set a level directly")
    @owner_only()
    @app_commands.describe(level="Level to set", member="Defaults to you")
    async def setlevel(self, interaction: discord.Interaction, level: int, member: discord.Member = None):
        if level < 0:
            await interaction.response.send_message("Level can't be negative.", ephemeral=True)
            return
        target = self._target(interaction, member)
        await db.set_level(target.id, interaction.guild.id, level)
        await interaction.response.send_message(
            f"✅ {target.display_name} is now **level {level}**", ephemeral=True
        )

    @dev.command(name="addxp", description="[owner] Add XP (negative to remove)")
    @owner_only()
    @app_commands.describe(amount="How much XP (can be negative)", member="Defaults to you")
    async def addxp(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        target = self._target(interaction, member)
        xp, level = await db.add_xp(target.id, interaction.guild.id, amount)
        new_level = await apply_level_up(target.id, interaction.guild.id, xp, level)
        level_note = f" (leveled up to **{new_level}**!)" if new_level != level else ""
        await interaction.response.send_message(
            f"✅ `{amount:+}` xp → {target.display_name}. Now **{xp} xp**, level **{new_level}**{level_note}",
            ephemeral=True,
        )

    @dev.command(name="resetcooldowns", description="[owner] Clear daily/work/xp/heist cooldowns")
    @owner_only()
    @app_commands.describe(member="Defaults to you")
    async def resetcooldowns(self, interaction: discord.Interaction, member: discord.Member = None):
        target = self._target(interaction, member)
        await db.reset_cooldowns(target.id, interaction.guild.id)
        await interaction.response.send_message(
            f"✅ Cooldowns cleared for {target.display_name}. /daily, /work and /heist are ready.",
            ephemeral=True,
        )

    @dev.command(name="nocooldown", description="[owner] Toggle skipping ALL cooldowns and lockouts")
    @owner_only()
    @app_commands.describe(on="Leave blank to flip it", member="Defaults to you")
    async def nocooldown(self, interaction: discord.Interaction, on: bool = None,
                         member: discord.Member = None):
        """Exempts someone from every cooldown *and* the shot lockout, for as
        long as the bot stays up. Set DEV_NO_COOLDOWN=1 in .env to have it on
        from boot instead of re-running this after every restart."""
        target = self._target(interaction, member)
        enable = (target.id not in db.NO_COOLDOWN) if on is None else on

        if enable:
            db.NO_COOLDOWN.add(target.id)
        else:
            db.NO_COOLDOWN.discard(target.id)

        state = "**OFF** — nothing is on a timer" if enable else "**ON** — timers apply again"
        await interaction.response.send_message(
            f"✅ Cooldowns for {target.display_name}: {state}\n"
            f"*(in-memory — clears if the bot restarts unless DEV_NO_COOLDOWN=1 is in .env)*",
            ephemeral=True,
        )

    # --- Items & housing ---

    @dev.command(name="giveitem", description="[owner] Put an item straight into an inventory")
    @owner_only()
    @app_commands.describe(item="Which item", qty="How many", member="Defaults to you")
    async def giveitem(self, interaction: discord.Interaction, item: str, qty: int = 1,
                       member: discord.Member = None):
        if qty <= 0:
            await interaction.response.send_message("Quantity must be positive.", ephemeral=True)
            return

        item_row = await db.get_item(item)
        if not item_row:
            await interaction.response.send_message(f"No item with id `{item}`.", ephemeral=True)
            return

        target = self._target(interaction, member)
        await db.add_item_to_inventory(target.id, interaction.guild.id, item, qty)
        await interaction.response.send_message(
            f"✅ Gave **{item_row[1]}** x{qty} to {target.display_name}", ephemeral=True
        )

    @giveitem.autocomplete("item")
    async def giveitem_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=name, value=item_id)
            for item_id, name, price in await db.get_all_items()
            if current.lower() in name.lower()
        ][:25]

    @dev.command(name="givehouse", description="[owner] Grant a house, skipping level and price checks")
    @owner_only()
    @app_commands.describe(tier="Which tier to grant", member="Defaults to you")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Studio", value=1),
        app_commands.Choice(name="Apartment", value=2),
        app_commands.Choice(name="Mansion", value=3),
    ])
    async def givehouse(self, interaction: discord.Interaction, tier: app_commands.Choice[int],
                        member: discord.Member = None):
        house = await db.get_house_by_tier(tier.value)
        if not house:
            await interaction.response.send_message("That tier doesn't exist.", ephemeral=True)
            return

        target = self._target(interaction, member)
        current = await db.get_player_house(target.id, interaction.guild.id)
        await db.set_player_house(
            target.id, interaction.guild.id, house[0], is_upgrade=current is not None
        )
        await interaction.response.send_message(
            f"✅ Gave the **{house[1]}** to {target.display_name} (free, no checks)",
            ephemeral=True,
        )

    @dev.command(name="clearhouse", description="[owner] Remove a house (leaves stored items alone)")
    @owner_only()
    @app_commands.describe(member="Defaults to you")
    async def clearhouse(self, interaction: discord.Interaction, member: discord.Member = None):
        target = self._target(interaction, member)
        house = await db.get_player_house(target.id, interaction.guild.id)
        if not house:
            await interaction.response.send_message(
                f"{target.display_name} doesn't own a house.", ephemeral=True
            )
            return

        used = await db.get_house_storage_used(target.id, interaction.guild.id)
        await db.remove_player_house(target.id, interaction.guild.id)
        note = f" ⚠️ {used} item(s) are still in house_storage." if used else ""
        await interaction.response.send_message(
            f"✅ Removed {target.display_name}'s **{house[1]}**.{note}", ephemeral=True
        )

    @dev.command(name="heal", description="[owner] Clear a heist lockout (being shot)")
    @owner_only()
    @app_commands.describe(member="Defaults to you")
    async def heal(self, interaction: discord.Interaction, member: discord.Member = None):
        target = self._target(interaction, member)
        await db.clear_incapacitated(target.id, interaction.guild.id)
        await interaction.response.send_message(
            f"✅ {target.display_name} is patched up and free to act.", ephemeral=True
        )

    # --- Inspection ---

    @dev.command(name="inspect", description="[owner] Dump someone's raw DB state")
    @owner_only()
    @app_commands.describe(member="Defaults to you")
    async def inspect(self, interaction: discord.Interaction, member: discord.Member = None):
        target = self._target(interaction, member)
        guild_id = interaction.guild.id

        balance = await db.get_balance(target.id, guild_id)
        xp, level = await db.get_xp_and_level(target.id, guild_id)
        inventory = await db.get_inventory(target.id, guild_id)
        house = await db.get_player_house(target.id, guild_id)

        embed = discord.Embed(
            title=f"DB state — {target.display_name}",
            color=discord.Color.dark_red(),
        )
        embed.add_field(name="user_id", value=str(target.id), inline=False)
        embed.add_field(name="Balance", value=str(balance), inline=True)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=str(xp), inline=True)

        if house:
            used = await db.get_house_storage_used(target.id, guild_id)
            storage = await db.get_house_storage(target.id, guild_id)
            embed.add_field(
                name="House",
                value=f"{house[1]} (tier {house[2]}) — {used}/{house[4]} slots"
                      f"{' · upgraded' if house[7] else ''}",
                inline=False,
            )
            embed.add_field(
                name="House storage",
                value="\n".join(f"{name} x{qty}" for _, name, qty in storage) or "empty",
                inline=False,
            )
        else:
            embed.add_field(name="House", value="none", inline=False)

        embed.add_field(
            name="Inventory",
            value="\n".join(f"{name} x{qty}" for _, name, qty in inventory) or "empty",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev.command(name="sync", description="[owner] Re-sync slash commands to this server instantly")
    @owner_only()
    async def sync(self, interaction: discord.Interaction):
        """Global syncs can take up to an hour to show up. Copying the global
        tree to this one guild makes new commands appear immediately."""
        await interaction.response.defer(ephemeral=True)
        self.bot.tree.copy_global_to(guild=interaction.guild)
        synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(
            f"✅ Synced **{len(synced)}** command(s) to this server.", ephemeral=True
        )

    @dev.command(name="whoami", description="[owner] Confirm the owner lock is configured")
    @owner_only()
    async def whoami(self, interaction: discord.Interaction):
        source = "OWNER_ID in .env" if OWNER_ID is not None else "Discord application owner"
        await interaction.response.send_message(
            f"You are `{interaction.user.id}` and you're authorised via **{source}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    if DEV_NO_COOLDOWN and OWNER_ID is not None:
        db.NO_COOLDOWN.add(OWNER_ID)
        log.warning(f"DEV_NO_COOLDOWN is on - owner {OWNER_ID} skips all cooldowns")
    await bot.add_cog(Dev(bot))
