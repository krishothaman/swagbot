import discord
from discord import app_commands
from discord.ext import commands

import database as db

import discord
from discord import app_commands
from discord.ext import commands

import database as db


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
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(NPC(bot))