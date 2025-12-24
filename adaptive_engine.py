# adaptive_engine.py - Smart Adaptive Bot Engine

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)

class RiskMode(Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

@dataclass
class TradeState:
    ticket: int
    symbol: str
    direction: str  # 'buy' or 'sell'
    entry_price: float
    current_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    open_time: float
    profit_pips: float
    atr_value: float
    scale_count: int = 0
    trailing_active: bool = False
    breakeven_set: bool = False

@dataclass
class MarketData:
    atr: float
    trend_strength: float
    volatility: float
    news_impact: float
    symbol: str = ""
    timeframe: str = ""
    current_price: float = 0.0
    rsi: float = 50.0
    volume: float = 0.0
    signal: str = "HOLD"
    strength: float = 0.0
    news_sentiment: str = "neutral"
    regime: str = "unknown"

class DynamicRiskModeResolver:
    """Dynamically switches risk modes based on performance and market conditions"""

    def __init__(self, config):
        self.config = config
        self.win_streak = 0
        self.loss_streak = 0
        self.recent_trades = []  # List of (profit, timestamp)
        self.current_mode = RiskMode.AGGRESSIVE
        self.last_mode_change = time.time()

    def update_performance(self, profit: float):
        """Update win/loss streaks"""
        if profit > 0:
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.loss_streak += 1
            self.win_streak = 0

        self.recent_trades.append((profit, time.time()))
        # Keep only last 10 trades
        self.recent_trades = self.recent_trades[-10:]

    def resolve_risk_mode(self, market_data: MarketData, account_balance: float) -> RiskMode:
        """Determine optimal risk mode based on current conditions"""

        # Performance-based switching
        if self.win_streak >= self.config.WIN_STREAK_TO_UPSHIFT:
            return RiskMode.AGGRESSIVE
        elif self.loss_streak >= self.config.LOSS_STREAK_TO_DOWNSHIFT:
            return RiskMode.CONSERVATIVE

        # Market volatility adjustment
        if market_data.volatility > 0.8:  # High volatility
            return RiskMode.CONSERVATIVE
        elif market_data.volatility < 0.3:  # Low volatility
            return RiskMode.AGGRESSIVE

        # News impact
        if market_data.news_impact > 0.7:
            return RiskMode.CONSERVATIVE

        # Account balance scaling (smaller accounts more conservative)
        if account_balance < 50:
            return RiskMode.CONSERVATIVE
        elif account_balance > 100:
            return RiskMode.AGGRESSIVE

        return RiskMode.BALANCED

class SmartSLTPManager:
    """Calculates dynamic SL/TP using live ATR and market conditions"""

    def __init__(self, config):
        self.config = config

    def calculate_sl_tp(self, entry_price: float, direction: str, atr: float,
                       trend_strength: float) -> Tuple[float, float]:
        """Calculate stop loss and take profit prices"""

        # SL based on ATR
        sl_distance = atr * self.config.ATR_MULTIPLIER_SL

        if direction == 'buy':
            sl_price = entry_price - sl_distance
            # TP scales with trend strength
            tp_multiplier = self.config.TP_RR_MIN + (
                self.config.TP_RR_MAX - self.config.TP_RR_MIN
            ) * trend_strength
            tp_price = entry_price + (sl_distance * tp_multiplier)
        else:  # sell
            sl_price = entry_price + sl_distance
            tp_multiplier = self.config.TP_RR_MIN + (
                self.config.TP_RR_MAX - self.config.TP_RR_MIN
            ) * trend_strength
            tp_price = entry_price - (sl_distance * tp_multiplier)

        return sl_price, tp_price

class AdaptiveTrailingSystem:
    """Manages trailing stops based on profit and ATR"""

    def __init__(self, config):
        self.config = config

    def should_activate_trailing(self, trade: TradeState) -> bool:
        """Check if trailing should be activated"""
        rr_ratio = abs(trade.current_price - trade.entry_price) / abs(trade.sl_price - trade.entry_price)
        return rr_ratio >= 1.5 and not trade.trailing_active

    def calculate_trailing_stop(self, trade: TradeState) -> float:
        """Calculate new trailing stop price"""
        trailing_distance = trade.atr_value * 1.2

        if trade.direction == 'buy':
            new_sl = trade.current_price - trailing_distance
            # Don't move SL backwards
            return max(new_sl, trade.sl_price)
        else:
            new_sl = trade.current_price + trailing_distance
            return min(new_sl, trade.sl_price)

class ConfidenceWeightedVoting:
    """Combines multiple signals with confidence weights"""

    def __init__(self, config):
        self.config = config

    def calculate_signal_confidence(self, signals: Dict[str, float],
                                  market_data: MarketData) -> float:
        """Calculate overall signal confidence"""

        # Base signal strength - filter to numeric values only
        numeric_signals = [v for v in signals.values() if isinstance(v, (int, float))]
        if not numeric_signals:
            return 0.0
        signal_strength = np.mean(numeric_signals)

        # Apply market condition modifiers
        volatility_modifier = 1.0 - (market_data.volatility * 0.3)  # Reduce confidence in high vol
        trend_modifier = 0.8 + (market_data.trend_strength * 0.4)  # Increase in strong trends
        news_modifier = 1.0 - (market_data.news_impact * 0.5)  # Reduce during news

        confidence = signal_strength * volatility_modifier * trend_modifier * news_modifier

        return min(confidence, 100.0)  # Cap at 100

    def should_trade(self, signals: Dict[str, float], market_data: MarketData) -> bool:
        """Determine if conditions are met for trading"""

        # Filter to numeric values only
        numeric_signals = {k: v for k, v in signals.items() if isinstance(v, (int, float))}

        # Aggressive mode: Allow trading if any signal is strong (>=35) - very permissive
        strong_signals = sum(1 for strength in numeric_signals.values()
                           if strength >= self.config.SIGNAL_STRENGTH_INCREASE)
        if strong_signals >= 1:  # Allow trade if at least one signal is strong
            logger.info(f"Aggressive mode: Allowing trade with {strong_signals} strong signals")
            return True

        # Check overall confidence - lowered threshold for aggressive mode
        confidence = self.calculate_signal_confidence(numeric_signals, market_data)
        return confidence >= self.config.SIGNAL_STRENGTH_DECREASE  # Use lower threshold

class PerformanceBasedAggressiveness:
    """Adjusts aggressiveness based on recent performance"""

    def __init__(self, config):
        self.config = config
        self.last_loss_time = 0
        self.aggressiveness_multiplier = 1.0

    def update_after_trade(self, profit: float):
        """Update aggressiveness after each trade"""
        if profit < 0:
            self.last_loss_time = time.time()
            self.aggressiveness_multiplier = max(0.5, self.aggressiveness_multiplier * 0.8)
        else:
            # Gradually increase after wins
            self.aggressiveness_multiplier = min(2.0, self.aggressiveness_multiplier * 1.1)

    def is_in_cooldown(self) -> bool:
        """Check if bot is in cooldown period after loss"""
        if time.time() - self.last_loss_time < self.config.COOLDOWN_AFTER_LOSS_SEC:
            return True
        return False

    def get_lot_multiplier(self) -> float:
        """Get current lot size multiplier"""
        return self.aggressiveness_multiplier

class AccountScaledExposure:
    """Scales position sizes based on account balance"""

    def __init__(self, config):
        self.config = config

    def calculate_lot_size(self, account_balance: float, risk_mode: RiskMode,
                          base_risk_pct: float) -> float:
        """Calculate appropriate lot size"""

        # Base risk amount
        risk_amount = account_balance * base_risk_pct

        # Apply risk mode multiplier
        risk_multiplier = self.config.RISK_MODE[risk_mode.value]
        risk_amount *= risk_multiplier

        # Convert to lot size (assuming 1 lot = $1000 for XAUUSD)
        lot_size = risk_amount / 1000.0

        # Apply limits
        lot_size = max(self.config.MIN_LOT_SIZE, min(self.config.MAX_LOT_SIZE, lot_size))

        # Round to lot step
        lot_size = round(lot_size / self.config.LOT_STEP) * self.config.LOT_STEP

        return lot_size

class HybridExitStrategy:
    """Manages complex exit logic with scaling and trailing"""

    def __init__(self, config):
        self.config = config

    def should_scale_in(self, trade: TradeState, current_time: float) -> bool:
        """Determine if position should be scaled"""

        # Check profit threshold
        if trade.profit_pips < trade.atr_value * 0.5:
            return False

        # Check max positions
        if trade.scale_count >= self.config.MAX_ADDITIONAL_POSITIONS:
            return False

        # Check time between scales
        # This would need to track last scale time per trade
        return True

    def calculate_scaled_tp(self, trade: TradeState) -> float:
        """Calculate take profit for scaled position"""
        base_tp_rr = 2.0
        additional_rr = 0.5 * trade.scale_count
        return base_tp_rr + additional_rr

    def manage_breakeven(self, trade: TradeState) -> Optional[float]:
        """Manage breakeven adjustments"""
        if trade.scale_count >= 1 and not trade.breakeven_set:
            buffer = trade.atr_value * 0.3
            if trade.direction == 'buy':
                return trade.entry_price + buffer
            else:
                return trade.entry_price - buffer
        return None

class AdaptiveEngine:
    """Main adaptive engine coordinating all components"""

    def __init__(self, config):
        self.config = config
        self.risk_resolver = DynamicRiskModeResolver(config)
        self.sl_tp_manager = SmartSLTPManager(config)
        self.trailing_system = AdaptiveTrailingSystem(config)
        self.confidence_voting = ConfidenceWeightedVoting(config)
        self.performance_tracker = PerformanceBasedAggressiveness(config)
        self.exposure_scaler = AccountScaledExposure(config)
        self.exit_strategy = HybridExitStrategy(config)

        self.active_trades: Dict[int, TradeState] = {}
        self.market_data = None

    def update_market_data(self, market_data: MarketData):
        """Update current market conditions"""
        self.market_data = market_data

    def process_signals(self, signals: Dict[str, float]) -> bool:
        """Process signals and determine if trading is allowed.
        Signature: process_signals(signals_dict) - expects market_data already set via update_market_data()
        """
        if not self.market_data:
            return False

        return self.confidence_voting.should_trade(signals, self.market_data)

    def calculate_entry_parameters(self, direction: str, account_balance: float) -> Dict:
        """Calculate lot size and SL/TP for new position"""

        # Get current risk mode
        risk_mode = self.risk_resolver.resolve_risk_mode(self.market_data, account_balance)

        # Check cooldown
        if self.performance_tracker.is_in_cooldown():
            return None

        # Calculate lot size
        lot_multiplier = self.performance_tracker.get_lot_multiplier()
        base_lot = self.exposure_scaler.calculate_lot_size(
            account_balance, risk_mode, self.config.BASE_RISK_PCT
        )
        lot_size = base_lot * lot_multiplier

        # Calculate SL/TP
        sl_price, tp_price = self.sl_tp_manager.calculate_sl_tp(
            self.market_data.atr, direction, self.market_data.atr, self.market_data.trend_strength
        )

        return {
            'lot_size': lot_size,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'risk_mode': risk_mode.value
        }

    def update_trade(self, ticket: int, current_price: float, profit_pips: float):
        """Update trade state and apply adaptive logic"""
        if ticket not in self.active_trades:
            return

        trade = self.active_trades[ticket]
        trade.current_price = current_price
        trade.profit_pips = profit_pips

        # Check for trailing activation
        if self.trailing_system.should_activate_trailing(trade):
            trade.trailing_active = True

        # Update trailing stop if active
        if trade.trailing_active:
            new_sl = self.trailing_system.calculate_trailing_stop(trade)
            trade.sl_price = new_sl

        # Check breakeven adjustment
        new_be_sl = self.exit_strategy.manage_breakeven(trade)
        if new_be_sl:
            trade.sl_price = new_be_sl
            trade.breakeven_set = True

    def on_trade_close(self, ticket: int, profit: float):
        """Handle trade closure and update performance"""
        self.performance_tracker.update_after_trade(profit)
        self.risk_resolver.update_performance(profit)

        if ticket in self.active_trades:
            del self.active_trades[ticket]

    def should_scale_position(self, ticket: int, current_time: float) -> bool:
        """Check if position should be scaled"""
        if ticket not in self.active_trades:
            return False

        trade = self.active_trades[ticket]
        return self.exit_strategy.should_scale_in(trade, current_time)

    def analyze_and_adapt(self, market_data: MarketData) -> Dict:
        """Analyze market conditions and return adaptive adjustments"""
        adjustments = {
            'signal_override': None,
            'adjusted_strength': market_data.strength,
            'risk_multiplier': 1.0
        }

        # Example adaptive logic based on market conditions
        if market_data.volatility > 0.8:
            adjustments['risk_multiplier'] = 0.7  # Reduce risk in high volatility
        elif market_data.volatility < 0.3:
            adjustments['risk_multiplier'] = 1.2  # Increase risk in low volatility

        # Signal override based on regime
        if market_data.regime == 'bearish' and market_data.signal == 'BUY':
            adjustments['signal_override'] = 'HOLD'
        elif market_data.regime == 'bullish' and market_data.signal == 'SELL':
            adjustments['signal_override'] = 'HOLD'

        return adjustments
