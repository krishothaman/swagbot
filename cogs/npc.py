import random

from config import SELL_PRICE_RATIO
from discord import integrations
import discord
from discord import app_commands
from discord.ext import commands

import database as db
from ui import build_items_embed
from cogs.housing import LandlordView, landlord_embed, LANDLORD_ID


class BuyView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, items: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label=f"{name} - {price} coins",
                value=item_id,
                description=description[:100],
            )
            for item_id, name, price, description in items
        ]

        select = discord.ui.Select(placeholder="Pick something to buy", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = await db.get_item(item_id)
        if not item:
            await interaction.response.send_message("Invalid item", ephemeral=True)
            return
        
        item_id, name, price, npc_id, description = item

        balance = await db.get_balance(self.user_id, self.guild_id)
        if balance < price:
            await interaction.response.send_message("git gud bro", ephemeral=True)
            return
        await db.update_balance(self.user_id, self.guild_id, -price)
        await db.add_item_to_inventory(self.user_id, self.guild_id, item_id)
        await interaction.response.send_message(f"You bought {name} for {price} coins")
        
class SellView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, inventory: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label=f"{name} x{qty}",
                value=item_id,
            )
            for item_id, name, qty in inventory
        ]

        select = discord.ui.Select(placeholder="Pick something to sell", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction : discord.Interaction):
        item_id = interaction.data['values'][0]
        item = await db.get_item(item_id)
        if not item:
            await interaction.response.send_message("Invalid item", ephemeral=True)
            return
        item_id, name, price, npc_id , description = item

        sell_price = int(price * SELL_PRICE_RATIO)
        success = await db.remove_item_from_inventory(self.user_id, self.guild_id, item_id, 1)
        if not success:
            await interaction.response.send_message("what are you selling??.", ephemeral=True)
            return
        await db.update_balance(self.user_id, self.guild_id, sell_price)
        await interaction.response.send_message(f"You sold {name} for {sell_price} coins", ephemeral=True)
class QuestView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, quest_id: str, status: str, reward_coins: int, reward_xp: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.quest_id = quest_id
        self.reward_coins = reward_coins
        self.reward_xp = reward_xp

        if status == "available":
            self.add_item(self.AcceptButton(self))
        elif status == "active":
            self.add_item(self.CompleteButton(self))

    class AcceptButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="Accept Quest", style=discord.ButtonStyle.primary)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.user_id:
                await interaction.response.send_message("Not your quest, selfish f**k", ephemeral=True)
                return
            await db.set_player_quest_status(
                self.parent_view.user_id, self.parent_view.guild_id, self.parent_view.quest_id, "active"
            )
            await interaction.response.edit_message(
                content="you got it.", embed=None, view=None
            )

    class CompleteButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="Turn In Quest", style=discord.ButtonStyle.success)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.user_id:
                await interaction.response.send_message("Not your quest gng.", ephemeral=True)
                return
            await db.set_player_quest_status(
                self.parent_view.user_id, self.parent_view.guild_id, self.parent_view.quest_id, "completed"
            )
            await db.update_balance(self.parent_view.user_id, self.parent_view.guild_id, self.parent_view.reward_coins)
            await db.add_xp(self.parent_view.user_id, self.parent_view.guild_id, self.parent_view.reward_xp)
            await interaction.response.edit_message(
                content=f"ayy you actually did it, gng. +{self.parent_view.reward_coins} coins, +{self.parent_view.reward_xp} xp",
                embed=None,
                view=None,
            )
        
            


class NPCActionView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, npc_id: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.npc_id = npc_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your convo.",ephemeral=True)
            return False
        return True    

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.primary)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        items = await db.get_items_for_npc(self.npc_id)
        if not items:
            await interaction.response.send_message("Nothing is for sale right now",ephemeral=True)
            return
        view = BuyView(interaction.user.id, interaction.guild.id, items)
        await interaction.response.send_message("Watchu buying?", view=view)


    @discord.ui.button(label="Sell", style=discord.ButtonStyle.secondary)
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        inventory = await db.get_inventory(self.user_id, self.guild_id)
        if not inventory:
            await interaction.response.send_message("You ain't got nothing to sell", ephemeral=True)
            return

        view = SellView(self.user_id, self.guild_id, inventory)
        await interaction.response.send_message("Sellin what?", view=view, ephemeral=True)

    @discord.ui.button(label="Quests", style=discord.ButtonStyle.success)
    async def quests_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        quests = await db.get_quests_for_npc(self.npc_id)
        if not quests:
            await interaction.response.send_message("No quests here right now.", ephemeral=True)
            return

        for quest_id, title, description, reward_coins, reward_xp in quests:
            status = await db.get_player_quest_status(self.user_id, self.guild_id, quest_id)
            if status != "completed":
                view = QuestView(self.user_id, self.guild_id, quest_id, status, reward_coins, reward_xp)
                embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
                embed.add_field(name="Reward", value=f"{reward_coins} coins, {reward_xp} xp")
            embed.add_field(name="Status", value=status.capitalize())
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        await interaction.response.send_message("you have done everything for now. return back later", ephemeral=True)


class InventoryView(discord.ui.View):
    """Toggles /inventory between what you're carrying and what's in your house.
    Both tabs go through build_items_embed, just pointed at a different table."""

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your stuff.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Carrying", style=discord.ButtonStyle.primary)
    async def carrying(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        items = await db.get_inventory(self.user_id, self.guild_id)
        embed = build_items_embed("Inventory", items, "You got nothin on u rn.")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="House", style=discord.ButtonStyle.secondary)
    async def house(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        house = await db.get_player_house(self.user_id, self.guild_id)
        if not house:
            await interaction.response.send_message(
                "You don't own a place yet. Go talk to the landlord.", ephemeral=True
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
        await interaction.response.edit_message(embed=embed, view=self)


class NPC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="talk", description="Talk to an NPC")
    @app_commands.choices(npc=[
        app_commands.Choice(name="Weird looking merchant", value="shady_merchant"),
        app_commands.Choice(name="Landlord", value=LANDLORD_ID),
    ])
    async def talk(self, interaction: discord.Interaction, npc: app_commands.Choice[str]):
        npc_data = await db.get_npc(npc.value)
        if npc_data is None:
            await interaction.response.send_message("That NPC doesn't exist. Schizophrenic?", ephemeral=True)
            return

        npc_id, name, role, greeting = npc_data

        # The landlord runs his own dialogue - what he says depends on what you own.
        if npc_id == LANDLORD_ID:
            embed = await landlord_embed(interaction.user.id, interaction.guild.id)
            view = LandlordView(interaction.user.id, interaction.guild.id)
            await interaction.response.send_message(embed=embed, view=view)
            return

        flavor = await db.get_npc_flavor_lines(npc_id)
        if flavor:
            greeting = f"{greeting}\n\n*{random.choice(flavor)}*"

        embed = discord.Embed(title=name, description=greeting, color=discord.Color.dark_gold())
        embed.set_footer(text=role.capitalize())
        view = NPCActionView(interaction.user.id, interaction.guild.id, npc_id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="inventory", description="Check your items")
    async def inventory(self, interaction: discord.Interaction):
        items = await db.get_inventory(interaction.user.id, interaction.guild.id)
        embed = build_items_embed("Inventory", items, "You got nothin on u rn.")
        view = InventoryView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(NPC(bot))