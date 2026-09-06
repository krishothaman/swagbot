"""Shared plumbing for the check scripts. Imported for its side effect only.

The problem this solves: aiosqlite runs its queries on a background thread, and
that thread is NOT a daemon. So once a check calls `db.init_db()`, the process
cannot exit until the connection is closed - `main()` returns, every assert has
already passed, and then python just sits there forever.

That failure mode is nasty because it looks nothing like what it is. The script
prints "CHECKS PASSED" and then hangs, so a runner with a timeout reports a
failure and a runner without one hangs the whole suite. Worse, a sweep that
kills the script and greps its output for "AssertionError" scores it as a
*pass* - which is exactly how nine of these sat green while never exiting.

atexit is too late to fix it: CPython joins non-daemon threads *before* it runs
atexit callbacks, so by the time a handler could close the connection the
interpreter is already blocked waiting on the very thread the close would end.

So instead we wrap `asyncio.run`. Every check ends with `asyncio.run(main())`,
and this closes the connection inside that same loop the moment main() returns -
on the exception path too, so a failing assert still exits instead of hanging
and disguising itself as a timeout.
"""

import asyncio
import sys

_real_run = asyncio.run


async def _close_database():
    database = sys.modules.get("database")
    connection = getattr(database, "_db", None)
    if connection is None:
        return
    # Clear the module global first: a check that runs a second loop (rentcheck
    # opens a fresh DB to test the migration) must call init_db again rather
    # than reuse a closed handle.
    database._db = None
    await connection.close()


def _run(coro, **kwargs):
    async def _with_teardown():
        try:
            return await coro
        finally:
            await _close_database()

    return _real_run(_with_teardown(), **kwargs)


asyncio.run = _run
