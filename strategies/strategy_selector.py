# strategy_selector.py - Strategy Selection and Switching Logic

import time
from datetime import datetime, timedelta
from strategies.regime_detector import RegimeDetector
from strategies.scalping import ScalpingStrategy

class StrategySelector:
    """
    Selects and switches between trading strategies based on market regime.
    """

    def __init__(self, cooldown_sec=300, min_confidence=0.6, config=None):
        """
        Initialize strategy selector.

        Args:
            cooldown_sec (int): Minimum time between strategy switches
            min_confidence (float): Minimum confidence for regime detection
            config (dict): Configuration parameters
        """
        self.cooldown_sec = cooldown_sec
        self.min_confidence = min_confidence
        self.config = config or {}

        # Initialize components
        self.regime_detector = RegimeDetector()
        self.last_switch_time = 0
        self.current_strategy_name = None
        self.current_strategy = None

        # Strategy instances - Only scalping for short-term focus
        self.strategies = {
            'scalping': ScalpingStrategy()
        }

        # Performance tracking
        self.regime_history = []
        self.switch_history = []

    def select_strategy(self, data, kb_results=None, signal_info=None, news_data=None):
        """
        Select appropriate strategy based on market regime and multiple factors.

        Args:
            data (pd.DataFrame): OHLC data
            kb_results (list): Knowledge base query results
            signal_info (dict): Current signal information
            news_data (dict): News sentiment data

        Returns:
            dict: Selection information with voting details
        """
        # Prepare data for regime detection
        prepared_data = self.regime_detector.prepare_data(data)

        # Detect regime
        regime_info = self.regime_detector.detect_regime(prepared_data)

        # Get enhanced strategy selection with multi-factor voting
        selection_result = self._enhanced_strategy_selection(
            prepared_data, regime_info, kb_results, signal_info, news_data
        )

        recommended_strategy = selection_result['selected_strategy']

        # Check if we should switch
        should_switch = self._should_switch_strategy(
            current_strategy=self.current_strategy_name,
            new_strategy=recommended_strategy,
            confidence=selection_result['confidence']
        )

        if should_switch:
            self._switch_strategy(recommended_strategy, regime_info)
        elif self.current_strategy is None:
            # Initialize with recommended strategy
            self._switch_strategy(recommended_strategy, regime_info)

        # Record regime and selection details
        self.regime_history.append({
            'timestamp': datetime.now(),
            'regime': regime_info['regime'],
            'confidence': regime_info['confidence'],
            'recommended_strategy': recommended_strategy,
            'active_strategy': self.current_strategy_name,
            'selection_factors': selection_result['factors'],
            'votes': selection_result['votes']
        })

        # Keep only recent history
        if len(self.regime_history) > 100:
            self.regime_history = self.regime_history[-100:]

        return {
            'selected_strategy': self.current_strategy_name,
            'regime_info': regime_info,
            'selection_info': selection_result,
            'switched': should_switch,
            'strategy_instance': self.current_strategy
        }

    def _should_switch_strategy(self, current_strategy, new_strategy, confidence):
        """
        Determine if strategy should be switched.

        Args:
            current_strategy (str): Current strategy name
            new_strategy (str): New strategy name
            confidence (float): Regime detection confidence

        Returns:
            bool: Whether to switch
        """
        # No current strategy = allow switch
        if current_strategy is None:
            return True

        # Different strategy requested
        if current_strategy != new_strategy:
            # Check cooldown
            time_since_switch = time.time() - self.last_switch_time
            if time_since_switch < self.cooldown_sec:
                return False

            # Check confidence
            if confidence < self.min_confidence:
                return False

            return True

        return False

    def _switch_strategy(self, new_strategy_name, regime_info):
        """
        Switch to new strategy.

        Args:
            new_strategy_name (str): Name of new strategy
            regime_info (dict): Regime detection information
        """
        old_strategy = self.current_strategy_name
        self.current_strategy_name = new_strategy_name
        self.current_strategy = self.strategies.get(new_strategy_name)
        self.last_switch_time = time.time()

        # Record switch
        self.switch_history.append({
            'timestamp': datetime.now(),
            'from_strategy': old_strategy,
            'to_strategy': new_strategy_name,
            'regime': regime_info['regime'],
            'confidence': regime_info['confidence'],
            'reason': 'regime_change'
        })

        # Keep only recent history
        if len(self.switch_history) > 50:
            self.switch_history = self.switch_history[-50:]

    def generate_signal(self, data):
        """
        Generate signal using currently selected strategy.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            dict: Signal information
        """
        if self.current_strategy is None:
            return {
                'signal': 'HOLD',
                'strength': 0,
                'strategy': None,
                'reasons': ['No strategy selected']
            }

        # Prepare data for current strategy
        prepared_data = self.current_strategy.prepare_data(data)

        # Generate signal
        signal = self.current_strategy.generate_signal(prepared_data)

        # Add strategy information
        signal['strategy_used'] = self.current_strategy_name
        signal['regime_adaptive'] = True

        return signal

    def get_strategy_performance(self):
        """
        Get performance statistics for strategy selection.

        Returns:
            dict: Performance metrics
        """
        if not self.switch_history:
            return {'total_switches': 0, 'regime_distribution': {}}

        # Count regime occurrences
        regime_counts = {}
        for record in self.regime_history[-100:]:  # Last 100 records
            regime = record['regime']
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        # Calculate switch frequency
        if len(self.switch_history) > 1:
            time_span = (self.switch_history[-1]['timestamp'] - self.switch_history[0]['timestamp']).total_seconds()
            switch_frequency = len(self.switch_history) / (time_span / 3600)  # Switches per hour
        else:
            switch_frequency = 0

        return {
            'total_switches': len(self.switch_history),
            'switch_frequency_per_hour': round(switch_frequency, 2),
            'regime_distribution': regime_counts,
            'current_strategy': self.current_strategy_name,
            'last_switch_time': datetime.fromtimestamp(self.last_switch_time) if self.last_switch_time > 0 else None
        }

    def force_strategy_switch(self, strategy_name, reason="manual_override"):
        """
        Force a strategy switch (for manual override).

        Args:
            strategy_name (str): Strategy to switch to
            reason (str): Reason for switch

        Returns:
            bool: Success
        """
        if strategy_name not in self.strategies:
            return False

        old_strategy = self.current_strategy_name
        self.current_strategy_name = strategy_name
        self.current_strategy = self.strategies[strategy_name]
        self.last_switch_time = time.time()

        # Record manual switch
        self.switch_history.append({
            'timestamp': datetime.now(),
            'from_strategy': old_strategy,
            'to_strategy': strategy_name,
            'regime': 'manual',
            'confidence': 100,
            'reason': reason
        })

        return True

    def get_available_strategies(self):
        """
        Get list of available strategies.

        Returns:
            list: Strategy names
        """
        return list(self.strategies.keys())

    def _enhanced_strategy_selection(self, prepared_data, regime_info, kb_results, signal_info, news_data):
        """
        FORCED M5 SCALPING: Always select 'scalping' strategy for aggressive M5-based trading.
        All voting logic bypassed to ensure pure scalping behavior.

        Args:
            prepared_data (pd.DataFrame): Data with regime indicators
            regime_info (dict): Regime detection results
            kb_results (list): Knowledge base query results
            signal_info (dict): Current signal information
            news_data (dict): News sentiment data

        Returns:
            dict: Selection result with forced scalping
        """
        # FORCE SCALPING STRATEGY - No voting, always scalping for M5 aggressive trading
        selected_strategy = 'scalping'
        confidence = 100.0  # Maximum confidence for forced selection

        # Keep some factors for logging/debugging purposes
        selection_factors = {
            'regime': f"{regime_info['regime']} ({regime_info['confidence']}%)",
            'kb_results': len(kb_results) if kb_results else 0,
            'forced_scalping': True,
            'reason': 'Aggressive M5 scalping mode'
        }

        if len(prepared_data) > 0:
            latest = prepared_data.iloc[-1]
            selection_factors['atr'] = round(latest.get('ATR', 0), 2)
            selection_factors['rsi'] = round(latest.get('RSI_14', 50), 2)

        if signal_info:
            selection_factors['signal_strength'] = signal_info.get('strength', 0)
            selection_factors['signal_type'] = signal_info.get('signal', 'HOLD')

        if news_data and news_data.get('available', False):
            selection_factors['news_sentiment'] = f"{news_data.get('sentiment', 'neutral')} ({news_data.get('avg_sentiment_score', 0):.2f})"

        # Mock votes for compatibility (only scalping available)
        strategy_votes = {
            'scalping': 100  # Maximum votes for scalping
        }

        return {
            'selected_strategy': selected_strategy,
            'confidence': confidence,
            'votes': strategy_votes,
            'factors': selection_factors,
            'total_votes': 100,
            'forced_mode': 'M5_scalping_aggressive'
        }

    def _calculate_kb_votes(self, kb_results):
        """
        Calculate strategy votes based on KB results.

        Args:
            kb_results (list): KB query results

        Returns:
            dict: Strategy votes from KB
        """
        votes = {'basic': 0, 'trend_trading': 0, 'breakout_retest': 0, 'swing_trading': 0, 'scalping': 0}

        if not kb_results:
            return votes

        for doc in kb_results:
            doc_text = doc.get('document', '').lower()

            # Strategy keywords mapping
            if any(keyword in doc_text for keyword in ['scalping', 'scalp', 'quick', 'fast']):
                votes['scalping'] += 1
            if any(keyword in doc_text for keyword in ['swing', 'range', 'consolidation']):
                votes['swing_trading'] += 1
            if any(keyword in doc_text for keyword in ['breakout', 'retest', 'break']):
                votes['breakout_retest'] += 1
            if any(keyword in doc_text for keyword in ['trend', 'ema', 'moving average', 'momentum']):
                votes['trend_trading'] += 1

        return votes

    def _calculate_market_condition_votes(self, latest_data, signal_info):
        """
        Calculate strategy votes based on market conditions.

        Args:
            latest_data (pd.Series): Latest market data
            signal_info (dict): Signal information

        Returns:
            dict: Strategy votes from market conditions
        """
        votes = {'basic': 0, 'trend_trading': 0, 'breakout_retest': 0, 'swing_trading': 0, 'scalping': 0}

        # ATR-based volatility voting
        atr_val = latest_data.get('ATR', 2.5)
        close_price = latest_data.get('close', 1800)
        atr_relative = atr_val / close_price

        if atr_relative > 0.005:  # High volatility
            votes['scalping'] += 1  # Scalping works well in volatile markets
        elif atr_relative < 0.002:  # Low volatility
            votes['swing_trading'] += 1  # Swing trading in calm markets

        # RSI-based momentum voting
        rsi_val = latest_data.get('RSI_14', 50)

        if rsi_val > 70 or rsi_val < 30:  # Extreme RSI
            votes['breakout_retest'] += 1  # Look for reversals
        elif 40 <= rsi_val <= 60:  # Neutral RSI
            votes['trend_trading'] += 1  # Trend following in balanced conditions

        # BB width for range detection
        bb_width = latest_data.get('BB_width', 0.02)

        if bb_width < 0.015:  # Tight bands (ranging market)
            votes['swing_trading'] += 1
        elif bb_width > 0.03:  # Wide bands (trending/volatile)
            votes['trend_trading'] += 1

        return votes

    def reset(self):
        """
        Reset selector state.
        """
        self.current_strategy_name = None
        self.current_strategy = None
        self.last_switch_time = 0
        self.regime_history = []
        self.switch_history = []


if __name__ == "__main__":
    # Example usage
    import pandas as pd
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='H')
    prices = 1800 + np.cumsum(np.random.randn(200) * 1)

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 1,
        'high': prices + abs(np.random.randn(200) * 2),
        'low': prices - abs(np.random.randn(200) * 2),
        'close': prices
    }, index=dates)

    # Create and test selector
    selector = StrategySelector(cooldown_sec=60)  # Short cooldown for testing

    # Select strategy
    selection = selector.select_strategy(sample_data)
    print(f"📊 Selected strategy: {selection['selected_strategy']}")
    print(f"Regime: {selection['regime_info']['regime']} (confidence: {selection['regime_info']['confidence']}%)")

    # Generate signal
    signal = selector.generate_signal(sample_data)
    print(f"\n📈 Signal: {signal['signal']} (strength: {signal['strength']}%)")
    print(f"Strategy used: {signal.get('strategy_used')}")

    # Get performance
    performance = selector.get_strategy_performance()
    print(f"\n📊 Performance: {performance}")
