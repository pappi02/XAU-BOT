import math
from datetime import datetime, timedelta, timezone
from logger_config import setup_logger
from margin_check import safe_margin_check
logger = setup_logger()

class RiskManager:
    def __init__(self, mt5_module, config):
        """
        mt5_module: MetaTrader5 module (imported as mt5 in caller)
        config: config module with constants
        """
        self.mt5 = mt5_module
        self.config = config
        self.daily_start = datetime.now(timezone.utc).date()
        self.daily_pnl = 0.0  # reset at start of day; you should persist across restarts in production

    def refresh_account(self):
        account = self.mt5.account_info()
        if account is None:
            raise RuntimeError("Failed to fetch MT5 account info")
        return account

    def update_daily_pnl(self):
        """Simple: compute today's closed trade P/L and update daily_pnl.
           For reliability persist trade events to a file/DB. Here we approximate by summing history for today."""
        now = datetime.now(timezone.utc)
        history = self.mt5.history_deals_get(
            datetime(now.year, now.month, now.day),
            now
        )
        pnl = 0.0
        if history:
            for deal in history:
                # deals have profit field
                try:
                    pnl += float(deal.profit)
                except Exception:
                    pass
        self.daily_pnl = pnl
        return self.daily_pnl

    def get_dynamic_daily_loss_limit(self, volatility=None, recent_performance=None):
        """
        Calculate dynamic daily loss limit based on market conditions and performance.

        Args:
            volatility (float, optional): Current market volatility (ATR)
            recent_performance (dict, optional): Recent trading performance metrics

        Returns:
            float: Dynamic daily loss percentage
        """
        if not self.config.DYNAMIC_DAILY_LOSS_ENABLED:
            return self.config.MAX_DAILY_LOSS_PCT

        base_limit = self.config.BASE_MAX_DAILY_LOSS_PCT

        # Adjust based on volatility
        if volatility is not None:
            if volatility > 2.0:  # High volatility
                base_limit *= 0.8  # Reduce limit in high volatility
            elif volatility < 1.0:  # Low volatility
                base_limit *= 1.2  # Increase limit in calm markets

        # Adjust based on recent performance
        if recent_performance:
            win_rate = recent_performance.get('win_rate', 50)
            if win_rate < 40:  # Poor performance
                base_limit *= 0.7  # More conservative
            elif win_rate > 70:  # Good performance
                base_limit *= 1.1  # Slightly more aggressive

        # Ensure reasonable bounds
        return max(1.0, min(base_limit, 5.0))  # Between 1% and 5%

    def check_daily_loss_limit(self, volatility=None, recent_performance=None):
        account = self.refresh_account()
        balance = float(account.balance)
        profit = float(account.profit)  # floating P&L
        dynamic_loss_pct = self.get_dynamic_daily_loss_limit(volatility, recent_performance)
        allowed_loss = balance * (dynamic_loss_pct / 100.0)
        logger.debug(f"Floating P&L: {profit:.2f}, allowed loss: {allowed_loss:.2f} (dynamic limit: {dynamic_loss_pct:.1f}%)")
        return profit > -allowed_loss

    def enough_balance(self):
        account = self.refresh_account()
        return float(account.balance) >= self.config.MIN_ACCOUNT_BALANCE

    def check_margin_for_trade(self, symbol, volume, price, sl_price):
        """
        Check if there's sufficient margin for a trade using safe margin check.

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
        positions = self.mt5.positions_get(symbol=symbol)
        return len(positions) if positions is not None else 0

    def compute_lot_size(self, stop_loss_price, entry_price):
        """
        Position sizing based on Risk % of equity:
          risk_amount = balance * RISK_PER_TRADE_PCT
          value_per_point = contract_size (USD per 1 lot per 1 unit price) => For XAU the conversion is price * contract_size
          lot = (risk_amount * leverage) / (contract_size * abs(entry - stop_loss))
        Note: contract_size must reflect broker's contract definition.
        """
        account = self.refresh_account()
        balance = float(account.balance)
        risk_amount = balance * self.config.RISK_PER_TRADE_PCT
        # price distance in USD
        price_distance = abs(entry_price - stop_loss_price)
        if price_distance <= 0:
            logger.error("Invalid price distance for SL calculation")
            return None

        # USD at risk per 1 lot = contract_size * price_distance
        usd_risk_per_lot = self.config.CONTRACT_SIZE * price_distance
        if usd_risk_per_lot <= 0:
            logger.error("usd_risk_per_lot <= 0")
            return None

        # leverage increases buying power; sizing uses leverage to compute nominal exposure allowed
        # but true risk measured is still usd_risk_per_lot per lot; we therefore ignore leverage for actual risk amount,
        # but ensure margin/volume limits separately via symbol_info
        lots = risk_amount / usd_risk_per_lot

        # Get symbol volume limits to round to allowed step
        symbol_info = self.mt5.symbol_info(self.config.SYMBOL_PHASE5)
        if symbol_info is None:
            logger.warning("symbol_info not available; returning lots as is")
            return max(0.01, round(lots, 2))

        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max
        step = symbol_info.volume_step if symbol_info.volume_step > 0 else 0.01

        # round down to nearest step
        if step > 0:
            lots = math.floor(lots / step) * step

        # enforce min,max
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
            # Fallback to percentage-based SL if ATR not available
            sl_distance = entry_price * 0.01  # 1% fallback

        return sl_distance

    def calculate_dynamic_lot_size(self, stop_loss_distance, signal_strength, atr_value, session, recent_perf, news_impact, trade_type, risk_mode=None):
        """
        Calculate dynamic lot size based on multiple market factors.

        Args:
            stop_loss_distance (float): Stop loss distance in price units
            signal_strength (float): Current signal strength (0-100)
            atr_value (float): Current ATR value
            session (str): Current market session ('Asian', 'London', 'New York')
            recent_perf (str): Recent performance ('winning', 'losing', 'neutral')
            news_impact (str): News impact level ('high', 'medium', 'low')
            trade_type (str): Trade type ('trend', 'reversal')
            risk_mode (str): Risk mode ('aggressive', 'balanced', 'conservative')

        Returns:
            float: Calculated lot size
        """
        if not self.config.DYNAMIC_LOT_SIZING_ENABLED:
            # Fallback to basic lot sizing
            return None

        # Get account equity
        account = self.refresh_account()
        equity = float(account.balance)

        # Base risk amount
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
        session_multipliers = self.config.SESSION_RISK_MULTIPLIERS
        session_key = session.lower().replace(" ", "")
        if session_key in session_multipliers:
            lot_size *= session_multipliers[session_key]

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

        # Apply trade type multiplier
        if trade_type == "reversal":
            lot_size *= self.config.TRADE_TYPE_REVERSAL_MULTIPLIER
        elif trade_type == "trend":
            lot_size *= self.config.TRADE_TYPE_TREND_MULTIPLIER

        # Apply correlation risk multiplier (simplified - check for multiple positions)
        open_positions = self.current_open_positions_count(self.config.SYMBOL_PHASE5)
        if open_positions >= self.config.MAX_CORRELATED_POSITIONS:
            lot_size *= self.config.CORRELATION_RISK_MULTIPLIER

        # Enforce lot size limits
        lot_size = max(self.config.MIN_LOT_SIZE, min(lot_size, self.config.MAX_LOT_SIZE))

        # Round to appropriate decimal places
        return round(lot_size, 2)

    def get_current_market_session(self):
        """
        Determine the current market session based on UTC time.

        Returns:
            str: Current session ('Asian', 'London', 'New York', 'Other')
        """
        now = datetime.now(timezone.utc)
        hour = now.hour

        # New York session: 13:30 - 20:00 UTC (check first due to overlap)
        if 13 <= hour < 20:
            return "New York"
        # London session: 08:00 - 16:00 UTC
        elif 8 <= hour < 16:
            return "London"
        # Asian session: 00:00 - 09:00 UTC (Tokyo/Sydney)
        elif 0 <= hour < 9:
            return "Asian"
        else:
            return "Other"

    def get_recent_performance(self, recent_trades=None):
        """
        Analyze recent trading performance.

        Args:
            recent_trades (list): List of recent trade results (optional)

        Returns:
            str: Performance status ('winning', 'losing', 'neutral')
        """
        # Simplified implementation - in production, analyze actual trade history
        # For now, return neutral as we don't have trade history tracking
        return "neutral"

    def get_news_impact_level(self, news_sentiment):
        """
        Convert news sentiment to impact level.

        Args:
            news_sentiment (str): News sentiment ('bullish', 'bearish', 'neutral')

        Returns:
            str: Impact level ('high', 'medium', 'low')
        """
        # Simplified - in production, check for upcoming high-impact events
        if news_sentiment in ['bullish', 'bearish']:
            return "medium"
        return "low"
