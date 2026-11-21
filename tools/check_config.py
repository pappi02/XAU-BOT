"""Static guard against silent redefinition (Phase 1.7).

Fails CI on:
  1. Any top-level name assigned more than once in config.py -- Python keeps
     the last one silently, which is how CONTRACT_SIZE, TRAIL_START_PRICE and
     TP_RISK_REWARD each ended up with two values (audit M-08).
  2. Any duplicate method name within a class, or duplicate top-level function,
     in any project module -- same failure mode, e.g. TradeExecutor's two
     _check_trailing_stop implementations.
  3. Any config.py key referenced nowhere else in the codebase (audit found 14).

Run:  python tools/check_config.py
Exit: 0 clean, 1 on any failure.
"""

import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.py")

# `tests` is excluded deliberately (Phase 12.4): a key referenced only by tests
# does nothing to the running bot. Counting test files as usage is how
# MIN_LOT_SIZE survived as dead configuration.
SKIP_DIRS = {"env", "venv", ".venv", "__pycache__", ".git", "tools", "docs",
             "scripts", ".githooks", "tests"}

# Keys that are legitimately unreferenced: consumed via os.getenv elsewhere,
# reserved for a documented upcoming phase, or read dynamically.
ALLOWED_UNREFERENCED = set()


def project_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def read(path):
    return io.open(path, encoding="utf-8", errors="surrogateescape").read()


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def duplicate_config_assignments():
    """Top-level names assigned more than once in config.py."""
    tree = ast.parse(read(CONFIG), filename=CONFIG)
    seen = {}
    dupes = []
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        for t in targets:
            if t.id in seen:
                dupes.append((t.id, seen[t.id], node.lineno))
            seen[t.id] = node.lineno
    return sorted(set(seen)), dupes


def duplicate_defs(path):
    """(qualified_name, first_line, second_line) for redefined defs."""
    try:
        tree = ast.parse(read(path), filename=path)
    except SyntaxError as exc:
        return [("<unparseable: %s>" % exc.msg, exc.lineno or 0, 0)]

    found = []

    def scan(body, prefix):
        seen = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                if node.name in seen:
                    found.append((name, seen[node.name], node.lineno))
                seen[node.name] = node.lineno
            elif isinstance(node, ast.ClassDef):
                scan(node.body, prefix + node.name + ".")

    scan(tree.body, "")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            pass  # already covered by scan's recursion from module level
    return found


def config_internal_uses():
    """Names read (not assigned) inside config.py itself.

    A key consumed only by another config expression -- e.g. SYMBOL_PHASE5
    branching on TRADE_ACCOUNT_MODE -- is genuinely used, so it must not be
    reported as dead.
    """
    tree = ast.parse(read(CONFIG), filename=CONFIG)
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def code_references(path):
    """Names a module genuinely uses in CODE.

    Phase 12.4: this used to be a regex over the raw source, so a key named in
    a comment or docstring counted as "used" -- which is how MIN_LOT_SIZE,
    mentioned only in a docstring explaining its own removal, survived. Now
    counts attribute accesses (config.X), bare names, and string literals
    passed to getattr/hasattr/setattr.
    """
    try:
        tree = ast.parse(read(path), filename=path)
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in ("getattr", "hasattr", "setattr")
              and len(node.args) >= 2
              and isinstance(node.args[1], ast.Constant)
              and isinstance(node.args[1].value, str)):
            found.add(node.args[1].value)
    return found


def unreferenced_config_keys(keys):
    """Config keys referenced nowhere in production code."""
    used = set()
    for path in project_files():
        if os.path.abspath(path) == CONFIG:
            continue
        used |= code_references(path)
    internal = config_internal_uses()

    unused = []
    for key in keys:
        if key.startswith("_") or key in ALLOWED_UNREFERENCED:
            continue
        if key in internal or key in used:
            continue
        unused.append(key)
    return unused


def main():
    failures = []

    keys, dupes = duplicate_config_assignments()
    print("config.py: %d top-level assignments" % len(keys))
    if dupes:
        failures.append("duplicate top-level assignments in config.py")
        for name, first, second in dupes:
            print("  DUPLICATE  %-32s lines %d and %d" % (name, first, second))

    dup_defs = []
    for path in sorted(project_files()):
        for name, first, second in duplicate_defs(path):
            dup_defs.append((rel(path), name, first, second))
    if dup_defs:
        failures.append("duplicate function/method definitions")
        for f, name, first, second in dup_defs:
            print("  DUPLICATE  %s: %s lines %d and %d" % (f, name, first, second))

    unused = unreferenced_config_keys(keys)
    if unused:
        failures.append("%d unreferenced config key(s)" % len(unused))
        print("  UNREFERENCED config keys (%d):" % len(unused))
        for key in unused:
            print("    %s" % key)

    print("-" * 60)
    if failures:
        print("FAILED: " + "; ".join(failures))
        return 1
    print("OK -- no duplicates, no unreferenced config keys.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
