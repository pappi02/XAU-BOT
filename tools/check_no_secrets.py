"""Fail if the revoked NewsAPI key reappears anywhere it could be used.

Phase 0.2 (H-10). A handful of files legitimately name the key because their
job is to detect it -- those are allowlisted explicitly rather than by a broad
pattern, so a new file mentioning the key still fails.

Run:  python tools/check_no_secrets.py
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REVOKED = "2287da19b4ca" "4f6a9d2711431ca2278b"  # split so this file self-excludes

SKIP_DIRS = {".git", "env", "venv", ".venv", "__pycache__", "node_modules"}

# Files permitted to name the revoked key, and why.
ALLOWED = {
    ".githooks/pre-commit":            "the pre-commit secret scanner",
    "scripts/check_env.py":            "the .env preflight checker",
    "tools/check_no_secrets.py":       "this script",
    "tests/test_phase1_guarantees.py": "the regression test",
    ".github/workflows/ci.yml":        "the CI job that runs this script",
    "docs/SECURITY-DECISIONS.md":      "the written decision record",
    "fix.md":                          "the remediation plan",
    "XAU-BOT-AUDIT.html":              "the audit report",
    "XAU-BOT-AUDIT.doc":               "the audit report",
}

TEXT_EXT = {".py", ".md", ".yml", ".yaml", ".txt", ".json", ".cfg", ".ini",
            ".toml", ".html", ".doc", ".env", ".example", ""}


def main():
    offenders = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            if rel in ALLOWED:
                continue
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            try:
                text = io.open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if REVOKED in text:
                offenders.append(rel)

    if offenders:
        print("FAILED: revoked NewsAPI key present in:")
        for o in offenders:
            print("  %s" % o)
        print("\nThe key was public on GitHub and is revoked. Remove it and "
              "read the value from .env via os.getenv('NEWS_API_KEY').")
        return 1

    print("OK -- revoked key appears only in the %d files that exist to "
          "detect it." % len(ALLOWED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
