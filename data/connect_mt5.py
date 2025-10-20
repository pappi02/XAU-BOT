import MetaTrader5 as mt5
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"  # ✅ Update this path if needed

def connect_mt5(account=None, password=None, server=None, timeout=60000):
    """Initialize and connect to MetaTrader 5 terminal."""
    if not mt5.initialize(path=MT5_PATH):
        logger.error(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False

    logger.info("✅ MT5 initialized successfully")

    # If credentials are provided, login
    if account and password and server:
        authorized = mt5.login(account, password, server)
        if authorized:
            logger.info(f"Connected to MT5 account {account} on {server}")
        else:
            logger.error(f"Failed to login: {mt5.last_error()}")
            mt5.shutdown()
            return False
    return True


def disconnect_mt5():
    """Disconnect from MetaTrader 5 terminal."""
    mt5.shutdown()
    logger.info("🔌 Disconnected from MT5")


def get_mt5_info():
    """Fetch terminal and account information."""
    if not mt5.terminal_info():
        logger.warning("⚠️ MT5 terminal not connected.")
        return None

    terminal_info = mt5.terminal_info()._asdict()
    account_info = mt5.account_info()._asdict() if mt5.account_info() else None

    return {
        "terminal": terminal_info,
        "account": account_info
    }


# Test connection
if __name__ == "__main__":
    if connect_mt5():
        info = get_mt5_info()
        if info:
            print("MT5 Info Retrieved ✅")
            print(info)
        disconnect_mt5()
