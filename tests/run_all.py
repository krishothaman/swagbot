"""Runs every check script in this folder and reports what passed.

    python tests/run_all.py            # everything
    python tests/run_all.py house      # only scripts whose name contains "house"

Each check is a standalone script full of asserts - there is no test framework
here on purpose, so any one of them can also be run directly:

    python tests/perkcheck.py

A check "fails" if it raises: an AssertionError means the game rule it guards
has changed, a Traceback means it couldn't even run. Exit code is the number of
failures, so CI or a shell can branch on it.

Two gotchas worth knowing before you debug a red result:

  - Anything opening the database must close it (`await db.get_db().close()`)
    or aiosqlite's worker thread keeps the process alive after main() returns.
    That looks exactly like a hung test but is really a clean pass that never
    exited - hence the timeout below.
  - These scripts print emoji. Every one reconfigures stdout to utf-8 at the
    top, because a stock Windows console is cp1252 and would raise on the
    first slot reel.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TIMEOUT = 60

# Not checks: this runner, and any private helper.
SKIP = {"run_all.py"}


def scripts(pattern=None):
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py") or name in SKIP or name.startswith("_"):
            continue
        if pattern and pattern.lower() not in name.lower():
            continue
        yield name


def run(name):
    """True if the script ran clean. Returns (ok, reason, seconds, output)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    started = time.time()
    try:
        done = subprocess.run(
            [sys.executable, "-u", os.path.join(HERE, name)],
            cwd=REPO, env=env, timeout=TIMEOUT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except subprocess.TimeoutExpired:
        return False, f"no exit within {TIMEOUT}s (unclosed db?)", time.time() - started, ""

    took = time.time() - started
    output = done.stdout.decode("utf-8", "replace")
    if done.returncode != 0:
        # The last assert or exception line is the useful part.
        tail = [l for l in output.strip().split("\n") if l.strip()]
        return False, (tail[-1][:100] if tail else f"exit {done.returncode}"), took, output
    return True, "", took, output


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    names = list(scripts(pattern))
    if not names:
        print(f"nothing matches {pattern!r}")
        return 1

    print(f"running {len(names)} checks against {REPO}\n")
    failures = []
    for name in names:
        ok, reason, took, output = run(name)
        stem = name[:-3]
        if ok:
            print(f"  pass  {stem:<18} {took:5.1f}s")
        else:
            print(f"  FAIL  {stem:<18} {took:5.1f}s  {reason}")
            failures.append((stem, output))

    print(f"\n{len(names) - len(failures)} passed, {len(failures)} failed")
    for stem, output in failures:
        print(f"\n{'=' * 60}\n{stem}\n{'=' * 60}")
        print("\n".join(output.strip().split("\n")[-25:]))
    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
