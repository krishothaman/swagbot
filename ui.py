"""Shared embed builders so different cogs render the same things the same way."""

import discord


def format_seconds(seconds: float) -> str:
    """Cooldown countdowns, rendered the same everywhere they appear.

    Lived in cogs/economy.py until housing needed it too - and housing can't
    import economy, because economy imports the house earnings boost back out
    of housing. Shared helpers belong here rather than in whichever cog got
    there first.

    Always two units, largest first - "6d 23h", never "6d 23h 59m 12s". A
    countdown is read at a glance, and the smaller units are noise at that
    scale. Days matter because /weekly's cooldown otherwise renders as
    "167h 59m", which is correct and unreadable.
    """
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


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
