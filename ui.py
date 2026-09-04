"""Shared embed builders so different cogs render the same things the same way."""

import discord


def build_items_embed(title: str, rows: list, empty_text: str, footer: str = None) -> discord.Embed:
    """Renders any (item_id, name, quantity) list - inventory, house storage, whatever.
    Both callers pull rows in that shape, so they stay visually identical."""
    if rows:
        description = "\n".join(f"**{name}** x{qty}" for item_id, name, qty in rows)
    else:
        description = empty_text

    embed = discord.Embed(title=title, description=description, color=discord.Color.teal())
    if footer:
        embed.set_footer(text=footer)
    return embed
