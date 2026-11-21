"""Test-session safety net: the suite must never touch a broker.

It also pins the environment. `config.py` reads `.env`, so without this the
test suite's behaviour depends on whatever credentials the developer happens to
have configured locally -- and a malformed `.env` breaks every test with an
error that has nothing to do with the code under test. Setting these before
`config` is first imported makes the suite hermetic; `load_dotenv()` does not
override variables that are already set.


Every real MetaTrader5 entry point is replaced for the duration of the test
session with a function that fails loudly. Tests that need MT5 behaviour supply
their own `unittest.mock` doubles, which are unaffected by this.

This makes "no broker connections in tests" a property the suite enforces,
rather than a rule everyone has to remember.
"""

import os

import pytest

# Pin the environment BEFORE config.py is imported by anything.
os.environ.setdefault("MT5_ACCOUNT", "12345678")
os.environ.setdefault("MT5_PASSWORD", "test-password")
os.environ.setdefault("MT5_SERVER", "Test-Server")
os.environ.setdefault("NEWS_API_KEY", "")
os.environ["ALLOW_LIVE"] = "false"      # never inherit a live override

# A developer's real .env must not leak into the suite. If MT5_ACCOUNT is set
# but not numeric, config.py refuses to import -- correctly, but that failure
# belongs to the developer's machine, not to these tests.
if not os.environ["MT5_ACCOUNT"].strip().isdigit():
    os.environ["MT5_ACCOUNT"] = "12345678"

# Entry points that either open a connection or move money.
_FORBIDDEN = (
    "initialize",
    "login",
    "shutdown",
    "order_send",
    "order_check",
    "order_calc_margin",
    "positions_get",
    "account_info",
    "terminal_info",
    "symbol_info",
    "symbol_info_tick",
    "symbol_select",
    "copy_rates_from_pos",
    "history_deals_get",
)


def _forbid(name):
    def _fail(*args, **kwargs):
        raise AssertionError(
            "Test called the real MetaTrader5.%s(). Tests must use mocks -- "
            "no broker connections. See tests/conftest.py." % name
        )
    return _fail


@pytest.fixture(autouse=True, scope="session")
def no_broker_calls():
    try:
        import MetaTrader5 as mt5
    except ImportError:  # MT5 not installed (e.g. CI on a non-Windows runner)
        yield
        return

    saved = {}
    for name in _FORBIDDEN:
        if hasattr(mt5, name):
            saved[name] = getattr(mt5, name)
            setattr(mt5, name, _forbid(name))
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(mt5, name, original)
