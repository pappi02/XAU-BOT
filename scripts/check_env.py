"""Preflight check for required environment variables (Phase 0.5).

Run before starting the bot:

    python scripts/check_env.py

Exits 0 if everything the bot needs is present, 1 otherwise. Reports the
status of every variable rather than stopping at the first problem, and
never prints a secret's value -- only whether it is set and its length.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# The revoked NewsAPI key from the audit (H-10). Refuse to start with it.
REVOKED_KEYS = {"2287da19b4ca4f6a9d2711431ca2278b"}

# (name, required, note)
VARS = [
    ("MT5_ACCOUNT", True, "broker account number"),
    ("MT5_PASSWORD", True, "broker password"),
    ("MT5_SERVER", True, "broker server name"),
    ("MT5_PATH", False, "path to terminal64.exe; config.py has a default"),
    ("NEWS_API_KEY", False, "news sentiment is disabled without it"),
    ("ALLOW_LIVE", False, "must be exactly 'true' to trade a non-demo account"),
]


def main():
    load_dotenv()
    problems = []

    print("Environment preflight\n" + "-" * 60)
    for name, required, note in VARS:
        raw = os.getenv(name)
        value = None if raw in (None, "", "None") else raw

        if value is None:
            state = "MISSING" if required else "unset"
            if required:
                problems.append("%s is required (%s)" % (name, note))
            print("  %-16s %-9s  %s" % (name, state, note))
            continue

        if value in REVOKED_KEYS:
            problems.append(
                "%s is the REVOKED key from the audit -- replace it with the "
                "reissued one (see docs/SECURITY-DECISIONS.md)" % name
            )
            print("  %-16s %-9s  <-- revoked, must be replaced" % (name, "REVOKED"))
            continue

        print("  %-16s %-9s  (%d chars)" % (name, "set", len(value)))

    # ALLOW_LIVE is a safety interlock: anything but the exact string is "no".
    allow_live = os.getenv("ALLOW_LIVE")
    if allow_live not in (None, "", "false", "true"):
        problems.append(
            "ALLOW_LIVE=%r is neither 'true' nor 'false'; it will be read as "
            "false, which may not be what you meant" % allow_live
        )

    print("-" * 60)
    if problems:
        print("\nFAILED:")
        for p in problems:
            print("  - %s" % p)
        print("\nFill these in .env (copy .env.example if you have not).")
        return 1

    print("\nOK -- all required variables present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
