import MetaTrader5 as mt5
import logging
import os

try:
    import config as _config
except Exception:  # config must never make this module unimportable
    _config = None

# Phase 1.7: no logging.basicConfig() here. This is an imported module, not an
# entry point -- configuring the root logger from it installed a second handler
# and every line was printed twice. Use the shared bot logger instead, so the
# account-identity warning below actually reaches the same stream as the rest.
from logger_config import setup_logger

logger = setup_logger()


class AccountIdentityError(RuntimeError):
    """Raised when the connected account is not the one we were told to trade."""


def assert_account_identity():
    """Refuse to trade a live account unless ALLOW_LIVE=true (Phase 1.6, H-06).

    Called after a successful login. Logs which account is actually being
    traded -- the audit's finding was that this was never stated anywhere.
    """
    acct = mt5.account_info()
    if acct is None:
        raise AccountIdentityError(
            "account_info() returned None after login -- cannot verify identity"
        )

    is_demo = acct.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    logger.warning(
        "Trading account %s (%s) on %s",
        acct.login, "DEMO" if is_demo else "LIVE", acct.server,
    )

    if not is_demo and os.getenv("ALLOW_LIVE") != "true":
        mt5.shutdown()
        raise AccountIdentityError(
            "Refusing to trade live account %s. Set ALLOW_LIVE=true in .env "
            "to override." % acct.login
        )
    if not is_demo:
        # Phase 13: ALLOW_LIVE is necessary, not sufficient. A live account
        # trades only inside the micro-rollout, after Gates C and D.
        from execution.rollout import live_rollout_problems
        problems = live_rollout_problems(_config) if _config is not None else [
            "config could not be imported"]
        if problems:
            mt5.shutdown()
            raise AccountIdentityError(
                "Refusing to trade live account %s -- the Phase 13 micro-rollout "
                "conditions are not met:\n  - %s"
                % (acct.login, "\n  - ".join(problems)))
    return acct


def connect_mt5(account=None, password=None, server=None, timeout=60000,
                path=None, verify_identity=True):
    """Initialize MT5 and log in.

    Phase 1.6 (H-06): all three credentials are REQUIRED. Previously a missing
    credential silently skipped the login and returned True, which meant the bot
    traded whatever account the terminal already had open.

    L-06: ``timeout`` is now actually passed through; it used to be accepted
    and discarded.
    """
    missing = [name for name, value in
               (("MT5_ACCOUNT", account), ("MT5_PASSWORD", password),
                ("MT5_SERVER", server))
               if value in (None, "", "None")]
    if missing:
        raise AccountIdentityError(
            "Missing required MT5 credential(s): %s. Set them in .env -- see "
            ".env.example. Refusing to trade whatever account the terminal "
            "happens to have open." % ", ".join(missing)
        )

    if path is None:
        path = getattr(_config, "MT5_PATH", None) if _config else None

    if not mt5.initialize(path=path, timeout=timeout):
        logger.error("MT5 initialization failed: %s", mt5.last_error())
        return False

    logger.info("MT5 initialized successfully")

    if not mt5.login(account, password, server, timeout=timeout):
        logger.error("Failed to login: %s", mt5.last_error())
        mt5.shutdown()
        return False

    logger.info("Connected to MT5 account %s on %s", account, server)

    if verify_identity:
        assert_account_identity()
    return True


def disconnect_mt5():
    """Disconnect from MetaTrader 5 terminal."""
    mt5.shutdown()
    logger.info("Disconnected from MT5")


def get_mt5_info():
    """Fetch terminal and account information."""
    if not mt5.terminal_info():
        logger.warning("MT5 terminal not connected.")
        return None

    terminal_info = mt5.terminal_info()._asdict()
    account_info = mt5.account_info()._asdict() if mt5.account_info() else None

    return {
        "terminal": terminal_info,
        "account": account_info
    }


def is_connected():
    """True when the terminal is reachable and reports a live connection."""
    try:
        info = mt5.terminal_info()
    except Exception:
        return False
    if info is None:
        return False
    return bool(getattr(info, "connected", True))


def reconnect_with_backoff(account=None, password=None, server=None,
                           timeout=60000, max_attempts=6, base_delay=2.0,
                           max_delay=60.0, sleep=None):
    """Re-establish the MT5 connection, backing off between attempts.

    Phase 6.4 (audit H-04). The audited bot had no reconnection logic at all:
    a dropped terminal simply made every query return None, which the rest of
    the code read as "nothing is open".

    Backoff matters because the common causes of a drop -- terminal restart,
    broker-side maintenance, a flaky link -- are not fixed by hammering. The
    delay doubles from ``base_delay`` up to ``max_delay``.

    Returns:
        True once connected, False if every attempt failed. The caller must
        treat False as "do not trade".
    """
    import time as _time
    sleep = sleep or _time.sleep

    for attempt in range(1, max_attempts + 1):
        if is_connected():
            logger.info("Terminal already connected.")
            return True

        logger.warning("Reconnect attempt %d/%d...", attempt, max_attempts)
        try:
            mt5.shutdown()
        except Exception:
            pass

        try:
            if connect_mt5(account, password, server, timeout):
                logger.info("Reconnected on attempt %d.", attempt)
                return True
        except AccountIdentityError:
            # A credential or live/demo problem will not fix itself by
            # retrying, and retrying it risks connecting to the wrong account.
            raise
        except Exception as exc:
            logger.error("Reconnect attempt %d failed: %s", attempt, exc)

        if attempt < max_attempts:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.info("Waiting %.1fs before the next attempt.", delay)
            sleep(delay)

    logger.error("Could not reconnect after %d attempts. NOT TRADING.",
                 max_attempts)
    return False


# Test connection
if __name__ == "__main__":
    if connect_mt5(getattr(_config, "MT5_ACCOUNT", None),
                   getattr(_config, "MT5_PASSWORD", None),
                   getattr(_config, "MT5_SERVER", None)):
        info = get_mt5_info()
        if info:
            print("MT5 Info Retrieved")
            print(info)
        disconnect_mt5()
