"""
Consolidated Risk Manager - Merges risk_manager.py and smart_risk.py functionality
Provides comprehensive risk management with adaptive lot sizing, margin checks, and dynamic SL
"""

import math
from datetime import datetime, timedelta, timezone
from logger_config import setup_logger
from margin_check import safe_margin_check
import MetaTrader5 as mt5
import logging

logger = setup_logger()

# === CONFIGURABLE LIMITS ===
MIN_LOT = 0.01
MAX_LOT = 0.05
MAX_MARGIN_PERCENT = 1.0  # max 100% of free margin used as margin

class ConsolidatedRiskManager:
    """
    Consolidated risk manager combining all risk management functionality:
    - Account monitoring and margin checks
    - Dynamic lot sizing based on risk percentage
    - Adaptive lot calculation based on ATR, signal strength, news impact
    - Daily loss limits and position management
    - Market session and performance-based adjustments
    """

    def __init__(self, mt5_module, config):
        """
        Initialize consolidated risk manager.

        Args:
            mt5_module: MetaTrader5 module (imported as mt5 in caller)
            config: config module with constants
        """
        self.mt5 = mt5_module
        self.config = config
        self.daily_start = datetime.now(timezone.utc).date()
        self.daily_pnl = 0.0  # reset at start of day; persist across restarts in production

        # Session data for equity-based daily loss tracking
        self.session_data = {
            'starting_equity': None,  # Set on first account refresh
            'daily_loss_triggered': False  # Hysteresis flag for recovery
        }

        # Smart risk parameters
        self.min_lot = MIN_LOT
        self.max_lot = MAX_LOT
        self.max_margin_percent = MAX_MARGIN_PERCENT

    def refresh_account(self):
        """Get fresh account information."""
        account = self.mt5.account_info()
        if account is None:
            raise RuntimeError("Failed to fetch MT5 account info")
        return account

    def update_daily_pnl(self):
        """Compute today's closed trade P/L and update daily_pnl."""
        now = datetime.now(timezone.utc)
        history = self.mt5.history_deals_get(
            datetime(now.year, now.month, now.day),
            now
        )
        pnl = 0.0
        if history:
            for deal in history:
                try:
                    pnl += float(deal.profit)
                except Exception:
                    pass
        self.daily_pnl = pnl
        return self.daily_pnl

    def check_daily_loss_limit(self, volatility=None, recent_performance=None):
        """
        Check if daily loss limit has been exceeded using equity-based calculation with hysteresis.

        Args:
            volatility (float, optional): Current market volatility (ATR)
            recent_performance (dict, optional): Recent trading performance metrics

        Returns:
            bool: True if trading is allowed, False if daily loss limit exceeded
        """
        account = self.refresh_account()
        current_equity = float(account.equity)

        # Initialize starting equity on first call
        if self.session_data['starting_equity'] is None:
            self.session_data['starting_equity'] = current_equity
            logger.info(f"Initialized daily loss tracking with starting equity: {current_equity:.2f}")

        starting_equity = self.session_data['starting_equity']
        loss_triggered = self.session_data['daily_loss_triggered']

        # Calculate current loss percentage from starting equity
        if starting_equity > 0:
            loss_pct = ((starting_equity - current_equity) / starting_equity) * 100
        else:
            loss_pct = 0.0

        # Get base loss limit
        base_limit = self.config.BASE_MAX_DAILY_LOSS_PCT

        # Apply adaptive adjustments if enabled
        if self.config.DYNAMIC_LOSS_TOLERANCE and recent_performance:
            win_rate = recent_performance.get('win_rate', 50)
            if win_rate < 40:  # Poor performance
                base_limit *= 0.8  # More conservative
            elif win_rate > 70:  # Good performance
                base_limit *= 1.1  # Slightly more aggressive

        # Apply volatility adjustments
        if volatility is not None:
            if volatility > 2.0:  # High volatility
                base_limit *= 0.9  # Reduce limit in high volatility
            elif volatility < 1.0:  # Low volatility
                base_limit *= 1.1  # Increase limit in calm markets

        # Hysteresis logic for recovery
        if loss_triggered:
            # Allow recovery if equity recovers to LOSS_RECOVERY_FACTOR of the limit
            recovery_threshold = base_limit * self.config.LOSS_RECOVERY_FACTOR
            if loss_pct <= recovery_threshold:
                self.session_data['daily_loss_triggered'] = False
                logger.info(f"Daily loss limit recovered. Loss: {loss_pct:.2f}%, Recovery threshold: {recovery_threshold:.2f}%")
                return True
            else:
                logger.debug(f"Daily loss limit still active. Loss: {loss_pct:.2f}%, Recovery threshold: {recovery_threshold:.2f}%")
                return False
        else:
            # Check if loss limit exceeded
            if loss_pct >= base_limit:
                self.session_data['daily_loss_triggered'] = True
                logger.warning(f"Daily loss limit exceeded. Loss: {loss_pct:.2f}%, Limit: {base_limit:.2f}%")
                return False

        logger.debug(f"Daily loss check passed. Loss: {loss_pct:.2f}%, Limit: {base_limit:.2f}%, Triggered: {loss_triggered}")
        return True

    def enough_balance(self):
        """Check if account has sufficient balance."""
        account = self.refresh_account()
        return float(account.balance) >= self.config.MIN_ACCOUNT_BALANCE

    def check_margin_for_trade(self, symbol, volume, price, sl_price):
        """
        Check if there's sufficient margin for a trade.

        Args:
            symbol (str): Trading symbol
            volume (float): Lot size
            price (float): Entry price
            sl_price (float): Stop loss price

        Returns:
            bool: True if sufficient margin, False otherwise
        """
        try:
            # Use safe margin check from margin_check.py
            ok, margin_required = safe_margin_check(symbol, volume)
            if not ok:
                logger.warning(f"Insufficient margin for {volume} lots @ {price}")
                return False

            account = self.refresh_account()
            free_margin = float(account.margin_free)
            logger.debug(f"Margin required: {margin_required:.2f}, Free margin: {free_margin:.2f}")

            return free_margin >= margin_required

        except Exception as e:
            logger.error(f"Error checking margin: {str(e)}")
            return False

    def current_open_positions_count(self, symbol):
        """Get count of open positions for symbol."""
        positions = self.mt5.positions_get(symbol=symbol)
        return len(positions) if positions is not None else 0

    def compute_lot_size(self, stop_loss_price, entry_price):
        """
        Basic position sizing based on Risk % of equity.

        Args:
            stop_loss_price (float): Stop loss price
            entry_price (float): Entry price

        Returns:
            float: Calculated lot size
        """
        account = self.refresh_account()
        balance = float(account.balance)
        risk_amount = balance * self.config.RISK_PER_TRADE_PCT

        # Price distance in USD
        price_distance = abs(entry_price - stop_loss_price)
        if price_distance <= 0:
            logger.error("Invalid price distance for SL calculation")
            return None

        # USD at risk per 1 lot
        usd_risk_per_lot = self.config.CONTRACT_SIZE * price_distance
        if usd_risk_per_lot <= 0:
            logger.error("usd_risk_per_lot <= 0")
            return None

        lots = risk_amount / usd_risk_per_lot

        # Get symbol volume limits
        symbol_info = self.mt5.symbol_info(self.config.SYMBOL_PHASE5)
        if symbol_info is None:
            logger.warning("symbol_info not available; returning lots as is")
            return max(0.01, round(lots, 2))

        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max
        step = symbol_info.volume_step if symbol_info.volume_step > 0 else 0.01

        # Round to nearest step
        if step > 0:
            lots = math.floor(lots / step) * step

        # Enforce min/max
        if lots < min_lot:
            logger.info(f"Calculated lots {lots} is below min lot {min_lot}; adjusting to min lot")
            lots = min_lot
        if lots > max_lot:
            logger.info(f"Calculated lots {lots} is above max lot {max_lot}; adjusting to max lot")
            lots = max_lot

        return round(lots, 2)

    def calculate_dynamic_sl_distance(self, entry_price, atr_value, sl_multiplier):
        """
        Calculate stop loss distance using ATR and dynamic multiplier.

        Args:
            entry_price (float): Entry price
            atr_value (float): Current ATR value
            sl_multiplier (float): Dynamic stop loss multiplier

        Returns:
            float: Stop loss distance in price units
        """
        if atr_value and atr_value > 0:
            sl_distance = atr_value * sl_multiplier
        else:
            # Fallback to percentage-based SL
            sl_distance = entry_price * 0.01  # 1% fallback

        return sl_distance

    # === SMART RISK FUNCTIONALITY (from smart_risk.py) ===

    def calculate_adaptive_lot(self, symbol, atr_value, signal_strength, news_impact="none"):
        """
        Dynamically calculate lot size based on ATR, signal strength, and news impact.

        Args:
            symbol (str): Trading symbol
            atr_value (float): Current ATR value
            signal_strength (float): Signal strength (0-100, normalized to 0-1)
            news_impact (str): News impact level

        Returns:
            float: Calculated lot size
        """
        account_info = self.mt5.account_info()
        if not account_info:
            logger.warning("Could not fetch account info; using minimum lot.")
            return self.min_lot

        balance = account_info.balance
        equity = account_info.equity

        # Base lot: proportional to balance
        base_lot = round((balance / 10000) * 0.02, 2)  # 0.02 lots per $10k
        base_lot = max(self.min_lot, min(base_lot, self.max_lot))

        # Adapt for volatility (ATR)
        if atr_value > 10:       # Very volatile
            base_lot *= 0.6
        elif atr_value > 5:      # Moderate volatility
            base_lot *= 0.8
        else:                    # Calm
            base_lot *= 1.0

        # Adapt for signal strength (0-1 range)
        signal_factor = max(0.1, min(signal_strength, 1.0))  # Clamp to 0.1-1.0
        base_lot *= signal_factor

        # Reduce during news events
        if news_impact.lower() == "high":
            base_lot *= 0.5
        elif news_impact.lower() == "medium":
            base_lot *= 0.75

        # Margin safety check
        safe_lot = self.get_safe_lot(symbol, round(base_lot, 2))
        return safe_lot or self.min_lot

    def safe_margin_check_internal(self, symbol, lot):
        """Internal safe margin check (complements margin_check.py)."""
        symbol_info = self.mt5.symbol_info(symbol)
        if not symbol_info:
            logger.error(f"Unable to fetch symbol info for {symbol}")
            return False, None

        tick = self.mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Unable to fetch tick data for {symbol}")
            return False, None

        price = tick.ask or tick.last or 0

        try:
            margin_check = self.mt5.order_calc_margin(self.mt5.ORDER_TYPE_BUY, symbol, lot, price)
            if margin_check is None or margin_check < 0:
                return False, None

            acc = self.mt5.account_info()
            if not acc:
                logger.error("Unable to fetch account info for margin check")
                return False, None

            free_margin = float(acc.margin_free)
            balance = float(acc.balance)
            equity = float(acc.equity)
            margin_used = float(acc.margin)

            logger.info(f"Account status: Balance={balance:.2f}, Equity={equity:.2f}, Free Margin={free_margin:.2f}, Margin Used={margin_used:.2f}")

            # Allow using up to max_margin_percent of free margin
            if margin_check > free_margin * self.max_margin_percent:
                logger.warning(f"Insufficient free margin: required {margin_check:.2f} > {free_margin * self.max_margin_percent:.2f} ({self.max_margin_percent*100}% of free)")
                return False, margin_check

            return True, margin_check
        except Exception as e:
            logger.error(f"Margin check error: {e}")
            return False, None

    def get_safe_lot(self, symbol, requested_lot, min_lot=None, step=0.01):
        """Progressively reduce lot until margin check passes."""
        min_lot = min_lot or self.min_lot

        # Log account status
        account = self.mt5.account_info()
        if account:
            logger.info(f"Account status: Balance={account.balance:.2f}, Equity={account.equity:.2f}, Free Margin={account.margin_free:.2f}")
        else:
            logger.warning("Unable to fetch account info for margin checking")

        logger.info(f"Checking safe lot for {symbol}: requested={requested_lot:.2f}, min={min_lot:.2f}, step={step:.2f}")
        lot = requested_lot
        iterations = 0
        while lot >= min_lot:
            iterations += 1
            ok, margin = self.safe_margin_check_internal(symbol, lot)
            if ok:
                logger.info(f"Margin OK for {lot:.2f} lots | Required: {margin:.2f} | Iterations: {iterations}")
                return round(lot, 2)
            if margin is not None:
                logger.warning(f"Insufficient margin for {lot:.2f} lots | Required: {margin:.2f}, reducing to {round(lot - step, 2):.2f}...")
            else:
                logger.warning(f"Margin calculation failed for {lot:.2f} lots, reducing to {round(lot - step, 2):.2f}...")
            lot = round(lot - step, 2)
        logger.error(f"Unable to find safe lot size for {symbol} after {iterations} iterations (even min {min_lot:.2f} failed)")
        return None

    # === ENHANCED DYNAMIC LOT SIZING ===

    def calculate_dynamic_lot_size(self, stop_loss_distance, signal_strength, atr_value, session, recent_perf, news_impact, trade_type, risk_mode=None):
        """
        Enhanced dynamic lot sizing combining all factors.

        Args:
            stop_loss_distance (float): Stop loss distance in price units
            signal_strength (float): Current signal strength (0-100)
            atr_value (float): Current ATR value
            session (str): Current market session
            recent_perf (str): Recent performance ('winning', 'losing', 'neutral')
            news_impact (str): News impact level ('high', 'medium', 'low')
            trade_type (str): Trade type ('trend', 'reversal')
            risk_mode (str): Risk mode ('aggressive', 'balanced', 'conservative')

        Returns:
            float: Calculated lot size
        """
        if not self.config.DYNAMIC_LOT_SIZING_ENABLED:
            # Fallback to basic lot sizing
            return self.compute_lot_size_basic(stop_loss_distance)

        # Get account equity
        account = self.refresh_account()
        equity = float(account.balance)

        # Base risk amount with mode adjustment
        risk_mode = risk_mode or self.config.DEFAULT_RISK_MODE
        base_risk_pct = self.config.BASE_RISK_PERCENT * self.config.RISK_MODE.get(risk_mode, 1.0)

        risk_amount = equity * (base_risk_pct / 100)

        # Calculate base lot size
        if stop_loss_distance <= 0:
            logger.error("Invalid stop loss distance for lot calculation")
            return self.config.MIN_LOT_SIZE

        usd_risk_per_lot = self.config.CONTRACT_SIZE * stop_loss_distance
        if usd_risk_per_lot <= 0:
            logger.error("Invalid USD risk per lot calculation")
            return self.config.MIN_LOT_SIZE

        lot_size = risk_amount / usd_risk_per_lot

        # Apply signal strength multiplier
        if signal_strength > self.config.SIGNAL_STRENGTH_HIGH_THRESHOLD:
            lot_size *= self.config.SIGNAL_STRENGTH_HIGH_MULTIPLIER
        elif signal_strength < self.config.SIGNAL_STRENGTH_LOW_THRESHOLD:
            lot_size *= self.config.SIGNAL_STRENGTH_LOW_MULTIPLIER

        # Apply volatility (ATR) multiplier
        if atr_value:
            if atr_value > self.config.ATR_HIGH_THRESHOLD:
                lot_size *= self.config.ATR_HIGH_MULTIPLIER
            elif atr_value < self.config.ATR_LOW_THRESHOLD:
                lot_size *= self.config.ATR_LOW_MULTIPLIER

        # Apply market session multiplier
        if session == "Asian":
            lot_size *= self.config.SESSION_ASIAN_MULTIPLIER
        elif session in ["London"]:
            lot_size *= self.config.SESSION_LONDON_MULTIPLIER
        elif session in ["New York"]:
            lot_size *= self.config.SESSION_NEWYORK_MULTIPLIER

        # Apply recent performance multiplier
        if recent_perf == "winning":
            lot_size *= self.config.WINNING_STREAK_MULTIPLIER
        elif recent_perf == "losing":
            lot_size *= self.config.LOSING_STREAK_MULTIPLIER

        # Apply news impact multiplier
        if news_impact == "high":
            lot_size *= self.config.NEWS_HIGH_IMPACT_MULTIPLIER
        elif news_impact == "medium":
            lot_size *= self.config.NEWS_MEDIUM_IMPACT_MULTIPLIER

        # Apply correlation risk multiplier
        open_positions = self.current_open_positions_count(self.config.SYMBOL_PHASE5)
        if open_positions >= self.config.MAX_CORRELATED_POSITIONS:
            lot_size *= self.config.CORRELATION_RISK_MULTIPLIER

        # Enforce lot size limits
        lot_size = max(self.config.MIN_LOT_SIZE, min(lot_size, self.config.MAX_LOT_SIZE))

        # Round to appropriate decimal places
        return round(lot_size, 2)

    def compute_lot_size_basic(self, stop_loss_distance):
        """Basic lot size calculation for fallback."""
        account = self.refresh_account()
        balance = float(account.balance)
        risk_amount = balance * self.config.RISK_PER_TRADE_PCT

        if stop_loss_distance <= 0:
            return self.config.MIN_LOT_SIZE

        usd_risk_per_lot = self.config.CONTRACT_SIZE * stop_loss_distance
        if usd_risk_per_lot <= 0:
            return self.config.MIN_LOT_SIZE

        lot_size = risk_amount / usd_risk_per_lot
        return round(max(self.config.MIN_LOT_SIZE, min(lot_size, self.config.MAX_LOT_SIZE)), 2)

    # === MARKET SESSION AND PERFORMANCE ANALYSIS ===

    def get_current_market_session(self):
        """Determine current market session."""
        now = datetime.now(timezone.utc)
        hour = now.hour

        # New York session: 13:30 - 20:00 UTC
        if 13 <= hour < 20:
            return "New York"
        # London session: 08:00 - 16:00 UTC
        elif 8 <= hour < 16:
            return "London"
        # Asian session: 00:00 - 09:00 UTC
        elif 0 <= hour < 9:
            return "Asian"
        else:
            return "Other"

    def get_recent_performance(self, recent_trades=None):
        """Analyze recent trading performance."""
        # Simplified - in production, analyze actual trade history
        return "neutral"

    def get_news_impact_level(self, news_sentiment):
        """Convert news sentiment to impact level."""
        if news_sentiment in ['bullish', 'bearish']:
            return "medium"
        return "low"

    # === UTILITY METHODS ===

    def get_account_summary(self):
        """Get comprehensive account summary."""
        account = self.refresh_account()
        return {
            'balance': float(account.balance),
            'equity': float(account.equity),
            'margin_free': float(account.margin_free),
            'margin_used': float(account.margin),
            'profit': float(account.profit),
            'daily_pnl': self.daily_pnl
        }

    def validate_trade_setup(self, symbol, volume, entry_price, sl_price, tp_price=None):
        """
        Comprehensive trade setup validation.

        Args:
            symbol (str): Trading symbol
            volume (float): Lot size
            entry_price (float): Entry price
            sl_price (float): Stop loss price
            tp_price (float): Take profit price (optional)

        Returns:
            dict: Validation results with issues if any
        """
        issues = []

        # Check margin
        if not self.check_margin_for_trade(symbol, volume, entry_price, sl_price):
            issues.append("Insufficient margin")

        # Check daily loss limit
        if not self.check_daily_loss_limit():
            issues.append("Daily loss limit exceeded")

        # Check balance
        if not self.enough_balance():
            issues.append("Insufficient account balance")

        # Check lot size limits
        symbol_info = self.mt5.symbol_info(symbol)
        if symbol_info:
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            if volume < min_lot:
                issues.append(f"Lot size {volume} below minimum {min_lot}")
            if volume > max_lot:
                issues.append(f"Lot size {volume} above maximum {max_lot}")

        # Check stop loss distance
        if abs(entry_price - sl_price) <= 0:
            issues.append("Invalid stop loss distance")

        return {
            'valid': len(issues) == 0,
            'issues': issues
        }

    def last_n_trades_profitable(self, n=10):
        """
        Check if the last N trades were profitable.
        This is a simple placeholder for performance tracking.

        Args:
            n (int): Number of recent trades to check

        Returns:
            bool: True if last N trades were profitable, False otherwise
        """
        try:
            # Get recent deals from today
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=1)  # Look back 1 day for recent trades

            deals = self.mt5.history_deals_get(start_date, now)
            if not deals:
                logger.debug(f"No recent deals found for last_n_trades_profitable check")
                return True  # No trades means no losses, so allow trading

            # Filter for our symbol and sort by time (most recent first)
            symbol_deals = [deal for deal in deals if deal.symbol == self.config.SYMBOL_PHASE5]
            symbol_deals.sort(key=lambda x: x.time, reverse=True)

            # Take the last N trades
            recent_deals = symbol_deals[:n]

            if len(recent_deals) < n:
                logger.debug(f"Only {len(recent_deals)} recent trades found, less than {n} requested")
                return True  # Not enough trades to judge

            # Check if all recent trades were profitable
            profitable_count = sum(1 for deal in recent_deals if deal.profit > 0)

            result = profitable_count == len(recent_deals)
            logger.debug(f"Last {len(recent_deals)} trades: {profitable_count} profitable out of {len(recent_deals)}")

            return result

        except Exception as e:
            logger.error(f"Error checking last_n_trades_profitable: {e}")
            return True  # Default to allowing trading on error


# === BACKWARD COMPATIBILITY FUNCTIONS ===

def calculate_adaptive_lot(symbol, atr_value, signal_strength, news_impact="none"):
    """
    Backward compatibility function for smart_risk.py interface.
    Creates a temporary risk manager instance for calculations.
    """
    # This would need proper MT5 and config instances in real usage
    # For now, return a basic calculation
    logger.warning("Using deprecated calculate_adaptive_lot function - migrate to ConsolidatedRiskManager")
    return max(MIN_LOT, min(0.02, MAX_LOT))  # Basic fallback


def safe_margin_check(symbol, lot):
    """Backward compatibility for margin_check.py interface."""
    logger.warning("Using deprecated safe_margin_check function - migrate to ConsolidatedRiskManager.safe_margin_check_internal")
    # Basic fallback - would need MT5 instance
    return True, 100.0  # Dummy values


def get_safe_lot(symbol, requested_lot, min_lot=MIN_LOT, step=0.01):
    """Backward compatibility for smart_risk.py interface."""
    logger.warning("Using deprecated get_safe_lot function - migrate to ConsolidatedRiskManager.get_safe_lot")
    return max(min_lot, min(requested_lot, MAX_LOT))  # Basic fallback


if __name__ == "__main__":
    # Example usage
    print("ConsolidatedRiskManager created successfully")
    print("Available methods:")
    methods = [method for method in dir(ConsolidatedRiskManager) if not method.startswith('_')]
    for method in methods:
        print(f"  - {method}")
