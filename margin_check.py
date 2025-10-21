import MetaTrader5 as mt5
import logging

logger = logging.getLogger(__name__)

def safe_margin_check(symbol, lot):
    """Safely check margin requirements before trade execution."""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"⚠️ Unable to fetch symbol info for {symbol}")
        return False, None

    # Default contract size fallback (common for metals)
    contract_size = getattr(symbol_info, "trade_contract_size", None)
    if contract_size is None:
        contract_size = 100 if "XAU" in symbol else 1  # metals vs forex

    # Get price
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logger.error(f"⚠️ Unable to fetch tick data for {symbol}")
        return False, None

    price = tick.ask or tick.last or 0

    # Estimate margin
    try:
        margin_check = mt5.order_calc_margin(
            mt5.ORDER_TYPE_BUY, symbol, lot, price
        )
        if margin_check is None or margin_check < 0:
            logger.warning(f"⚠️ Margin check failed for {symbol}, lot {lot}")
            return False, None
        return True, margin_check

    except Exception as e:
        logger.error(f"⚠️ Error during margin check: {e}")
        return False, None


def get_safe_lot(symbol, requested_lot, min_lot=0.01, step=0.01):
    """Try progressively smaller lots until margin check passes."""
    lot = requested_lot
    while lot >= min_lot:
        ok, margin = safe_margin_check(symbol, lot)
        if ok:
            logger.info(f"✅ Margin OK for {lot} lots | Margin: {margin:.2f}")
            return lot
        logger.warning(f"⚠️ Insufficient margin for {lot:.2f}, reducing...")
        lot = round(lot - step, 2)
    logger.error("❌ Execution error: Insufficient margin even for minimum lot size.")
    return None
