"""The Part 1 manual pass, played end to end against a real database.

Drives the actual slash-command callbacks and prints every message and embed
exactly as they'd be rendered, so the player-facing text and the /house info
layout can be read without a Discord client.

What this canNOT prove: that the commands register with Discord's API and that
embeds render inside the client. loadall.py covers registration; the rest is a
human in a server.
"""
import asyncio, os, sys, tempfile, time
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

tmp = os.path.join(tempfile.mkdtemp(), "walk.db")
import config
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp
import house_perks as P
import heist_logic as L

U, G = 42, 7
DAY = P.SECONDS_PER_DAY


def rule(title):
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def show_embed(embed):
    """Render a discord.Embed the way it reads on screen."""
    print(f"  ┌─ {embed.title or '(no title)'}")
    if embed.description:
        for line in str(embed.description).split("\n"):
            print(f"  │  {line}")
    for f in embed.fields:
        print(f"  ├─ {f.name}" + ("   [inline]" if f.inline else ""))
        for line in str(f.value).split("\n"):
            print(f"  │    {line}")
    if embed.footer and embed.footer.text:
        print(f"  └─ {embed.footer.text}")
    else:
        print("  └─")


class Response:
    def __init__(self):
        self.content = None
        self.embed = None

    async def send_message(self, content=None, embed=None, view=None, **kw):
        self.content, self.embed = content, embed


class Interaction:
    def __init__(self):
        self.user = type("U", (), {"id": U})()
        self.guild = type("G", (), {"id": G, "get_member": lambda s, i: None})()
        self.response = Response()


async def run(command, cog):
    i = Interaction()
    await command.callback(cog, i)
    return i.response


async def rewind(days):
    d = db.get_db()
    await d.execute(
        "UPDATE player_houses SET last_collect_at = ? WHERE user_id = ? AND guild_id = ?",
        (time.time() - days * DAY, U, G),
    )
    await d.commit()


async def main():
    await db.init_db()
    await db.seed_npc_data()
    await db.seed_item_data()
    await db.seed_house_data()
    await db.seed_quest_data()

    import cogs.housing as housing
    from cogs.housing import Housing
    from cogs.economy import Economy
    import cogs.heist as heist

    houses, economy = Housing(None), Economy(None)
    await db.ensure_user(U, G)

    rule("1. A fresh player buys a Studio")
    await db.set_level(U, G, 3)
    await db.set_balance(U, G, 10_000)
    print("  balance before:", await db.get_balance(U, G))
    print("  landlord:", await housing.purchase_house(U, G, 1))
    print("  balance after :", await db.get_balance(U, G))

    rule("2. /house collect straight after buying — should refuse")
    print("  ", await housing.collect_rent(U, G))

    rule("3. /work in a Studio — should show +5%")
    await db.reset_cooldowns(U, G)
    print("  ", (await run(Economy.work, economy)).content)

    rule("4. /daily in a Studio")
    await db.reset_cooldowns(U, G)
    print("  ", (await run(Economy.daily, economy)).content)

    rule("5. /house info — the layout with the new perk fields")
    show_embed((await run(Housing.house_info, houses)).embed)

    rule("6. The landlord's greeting embed")
    show_embed(await housing.landlord_embed(U, G))

    rule("7. Three days pass, then /house collect")
    await rewind(3)
    print("  ", await housing.collect_rent(U, G))
    print("   immediately again:", await housing.collect_rent(U, G))

    rule("8. Upgrade to a Mansion")
    await db.set_level(U, G, 25)
    await db.set_balance(U, G, 600_000)
    print("  landlord:", await housing.purchase_house(U, G, 3))
    print("  NOTE: upgrading forfeits accrued rent by design —")
    print("        rent waiting is now:", P.rent_owed("mansion", await db.get_house_rent_stamp(U, G)))

    rule("9. /work and /daily in a Mansion — should show +20%")
    await db.reset_cooldowns(U, G)
    print("  ", (await run(Economy.work, economy)).content)
    await db.reset_cooldowns(U, G)
    print("  ", (await run(Economy.daily, economy)).content)

    rule("10. Two days of Mansion rent")
    await rewind(2)
    print("  ", await housing.collect_rent(U, G))

    rule("11. A month away — the 7 day cap")
    await rewind(30)
    print("  ", await housing.collect_rent(U, G))

    rule("12. /house info as a Mansion owner")
    show_embed((await run(Housing.house_info, houses)).embed)

    rule("13. The heist odds line with a Mansion on the crew")

    class StubGuild:
        id = G

    session = heist.HeistSession(G, U)
    session.players = [U]
    approach = "force"

    chance = L.calculate_success(approach, session.npc_ids, 1)
    gear = L.gear_bonus(await heist.collect_gear(StubGuild(), session.players), approach)
    crew_houses = await heist.collect_houses(StubGuild(), session.players)
    house_bonus = P.house_heist_bonus(crew_houses)
    print(f"  crew houses: {crew_houses}")
    print(f"  base {chance}%  gear +{gear}  house +{house_bonus}")

    final = max(L.MIN_SUCCESS, min(L.MAX_SUCCESS, chance + gear + house_bonus))
    log = []
    if gear:
        log.append(f"*The crew's gear is worth **+{gear}%** on this approach.*")
    if house_bonus:
        log.append(f"*Somebody on this crew owns a Mansion. **+{house_bonus}%**.*")

    show_embed(heist.stage_embed(session, L.get_stage(0), 0, final, 1.0, log))

    rule("14. Same crew, sold the Mansion — the +2 should vanish")
    await db.remove_player_house(U, G)
    crew_houses = await heist.collect_houses(StubGuild(), session.players)
    print(f"  crew houses: {crew_houses}")
    print(f"  house bonus: +{P.house_heist_bonus(crew_houses)}  (was +2)")

    await db.get_db().close()
    print("\nwalkthrough complete")


if __name__ == "__main__":
    asyncio.run(main())
