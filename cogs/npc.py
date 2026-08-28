from config import SELL_PRICE_RATIO
from discord import integrations
import discord
from discord import app_commands
from discord.ext import commands

import database as db


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
        
            


class NPCActionView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, npc_id: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.npc_id = npc_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("not your convo gng",ephemeral=True)
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


class NPC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="talk", description="Talk to an NPC")
    @app_commands.choices(npc=[
        app_commands.Choice(name="Shady Merchant", value="shady_merchant"),
    ])
    async def talk(self, interaction: discord.Interaction, npc: app_commands.Choice[str]):
        npc_data = await db.get_npc(npc.value)
        if npc_data is None:
            await interaction.response.send_message("That NPC doesn't exist.", ephemeral=True)
            return

        npc_id, name, role, greeting = npc_data

        embed = discord.Embed(title=name, description=greeting, color=discord.Color.dark_gold())
        embed.set_footer(text=role.capitalize())
        view = NPCActionView(interaction.user.id, interaction.guild.id, npc_id)
        await interaction.response.send_message(embed=embed, view=view)
    @app_commands.command(name="inventory", description="Check your items")
    async def inventory(self, interaction: discord.Interaction):
        items = await db.get_inventory(interaction.user.id, interaction.guild.id)
        if not items:
            await interaction.response.send_message("Your inventory's empty, cuh. Go buy something.")
            return

        lines = [f"**{name}** x{qty}" for item_id, name, qty in items]
        embed = discord.Embed(title="Inventory", description="\n".join(lines), color=discord.Color.teal())
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(NPC(bot))