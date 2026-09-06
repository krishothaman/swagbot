"""The house earnings boost: does it actually reach /work, /daily and quest
turn-ins, and does a player with no house still get paid exactly the base?

Drives the real command callbacks through a stub interaction rather than
testing pay_with_boost in isolation - the bug worth catching here is a payout
site that was never wired up, and calling the helper directly would never see
it.

/work pays a random amount, so it is run twice from the same random seed - once
homeless, once housed - and the two are compared. That keeps the assertion
exact without pinning the reward range.
"""
import asyncio, os, random, sys, tempfile
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

tmp = os.path.join(tempfile.mkdtemp(), "test.db")
import config
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp
import house_perks as P
from config import DAILY_REWARD

USER, GUILD = 1, 1
SEED = 20260905


class StubResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append(content)


class StubInteraction:
    """Everything /work and /daily touch: user.id, guild.id, response."""
    def __init__(self, user_id=USER, guild_id=GUILD):
        self.user = type("U", (), {"id": user_id})()
        self.guild = type("G", (), {"id": guild_id})()
        self.response = StubResponse()


async def set_house(house_id):
    await db.remove_player_house(USER, GUILD)
    if house_id:
        await db.set_player_house(USER, GUILD, house_id)


async def run_command(command, cog):
    """Invoke a slash command's callback and report the balance delta."""
    await db.reset_cooldowns(USER, GUILD)
    before = await db.get_balance(USER, GUILD)
    interaction = StubInteraction()
    await command.callback(cog, interaction)
    after = await db.get_balance(USER, GUILD)
    return after - before, interaction.response.sent[-1]


async def main():
    await db.init_db()
    await db.seed_house_data()
    await db.seed_item_data()
    await db.seed_npc_data()
    await db.seed_quest_data()

    import cogs.housing as housing
    from cogs.economy import Economy
    from cogs.quests import turn_in_quest

    economy = Economy(None)
    await db.ensure_user(USER, GUILD)

    print("=== pay_with_boost reports base and bonus separately ===")
    for house_id in (None, "studio", "apartment", "mansion"):
        await set_house(house_id)
        await db.set_balance(USER, GUILD, 0)
        base, bonus, balance = await housing.pay_with_boost(USER, GUILD, 1000)
        print(f"  {str(house_id):10} 1000 -> {balance} (base {base} + bonus {bonus})")
        assert base == 1000, "the base was altered"
        assert balance == base + bonus, "the reported split doesn't add up"
        assert balance == P.apply_boost(1000, house_id), "helper disagrees with the perk table"

    print("\n=== /daily pays the boosted amount ===")
    for house_id in (None, "studio", "apartment", "mansion"):
        await set_house(house_id)
        gained, message = await run_command(Economy.daily, economy)
        expected = P.apply_boost(DAILY_REWARD, house_id)
        print(f"  {str(house_id):10} -> {gained} coins (want {expected})")
        assert gained == expected, f"{house_id}: got {gained}, wanted {expected}"

    assert (await run_command(Economy.daily, economy))[0] == P.apply_boost(DAILY_REWARD, "mansion")

    print("\n=== /work pays the boosted amount (same seed, housed vs not) ===")
    await set_house(None)
    random.seed(SEED)
    base_gain, _ = await run_command(Economy.work, economy)
    print(f"  no house   -> {base_gain} coins")
    assert base_gain > 0, "/work paid nothing"

    for house_id in ("studio", "apartment", "mansion"):
        await set_house(house_id)
        random.seed(SEED)
        gained, message = await run_command(Economy.work, economy)
        expected = P.apply_boost(base_gain, house_id)
        print(f"  {house_id:10} -> {gained} coins (want {expected})")
        assert gained == expected, f"{house_id}: got {gained}, wanted {expected}"

    print("\n=== quest rewards are boosted too ===")
    quest = await db.get_quest("daily_hustle")
    reward = quest["reward_coins"]
    print(f"  daily_hustle pays {reward}")
    assert reward > 0, "picked a quest with no coin reward"

    for house_id in (None, "studio", "mansion"):
        await set_house(house_id)
        # The condition is "hold 500 coins", which nothing consumes, so the
        # only balance movement across the turn-in is the reward itself.
        await db.set_balance(USER, GUILD, 500)
        await db.clear_player_quest(USER, GUILD, "daily_hustle")
        await db.set_player_quest_status(USER, GUILD, "daily_hustle", "active")
        before = await db.get_balance(USER, GUILD)
        message = await turn_in_quest(USER, GUILD, "daily_hustle")
        gained = await db.get_balance(USER, GUILD) - before
        expected = P.apply_boost(reward, house_id)
        print(f"  {str(house_id):10} -> {gained} coins (want {expected})")
        assert "complete" in message.lower(), f"quest didn't turn in: {message}"
        assert gained == expected, f"{house_id}: got {gained}, wanted {expected}"

    print("\n=== the homeless are paid exactly the base, everywhere ===")
    await set_house(None)
    gained, _ = await run_command(Economy.daily, economy)
    assert gained == DAILY_REWARD, f"no house paid {gained}, not {DAILY_REWARD}"
    print(f"  /daily with no house -> {gained} (base is {DAILY_REWARD})")

    print("\n=== rent itself is NOT boosted (that would be paying twice) ===")
    await set_house("mansion")
    d = db.get_db()
    import time
    await d.execute(
        "UPDATE player_houses SET last_collect_at = ? WHERE user_id = ? AND guild_id = ?",
        (time.time() - 2 * P.SECONDS_PER_DAY, USER, GUILD),
    )
    await d.commit()
    before = await db.get_balance(USER, GUILD)
    await housing.collect_rent(USER, GUILD)
    gained = await db.get_balance(USER, GUILD) - before
    print(f"  2 days of mansion rent -> {gained} (flat rate, not {P.apply_boost(3000, 'mansion')})")
    assert gained == 3000, f"rent was boosted: {gained}"

    await db.get_db().close()
    print("\nboostcheck OK")


if __name__ == "__main__":
    asyncio.run(main())
