import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
import house_perks as perks
from config import HOUSE_SELL_RATIO, HOUSE_LEVEL_REQUIREMENTS
from ui import build_items_embed, format_seconds

LANDLORD_ID = "landlord"

# The landlord never explains himself. Every pool below is short, flat, and
# occasionally knows more about the building than it should.
GREETINGS_PROSPECT = [
    "You're standing in my lobby. State your business.",
    "No keys for you yet. Come back when you can afford one.",
    "You've got the look of someone who moves a lot. That stops here.",
]

GREETINGS_TENANT = [
    "Welcome home. Don't damage the walls.",
    "Your unit's still standing. That's not always the case.",
    "You're quieter than the last one. Keep it that way.",
]

GREETINGS_UPGRADED = [
    "Funny. This building didn't used to have a fifth floor.",
    "Bigger place. Same rules. Same walls, mostly.",
    "You moved up. The paperwork was already filled out.",
]

# Used when the player pokes at something he said. He never answers.
DEFLECTIONS = [
    "Rent's due the first. Same as always.",
    "I said what I said. Check your lease.",
    "That's not a maintenance issue. Was there something else?",
    "The building's older than your questions.",
    "Rent's due the first. It was due the first before you got here, too.",
]

REJECT_BROKE = [
    "Come back with the full amount. I don't do payment plans.",
    "That's not enough. I can count.",
    "The price is the price. It was the price for the last tenant, too.",
]

REJECT_LEVEL = [
    "You're not ready for that door. Keep working.",
    "I don't rent to people who just got here.",
    "Not yet. The building decides these things before I do.",
]


def _greeting_for(house_row) -> str:
    """Which pool he pulls from depends purely on what the player owns,
    so we don't need to track conversation state anywhere."""
    if house_row is None:
        return random.choice(GREETINGS_PROSPECT)
    if house_row[7] is not None:  # upgraded_at
        return random.choice(GREETINGS_UPGRADED)
    return random.choice(GREETINGS_TENANT)


async def landlord_embed(user_id: int, guild_id: int) -> discord.Embed:
    house = await db.get_player_house(user_id, guild_id)
    embed = discord.Embed(
        title="The Landlord",
        description=_greeting_for(house),
        color=discord.Color.dark_grey(),
    )
    if house:
        house_id, name, tier, price, storage_slots, description, purchased_at, upgraded_at = house
        used = await db.get_house_storage_used(user_id, guild_id)
        embed.add_field(name="Your Unit", value=name, inline=True)
        embed.add_field(name="Storage", value=f"{used}/{storage_slots}", inline=True)
    else:
        embed.add_field(name="Your Unit", value="None", inline=True)
    embed.set_footer(text="Landlord")
    return embed


class HouseListingView(discord.ui.View):
    """Select menu of everything the landlord has available."""

    def __init__(self, user_id: int, guild_id: int, houses: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label=f"{name} - {price} coins",
                value=house_id,
                description=description[:100],
            )
            for house_id, name, tier, price, storage_slots, description in houses
        ]

        select = discord.ui.Select(placeholder="Pick a unit", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your lease.", ephemeral=True)
            return

        house = await db.get_house(interaction.data["values"][0])
        if not house:
            await interaction.response.send_message("That unit doesn't exist.", ephemeral=True)
            return

        message = await purchase_house(self.user_id, self.guild_id, house[2])
        await interaction.response.send_message(message, ephemeral=True)


class LandlordView(discord.ui.View):
    """Buttons the landlord offers. Mirrors NPCActionView's guard pattern."""

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your convo.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Buy / Upgrade", style=discord.ButtonStyle.primary)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        houses = await db.get_houses()
        current = await db.get_player_house(self.user_id, self.guild_id)
        if current:
            houses = [h for h in houses if h[2] > current[2]]  # only upgrades
        if not houses:
            await interaction.response.send_message(
                "There's nothing above you. You're already at the top of the building.",
                ephemeral=True,
            )
            return

        view = HouseListingView(self.user_id, self.guild_id, houses)
        await interaction.response.send_message("These are open.", view=view, ephemeral=True)

    @discord.ui.button(label="Sell", style=discord.ButtonStyle.secondary)
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        message = await sell_house(self.user_id, self.guild_id)
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Storage", style=discord.ButtonStyle.success)
    async def storage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        house = await db.get_player_house(self.user_id, self.guild_id)
        if not house:
            await interaction.response.send_message(
                "You don't have anywhere to put anything.", ephemeral=True
            )
            return

        rows = await db.get_house_storage(self.user_id, self.guild_id)
        used = await db.get_house_storage_used(self.user_id, self.guild_id)
        embed = build_items_embed(
            f"{house[1]} — Storage",
            rows,
            "Empty. Previous tenant left it that way.",
            footer=f"{used}/{house[4]} slots used",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="\"What?\"", style=discord.ButtonStyle.secondary)
    async def push(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.send_message(random.choice(DEFLECTIONS), ephemeral=True)


async def purchase_house(user_id: int, guild_id: int, tier: int) -> str:
    """Shared by /house buy and the landlord's select menu. Returns the line
    the landlord says back, whether it worked or not."""
    house = await db.get_house_by_tier(tier)
    if not house:
        return "No such unit in this building."

    house_id, name, tier, price, storage_slots, description = house
    current = await db.get_player_house(user_id, guild_id)

    if current:
        current_tier = current[2]
        if current_tier == tier:
            return f"You already live in the {name}. Try the door."
        if current_tier > tier:
            return "Downsizing means selling first. I don't hold two leases for one person."

    level = (await db.get_xp_and_level(user_id, guild_id))[1]
    required_level = HOUSE_LEVEL_REQUIREMENTS.get(tier, 0)
    if level < required_level:
        return f"{random.choice(REJECT_LEVEL)} *(need level {required_level}, you're {level})*"

    # Upgrading trades the old unit in at the same rate he'd buy it back for.
    trade_in = int(current[3] * HOUSE_SELL_RATIO) if current else 0
    cost = max(price - trade_in, 0)

    balance = await db.get_balance(user_id, guild_id)
    if balance < cost:
        return f"{random.choice(REJECT_BROKE)} *({cost} coins, you have {balance})*"

    await db.update_balance(user_id, guild_id, -cost)
    await db.set_player_house(user_id, guild_id, house_id, is_upgrade=current is not None)

    if current:
        return (
            f"Keys to the **{name}**. {cost} coins after the trade-in on the {current[1]}.\n"
            f"*{random.choice(GREETINGS_UPGRADED)}*"
        )
    return (
        f"Keys to the **{name}**. {cost} coins. {storage_slots} slots of storage.\n"
        f"*Welcome home. Don't damage the walls.*"
    )


async def pay_with_boost(user_id: int, guild_id: int, amount: int):
    """Credit `amount`, plus whatever the player's house adds on top.

    The one place the earnings boost is applied, so /work, /daily, quest
    rewards and anything added later all agree on what the boost means without
    each re-implementing the percentage. Returns (base, bonus, new_balance) so
    the caller can show the bonus - a perk the player can't see may as well not
    exist.
    """
    house = await db.get_player_house(user_id, guild_id)
    house_id = house[0] if house else None
    total = perks.apply_boost(amount, house_id)
    new_balance = await db.update_balance(user_id, guild_id, total)
    return amount, total - amount, new_balance


async def collect_rent(user_id: int, guild_id: int) -> str:
    """Hand over whatever rent has piled up since the last collection."""
    house = await db.get_player_house(user_id, guild_id)
    if not house:
        return "You don't collect anything. You don't own anything."

    house_id, name, tier, price, storage_slots, description, purchased_at, upgraded_at = house
    rate = perks.rent_rate(house_id)
    stamp = await db.get_house_rent_stamp(user_id, guild_id)
    now = time.time()

    # Bought their place before rent existed, so the ledger is at its 0 default.
    # Open it now rather than reading 0 as "collecting since 1970".
    if stamp <= 0:
        await db.set_house_rent_stamp(user_id, guild_id, now)
        return (
            f"Ledger's open on the **{name}**. **{rate:,}** a day from here on. "
            "Come back tomorrow."
        )

    days = perks.days_accrued(stamp, now)
    if days <= 0:
        wait = perks.seconds_until_next_day(stamp, now)
        return f"Nothing's due yet. Next **{rate:,}** in **{format_seconds(wait)}**."

    owed = rate * days
    new_balance = await db.update_balance(user_id, guild_id, owed)
    await db.set_house_rent_stamp(user_id, guild_id, perks.advance_stamp(stamp, now))

    capped = ""
    if days >= perks.RENT_CAP_DAYS:
        capped = (
            f" That's the {perks.RENT_CAP_DAYS} day ceiling — "
            "anything older than that, I already spent."
        )
    return (
        f"**{owed:,}** coins off the **{name}**. {days} day(s) at {rate:,}.{capped}\n"
        f"Balance: **{new_balance:,}**"
    )


async def sell_house(user_id: int, guild_id: int) -> str:
    house = await db.get_player_house(user_id, guild_id)
    if not house:
        return "You don't own anything here. Can't sell what isn't yours."

    house_id, name, tier, price, storage_slots, description, purchased_at, upgraded_at = house

    # Refuse rather than delete their items - they can always withdraw first.
    used = await db.get_house_storage_used(user_id, guild_id)
    if used > 0:
        return (
            f"There's still {used} item(s) in there. Empty it first — "
            "I'm not responsible for what gets left behind."
        )

    refund = int(price * HOUSE_SELL_RATIO)
    await db.remove_player_house(user_id, guild_id)
    await db.update_balance(user_id, guild_id, refund)
    return f"The **{name}** is back on the market. **{refund}** coins. Leave the key."


class Housing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    house = app_commands.Group(name="house", description="Buy, sell, and stock your place")

    async def _item_autocomplete(self, interaction: discord.Interaction, current: str, rows: list):
        return [
            app_commands.Choice(name=f"{name} x{qty}", value=item_id)
            for item_id, name, qty in rows
            if current.lower() in name.lower()
        ][:25]

    @house.command(name="info", description="Look at your place, and what's for sale")
    async def house_info(self, interaction: discord.Interaction):
        house = await db.get_player_house(interaction.user.id, interaction.guild.id)
        owned_id = house[0] if house else None

        if house:
            house_id, name, tier, price, storage_slots, description, purchased_at, upgraded_at = house
            used = await db.get_house_storage_used(interaction.user.id, interaction.guild.id)
            embed = discord.Embed(title=name, description=description, color=discord.Color.dark_grey())
            embed.add_field(name="Tier", value=str(tier), inline=True)
            embed.add_field(name="Storage", value=f"{used}/{storage_slots}", inline=True)
            embed.add_field(name="Sells back for", value=f"{int(price * HOUSE_SELL_RATIO):,} coins", inline=True)
        else:
            embed = discord.Embed(title="Available Units", color=discord.Color.dark_grey())
            embed.set_footer(text="You don't own anything yet.")

        # The listing goes out whether you own a place or not. It used to be the
        # else-branch of the block above, so an owner couldn't see what an upgrade
        # cost, and a top-tier owner couldn't see prices anywhere - the landlord's
        # Buy/Upgrade menu filters to tiers above yours and shows nothing at the top.
        lines = []
        for house_id, name, tier, price, storage_slots, description in await db.get_houses():
            required = HOUSE_LEVEL_REQUIREMENTS.get(tier, 0)
            marker = " — *yours*" if house_id == owned_id else ""
            lines.append(
                f"**{name}**{marker}\n{price:,} coins · {storage_slots} slots · level {required}+"
            )
        embed.add_field(name="Every unit", value="\n\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed)

    @house.command(name="buy", description="Buy or upgrade into a house")
    @app_commands.describe(tier="Which unit you want")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Studio", value=1),
        app_commands.Choice(name="Apartment", value=2),
        app_commands.Choice(name="Mansion", value=3),
    ])
    async def house_buy(self, interaction: discord.Interaction, tier: app_commands.Choice[int]):
        message = await purchase_house(interaction.user.id, interaction.guild.id, tier.value)
        await interaction.response.send_message(message)

    @house.command(name="collect", description="Collect the rent your place has earned")
    async def house_collect(self, interaction: discord.Interaction):
        message = await collect_rent(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(message)

    @house.command(name="sell", description="Sell your house back to the landlord")
    async def house_sell(self, interaction: discord.Interaction):
        message = await sell_house(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(message)

    @house.command(name="deposit", description="Move an item from your inventory into house storage")
    @app_commands.describe(item="What to store", qty="How many")
    async def house_deposit(self, interaction: discord.Interaction, item: str, qty: int = 1):
        user_id, guild_id = interaction.user.id, interaction.guild.id

        if qty <= 0:
            await interaction.response.send_message("Amount must be positive.", ephemeral=True)
            return

        house = await db.get_player_house(user_id, guild_id)
        if not house:
            await interaction.response.send_message(
                "You don't have a place to store that.", ephemeral=True
            )
            return

        storage_slots = house[4]
        used = await db.get_house_storage_used(user_id, guild_id)
        if used + qty > storage_slots:
            await interaction.response.send_message(
                f"Won't fit. {used}/{storage_slots} slots used, you're trying to add {qty}.",
                ephemeral=True,
            )
            return

        item_row = await db.get_item(item)
        if not item_row:
            await interaction.response.send_message("Invalid item", ephemeral=True)
            return

        # Take it out of the inventory first so a failure can't duplicate items.
        if not await db.remove_item_from_inventory(user_id, guild_id, item, qty):
            await interaction.response.send_message("You don't have that many.", ephemeral=True)
            return

        await db.add_item_to_house_storage(user_id, guild_id, item, qty)
        await interaction.response.send_message(
            f"Stored **{item_row[1]}** x{qty} in your {house[1]}. ({used + qty}/{storage_slots})"
        )

    @house_deposit.autocomplete("item")
    async def deposit_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await db.get_inventory(interaction.user.id, interaction.guild.id)
        return await self._item_autocomplete(interaction, current, rows)

    @house.command(name="withdraw", description="Take an item back out of house storage")
    @app_commands.describe(item="What to take", qty="How many")
    async def house_withdraw(self, interaction: discord.Interaction, item: str, qty: int = 1):
        user_id, guild_id = interaction.user.id, interaction.guild.id

        if qty <= 0:
            await interaction.response.send_message("Amount must be positive.", ephemeral=True)
            return

        house = await db.get_player_house(user_id, guild_id)
        if not house:
            await interaction.response.send_message("You don't have a house.", ephemeral=True)
            return

        item_row = await db.get_item(item)
        if not item_row:
            await interaction.response.send_message("Invalid item", ephemeral=True)
            return

        if not await db.remove_item_from_house_storage(user_id, guild_id, item, qty):
            await interaction.response.send_message("That's not in there.", ephemeral=True)
            return

        await db.add_item_to_inventory(user_id, guild_id, item, qty)
        await interaction.response.send_message(
            f"Took **{item_row[1]}** x{qty} out of your {house[1]}."
        )

    @house_withdraw.autocomplete("item")
    async def withdraw_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await db.get_house_storage(interaction.user.id, interaction.guild.id)
        return await self._item_autocomplete(interaction, current, rows)


async def setup(bot: commands.Bot):
    await bot.add_cog(Housing(bot))
