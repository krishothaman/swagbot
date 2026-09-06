"""Does /house info show prices in BOTH cases - owning nothing and owning a house?

Calls the real command body with a fake interaction so we see the actual embed.
"""
import asyncio, os, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import config
config.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
import database as db
db.DB_PATH = config.DB_PATH

USER, GUILD = 7, 1


class FakeResponse:
    def __init__(self): self.embed = None
    async def send_message(self, embed=None, **kw): self.embed = embed


class FakeInteraction:
    def __init__(self):
        self.user = type("U", (), {"id": USER})()
        self.guild = type("G", (), {"id": GUILD})()
        self.response = FakeResponse()


def render(e):
    print(f"  TITLE: {e.title}")
    if e.description:
        print(f"  DESC : {e.description}")
    for f in e.fields:
        print(f"  [{f.name}]")
        for line in str(f.value).split("\n"):
            print(f"      {line}")
    if e.footer and e.footer.text:
        print(f"  FOOTER: {e.footer.text}")


def prices_shown(e):
    """Every house price must appear somewhere in the embed."""
    blob = " ".join([str(e.title or ""), str(e.description or "")]
                    + [str(f.value) for f in e.fields])
    return blob


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()
    await db.ensure_user(USER, GUILD)

    from cogs.housing import Housing
    cog = Housing(bot=None)
    cmd = cog.house_info.callback

    houses = await db.get_houses()
    all_prices = [h[3] for h in houses]

    print("=== CASE 1: you own nothing ===")
    it = FakeInteraction()
    await cmd(cog, it)
    render(it.response.embed)
    blob = prices_shown(it.response.embed)
    for p in all_prices:
        assert f"{p:,}" in blob or str(p) in blob, f"price {p} missing"
    print("  -> all 3 prices visible\n")

    print("=== CASE 2: you own the Studio (bottom tier) ===")
    await db.set_player_house(USER, GUILD, "studio")
    it = FakeInteraction()
    await cmd(cog, it)
    render(it.response.embed)
    blob = prices_shown(it.response.embed)
    for p in all_prices:
        assert f"{p:,}" in blob or str(p) in blob, f"price {p} missing while owning studio"
    assert "yours" in blob, "no marker showing which one you own"
    print("  -> all 3 prices visible, and yours is marked\n")

    print("=== CASE 3: you own the Mansion (top tier - the worst case before) ===")
    await db.set_player_house(USER, GUILD, "mansion", is_upgrade=True)
    it = FakeInteraction()
    await cmd(cog, it)
    render(it.response.embed)
    blob = prices_shown(it.response.embed)
    for p in all_prices:
        assert f"{p:,}" in blob or str(p) in blob, f"price {p} missing while owning mansion"
    print("  -> all 3 prices visible even at the top tier\n")

    # Discord rejects a field value over 1024 chars
    for f in it.response.embed.fields:
        assert len(str(f.value)) <= 1024, f"field '{f.name}' is {len(str(f.value))} chars, Discord caps at 1024"
    print("  embed field lengths are inside Discord's limits")

    await db.get_db().close()
    print("\nHOUSE INFO CHECKS PASSED")

asyncio.run(main())
