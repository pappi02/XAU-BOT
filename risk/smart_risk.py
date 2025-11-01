import MetaTrader5 as mt5
import logging

logger = logging.getLogger(__name__)

# === CONFIGURABLE LIMITS ===
MIN_LOT = 0.01
MAX_LOT = 0.05
MAX_MARGIN_PERCENT = 1.0  # max 100% of free margin used as margin

def calculate_adaptive_lot(symbol, atr_value, signal_strength, news_impact="none"):
    """
    Dynamically calculate lot size based on:
      - Account balance
      - ATR volatility
      - Signal confidence
      - News impact level
    """
    account_info = mt5.account_info()
    if not account_info:
        logger.warning("⚠️ Could not fetch account info; using minimum lot.")
        return MIN_LOT

    balance = account_info.balance
    equity = account_info.equity

    # --- BASE LOT: proportional to balance ---
    base_lot = round((balance / 10000) * 0.02, 2)  # 0.02 lots per $10k
    base_lot = max(MIN_LOT, min(base_lot, MAX_LOT))

    # --- ADAPT FOR VOLATILITY ---
    if atr_value > 10:       # very volatile
        base_lot *= 0.6
    elif atr_value > 5:      # moderate volatility
        base_lot *= 0.8
    else:
        base_lot *= 1.0      # calm

    # --- ADAPT FOR SIGNAL STRENGTH ---
    base_lot *= signal_strength  # range: 0.0–1.0

    # --- REDUCE DURING NEWS EVENTS ---
    if news_impact.lower() == "high":
        base_lot *= 0.5
    elif news_impact.lower() == "medium":
        base_lot *= 0.75

    # --- MARGIN SAFETY CHECK ---
    safe_lot = get_safe_lot(symbol, round(base_lot, 2))
    return safe_lot or MIN_LOT


def safe_margin_check(symbol, lot):
    """Safely test if margin is available for given lot."""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"⚠️ Unable to fetch symbol info for {symbol}")
        return False, None

    # contract size fallback
    contract_size = getattr(symbol_info, "trade_contract_size", None)
    if contract_size is None:
        contract_size = 100 if "XAU" in symbol else 1

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logger.error(f"⚠️ Unable to fetch tick data for {symbol}")
        return False, None

    price = tick.ask or tick.last or 0

    try:
        margin_check = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lot, price)
        if margin_check is None or margin_check < 0:
            return False, None

        acc = mt5.account_info()
        if not acc:
            logger.error("⚠️ Unable to fetch account info for margin check")
            return False, None

        free_margin = float(acc.margin_free)
        balance = float(acc.balance)
        equity = float(acc.equity)
        margin_used = float(acc.margin)

        logger.info(f"💰 Account status: Balance={balance:.2f}, Equity={equity:.2f}, Free Margin={free_margin:.2f}, Margin Used={margin_used:.2f}")

        # Allow using up to 100% of free margin
        if margin_check > free_margin:
            logger.warning(f"⚠️ Insufficient free margin: required {margin_check:.2f} > free {free_margin:.2f} (Balance: {balance:.2f}, Equity: {equity:.2f})")
            return False, margin_check

        return True, margin_check
    except Exception as e:
        logger.error(f"Margin check error: {e}")
        return False, None


def get_safe_lot(symbol, requested_lot, min_lot=MIN_LOT, step=0.01):
    """Progressively reduce lot until margin check passes."""
    # Log account status for context
    account = mt5.account_info()
    if account:
        logger.info(f"💰 Account status: Balance={account.balance:.2f}, Equity={account.equity:.2f}, Free Margin={account.margin_free:.2f}")
    else:
        logger.warning("⚠️ Unable to fetch account info for margin checking")

    logger.info(f"🔍 Checking safe lot for {symbol}: requested={requested_lot:.2f}, min={min_lot:.2f}, step={step:.2f}")
    lot = requested_lot
    iterations = 0
    while lot >= min_lot:
        iterations += 1
        ok, margin = safe_margin_check(symbol, lot)
        if ok:
            logger.info(f"✅ Margin OK for {lot:.2f} lots | Required: {margin:.2f} | Iterations: {iterations}")
            return round(lot, 2)
        if margin is not None:
            logger.warning(f"⚠️ Insufficient margin for {lot:.2f} lots | Required: {margin:.2f}, reducing to {round(lot - step, 2):.2f}...")
        else:
            logger.warning(f"⚠️ Margin calculation failed for {lot:.2f} lots, reducing to {round(lot - step, 2):.2f}...")
        lot = round(lot - step, 2)
    logger.error(f"❌ Unable to find safe lot size for {symbol} after {iterations} iterations (even min {min_lot:.2f} failed)")
    return None
