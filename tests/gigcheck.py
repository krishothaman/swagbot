"""The weekly gig: does it pay once a week, does the house boost reach it, and
does its cooldown survive a restart?

Also pins /work's cooldown, because the whole reason /gig exists is that a
weekly payout has to be worth more than a few minutes of clicking /work. If
that cooldown ever drops back to seconds, this file should be what notices.
"""
import sys
# Find the repo from this file's own location, so the suite runs from anywhere.
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Windows consoles default to cp1252 and these scripts print emoji.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# Closes aiosqlite at exit; without it the process hangs after passing.
import _harness  # noqa: F401

import asyncio
import tempfile

import config
tmp = os.path.join(tempfile.mkdtemp(), "test.db")
config.DB_PATH = tmp
import database as db
db.DB_PATH = tmp

U, G = 31, 9
WEEK = 60 * 60 * 24 * 7


async def main():
    await db.init_db()
    await db.seed_house_data()
    await db.ensure_user(U, G)

    print("=== the economy's cooldowns are spaced far enough apart to mean anything ===")
    print(f"  /work  {config.WORK_COOLDOWN_SECONDS:>7}s")
    print(f"  /daily {config.DAILY_COOLDOWN_SECONDS:>7}s")
    print(f"  /gig   {config.GIG_COOLDOWN_SECONDS:>7}s")
    assert config.WORK_COOLDOWN_SECONDS >= 15 * 60, \
        "/work is back to being a clicker - it will out-earn every paced reward in the game"
    assert config.GIG_COOLDOWN_SECONDS == WEEK, "the weekly gig isn't weekly"
    assert config.GIG_COOLDOWN_SECONDS > config.DAILY_COOLDOWN_SECONDS > config.WORK_COOLDOWN_SECONDS, \
        "the income ladder is out of order"

    print("\n=== a week's gig beats an hour of honest work ===")
    work_per_hour = (3600 / config.WORK_COOLDOWN_SECONDS) * config.WORK_MAX_REWARD
    print(f"  /work farmed for an hour: {work_per_hour:,.0f} coins")
    print(f"  one gig:                  {config.GIG_MIN_REWARD}-{config.GIG_MAX_REWARD} coins")
    assert config.GIG_MIN_REWARD > work_per_hour, \
        "a gig is worth less than an hour of /work - nobody will ever run it"

    print("\n=== the gig pays, and only once a week ===")
    from cogs.economy import claim_gig

    await db.set_balance(U, G, 0)
    paid, message = await claim_gig(U, G)
    print(f"  first claim:  paid={paid}  {message[:60]}")
    assert paid, "the very first gig was refused"
    balance = await db.get_balance(U, G)
    assert config.GIG_MIN_REWARD <= balance <= config.GIG_MAX_REWARD, \
        f"gig paid {balance}, outside {config.GIG_MIN_REWARD}-{config.GIG_MAX_REWARD}"

    paid, message = await claim_gig(U, G)
    print(f"  second claim: paid={paid}  {message[:60]}")
    assert not paid, "EXPLOIT: the gig paid twice in a row"
    assert await db.get_balance(U, G) == balance, "a refused gig still moved the balance"
    assert "d" in message or "h" in message, f"the refusal doesn't say when to come back: {message}"

    print("\n=== six days is not a week ===")
    await db.set_cooldown_at(U, G, "last_gig", __import__("time").time() - (WEEK - 3600))
    paid, message = await claim_gig(U, G)
    print(f"  at 6d23h:     paid={paid}  {message[:50]}")
    assert not paid, "the gig came off cooldown an hour early"

    print("\n=== a week later it pays again ===")
    await db.set_cooldown_at(U, G, "last_gig", __import__("time").time() - WEEK - 1)
    before = await db.get_balance(U, G)
    paid, message = await claim_gig(U, G)
    print(f"  at 7d:        paid={paid}  {message[:60]}")
    assert paid, "a full week passed and the gig still refused"
    assert await db.get_balance(U, G) > before, "the gig paid nothing"

    print("\n=== the house boost reaches the gig, same as /work and /daily ===")
    import house_perks as perks
    for house_id in ("studio", "apartment", "mansion"):
        await db.set_player_house(U, G, house_id)
        await db.set_balance(U, G, 0)
        await db.set_cooldown_at(U, G, "last_gig", 0)
        paid, message = await claim_gig(U, G)
        earned = await db.get_balance(U, G)
        floor = perks.apply_boost(config.GIG_MIN_REWARD, house_id)
        ceiling = perks.apply_boost(config.GIG_MAX_REWARD, house_id)
        print(f"  {house_id:10} (+{perks.boost_percent(house_id)}%) -> {earned:,} "
              f"(expected {floor:,}-{ceiling:,})")
        assert floor <= earned <= ceiling, f"the boost missed the gig for {house_id}"
        assert "from your place" in message, f"the gig doesn't show the house cut: {message}"

    print("\n=== the gig pays xp too ===")
    await db.set_cooldown_at(U, G, "last_gig", 0)
    xp_before, level_before = await db.get_xp_and_level(U, G)
    await claim_gig(U, G)
    xp_after, level_after = await db.get_xp_and_level(U, G)
    print(f"  xp {xp_before} -> {xp_after}, level {level_before} -> {level_after}")
    assert xp_after - xp_before == config.GIG_XP, \
        f"the gig paid {xp_after - xp_before} xp, expected {config.GIG_XP}"

    print("\n=== the cooldown is stored, not held in memory ===")
    await db.set_cooldown_at(U, G, "last_gig", 0)
    await claim_gig(U, G)
    stamp = await db.get_cooldown(U, G, "last_gig")
    print(f"  last_gig stamped at {stamp:.0f}")
    assert stamp > 0, "the gig never wrote its cooldown - a restart would hand out a free one"

    print("\ngigcheck OK")


asyncio.run(main())
