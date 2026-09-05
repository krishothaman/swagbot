"""The Gun Man - the only NPC in this city who is glad to see you.

The merchant whispers. The landlord says as little as he can get away with.
This one is the opposite failure mode: he tells you everything, twice, loudly,
including the parts you did not ask about. He is not mysterious. He is
delighted, and that is worse.

Level-gated at GUNMAN_LEVEL_REQUIREMENT. He does not really register people
below it as real, which doubles as the cheapest way to keep a brand new
account from walking out with a 7500 coin sidearm.

The guns here are permanent - buy once, keep it. The C4 is not; it's meant to
be spent. Nothing enforces that yet because nothing consumes it yet: that
lands when the heist starts reading gear.

NOT a cog, despite living in cogs/ - he has no slash commands of his own and
/talk routes into him, same as the landlord's dialogue. Do not add this to
COGS in bot.py; there's no setup() to call.
"""

import random

import discord

import database as db
import heist_logic
from config import GUNMAN_LEVEL_REQUIREMENT

GUNMAN_ID = "gun_man"

# What counts as a gun is decided by heist_logic.GUN_SHOTS - a gun IS how many
# shots it gives you in a firefight. Deriving it here instead of re-typing the
# ids means adding a gun to that table is the only edit needed.
GUN_IDS = tuple(heist_logic.GUN_SHOTS)


GREETINGS_UNARMED = [
    "HEY. Hey hey hey. Look at this face. This is the face of a man who has "
    "never once been shot. We're gonna fix that — no, NO, not like that. "
    "Relax. Come in, come in.",

    "Empty hands. Look at 'em! Terrible. Tragic. I'm gonna cry, I'm actually "
    "gonna cry. What're you buying.",

    "You came to the right guy. There is no other guy. There WAS another guy.",
]

GREETINGS_ARMED = [
    "There he is. THERE HE IS. My guy. You still got it on you? Course you do. "
    "Don't you sell that thing. I'll know.",

    "You walk different now. You feel that? That's the walk. That's MY walk, "
    "I gave you that.",

    "Back already! I love this. I LOVE this. What, you want another one? "
    "Say yes. Say yes.",
]

# Under the level requirement. He is not being careful, he's being superstitious.
REJECT_LEVEL = [
    "Whoa. Whoa whoa whoa. No. Look at you, you're brand new, you're still "
    "WET. Go be somebody first. Then we talk.",

    "Do you know what happens when I hand one of these to someone like you? "
    "Neither do I! And that scares ME. Out.",

    "I don't sell to babies. Nothing personal. It IS personal. Just not "
    "about you.",
]

REJECT_BROKE = [
    "That's not the price. That's not the — hey. HEY. Do I look like a "
    "charity to you? Don't answer that.",

    "You're short. I like you, so I'm saying it nice: you're short. "
    "Come back heavy.",

    "Cash first. Always cash first. It's the one rule and I'm the one who "
    "made it, so.",
]

# He doesn't deflect like the others do. Ask him anything and he over-shares.
RAMBLES = [
    "You wanna know about the Five-seveN? SIT DOWN. Twenty rounds. Twenty! "
    "And it goes through things it has no business going through. That's all "
    "I'm saying. That's not all I'm saying—",

    "Ohhh you noticed the C4. Yeah. YEAH. You stick it on a door and then the "
    "door is just a suggestion. Best day of my life. One of four.",

    "My brother told me I talk too much. My brother doesn't say much anymore. "
    "Different reason! Totally unrelated. What were we doing.",

    "Everybody in this city is so QUIET. The merchant, whispering. The "
    "landlord, whispering. I'm the only honest man here and I'm the maniac.",

    "The P250? It's boring. It's BORING. And it has never once lied to me. "
    "You know how many people can I say that about? Zero. It's zero.",
]


async def _owns_a_gun(user_id: int, guild_id: int) -> bool:
    inventory = await db.get_inventory(user_id, guild_id)
    return any(item_id in GUN_IDS for item_id, _, _ in inventory)


async def gunman_intro(user_id: int, guild_id: int):
    """Returns (embed, view). View is None when he won't deal with you.

    Which greeting pool he pulls from depends only on what you're carrying,
    so there's no conversation state to store anywhere.
    """
    _, level = await db.get_xp_and_level(user_id, guild_id)

    if level < GUNMAN_LEVEL_REQUIREMENT:
        embed = discord.Embed(
            title="The Gun Man",
            description=random.choice(REJECT_LEVEL),
            color=discord.Color.dark_orange(),
        )
        embed.set_footer(text=f"Come back at level {GUNMAN_LEVEL_REQUIREMENT}. You're {level}.")
        return embed, None

    armed = await _owns_a_gun(user_id, guild_id)
    greeting = random.choice(GREETINGS_ARMED if armed else GREETINGS_UNARMED)

    flavor = await db.get_npc_flavor_lines(GUNMAN_ID)
    if flavor:
        greeting = f"{greeting}\n\n*{random.choice(flavor)}*"

    embed = discord.Embed(
        title="The Gun Man",
        description=greeting,
        color=discord.Color.dark_orange(),
    )
    embed.set_footer(text="Arms dealer")
    return embed, GunmanView(user_id, guild_id)


class GunStockView(discord.ui.View):
    """His stock. Refuses a second copy of a gun you already own - they're
    permanent, so a duplicate would be pure coin loss with nothing to show."""

    def __init__(self, user_id: int, guild_id: int, items: list):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

        select = discord.ui.Select(
            placeholder="What're you buying",
            options=[
                discord.SelectOption(
                    label=f"{name} — {price} coins",
                    value=item_id,
                    description=description[:100],
                )
                for item_id, name, price, description in items
            ],
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Wait your turn.", ephemeral=True)
            return

        item_id = interaction.data["values"][0]
        item = await db.get_item(item_id)
        if not item:
            await interaction.response.send_message("He doesn't stock that.", ephemeral=True)
            return

        item_id, name, price, _npc_id, _description = item

        if item_id in GUN_IDS:
            inventory = await db.get_inventory(self.user_id, self.guild_id)
            if any(owned == item_id for owned, _, _ in inventory):
                await interaction.response.send_message(
                    f"You already GOT one. What, you want two? "
                    f"...okay that's fair actually. No. No, put it back.",
                    ephemeral=True,
                )
                return

        balance = await db.get_balance(self.user_id, self.guild_id)
        if balance < price:
            await interaction.response.send_message(
                f"{random.choice(REJECT_BROKE)}\n*({name} is {price}. You have {balance}.)*",
                ephemeral=True,
            )
            return

        await db.update_balance(self.user_id, self.guild_id, -price)
        await db.add_item_to_inventory(self.user_id, self.guild_id, item_id)
        await interaction.response.send_message(
            f"**{name}** — {price} coins. Sold.\n"
            f"*\"Don't point it at me. I'm serious. That's the only thing I'm serious about.\"*"
        )


class GunmanView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("He's not talking to you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.danger)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return

        items = await db.get_items_for_npc(GUNMAN_ID)
        if not items:
            await interaction.response.send_message(
                "\"Sold out. SOLD OUT! Come back tomorrow.\"", ephemeral=True
            )
            return

        view = GunStockView(self.user_id, self.guild_id, items)
        await interaction.response.send_message(
            "*He drags a crate out from under the counter with his foot.*", view=view
        )

    @discord.ui.button(label="Let him talk", style=discord.ButtonStyle.secondary)
    async def ramble(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.send_message(f"*\"{random.choice(RAMBLES)}\"*", ephemeral=True)
