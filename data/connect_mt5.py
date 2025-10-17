import MetaTrader5 as mt5
import logging
import os
import time

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
        logger.info(f"Attempting to login to MT5 account {account} on {server}")
        # Convert account to int if it's a string
        try:
            account_int = int(account)
        except (ValueError, TypeError):
            logger.error(f"Invalid account number format: {account}")
            mt5.shutdown()
            return False

        authorized = mt5.login(login=account_int, server=server, password=password)
        if authorized:
            logger.info(f"Login command sent to MT5 account {account_int} on {server}")
            # Wait for login to complete - MT5 login is asynchronous
            max_wait = 10  # seconds
            for i in range(max_wait):
                time.sleep(1)
                account_info = mt5.account_info()
                if account_info is not None:
                    logger.info(f"Successfully logged in. Account info retrieved: Balance={account_info.balance}, Equity={account_info.equity}")
                    break
                if i == max_wait - 1:
                    logger.error(f"Login timeout - account info not available after {max_wait} seconds")
                    mt5.shutdown()
                    return False
        else:
            error = mt5.last_error()
            logger.error(f"Failed to send login command: {error}")
            mt5.shutdown()
            return False
    else:
        logger.warning("No credentials provided - MT5 initialized in demo mode")
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
