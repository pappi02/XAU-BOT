# strategy_selector.py - Professional Scalping Strategy Selection and Switching Logic

import time
from datetime import datetime, timedelta
from strategies.regime_detector import RegimeDetector
from strategies.breakout_scalping import BreakoutScalping
from strategies.momentum_scalping import MomentumScalping
from strategies.ma_scalping import MovingAverageScalping
from strategies.dip_scalping import DipScalping
from strategies.range_scalping import RangeScalping

class StrategySelector:
    """
    Professional Scalping Strategy Selector
    
    Dynamically selects between 5 expert scalping strategies based on market conditions:
    - Breakout Scalping: High volatility breakouts with volume confirmation
    - Momentum Scalping: Strong directional moves with momentum indicators
    - Moving Average Scalping: MA bounces and crossovers in trends
    - Dip Scalping: Buying dips in uptrends, selling rallies in downtrends
    - Range Scalping: Oscillations between support/resistance in sideways markets
    """

    def __init__(self, cooldown_sec=180, min_confidence=0.6, config=None):
        """
        Initialize professional scalping strategy selector.

        Args:
            cooldown_sec (int): Minimum time between strategy switches (default 3 minutes)
            min_confidence (float): Minimum confidence for regime detection
            config (dict): Configuration parameters for strategies
        """
        self.cooldown_sec = cooldown_sec
        self.min_confidence = min_confidence
        self.config = config or {}

        # Initialize components
        self.regime_detector = RegimeDetector()
        self.last_switch_time = 0
        self.current_strategy_name = None
        self.current_strategy = None

        # Initialize all 5 professional scalping strategies
        self.strategies = {
            'breakout_scalping': BreakoutScalping(config=self.config.get('breakout_scalping', {})),
            'momentum_scalping': MomentumScalping(config=self.config.get('momentum_scalping', {})),
            'ma_scalping': MovingAverageScalping(config=self.config.get('ma_scalping', {})),
            'dip_scalping': DipScalping(config=self.config.get('dip_scalping', {})),
            'range_scalping': RangeScalping(config=self.config.get('range_scalping', {}))
        }

        # Performance tracking
        self.regime_history = []
        self.switch_history = []
        self.strategy_performance = {key: {'wins': 0, 'losses': 0, 'total_signals': 0} 
                                     for key in self.strategies.keys()}

    def select_strategy(self, data, kb_results=None, signal_info=None, news_data=None):
        """
        Select appropriate scalping strategy based on market conditions and regime.

        Strategy Selection Logic:
        - Breakout Scalping: High volatility + clear breakout levels
        - Momentum Scalping: Strong directional momentum + volume
        - MA Scalping: Trending markets with clear MA structure
        - Dip Scalping: Strong trends with healthy pullbacks
        - Range Scalping: Low volatility sideways markets

        Args:
            data (pd.DataFrame): OHLC data
            kb_results (list): Knowledge base query results
            signal_info (dict): Current signal information
            news_data (dict): News sentiment data

        Returns:
            dict: Selection information with strategy details
        """
        # Prepare data for regime detection
        prepared_data = self.regime_detector.prepare_data(data)

        # Detect regime
        regime_info = self.regime_detector.detect_regime(prepared_data)

        # Get intelligent strategy selection based on market conditions
        selection_result = self._intelligent_strategy_selection(
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
        Generate trading signal using currently selected scalping strategy.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            dict: Signal information with entry, SL, TP, and confluences
        """
        if self.current_strategy is None:
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'strategy': None,
                'reason': 'No strategy selected'
            }

        # Generate signal using current strategy's analyze() method
        signal_result = self.current_strategy.analyze(data)

        # Add strategy information
        signal_result['strategy_used'] = self.current_strategy_name
        signal_result['regime_adaptive'] = True

        # Track signal generation
        self.strategy_performance[self.current_strategy_name]['total_signals'] += 1

        return signal_result

    def get_strategy_performance(self):
        """
        Get performance statistics for all scalping strategies.

        Returns:
            dict: Performance metrics for each strategy
        """
        if not self.switch_history:
            return {
                'total_switches': 0,
                'regime_distribution': {},
                'strategy_stats': self.strategy_performance,
                'current_strategy': self.current_strategy_name
            }

        # Count regime occurrences
        regime_counts = {}
        for record in self.regime_history[-100:]:  # Last 100 records
            regime = record['regime']
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        # Calculate strategy usage distribution
        strategy_usage = {}
        for switch in self.switch_history:
            strategy = switch['to_strategy']
            strategy_usage[strategy] = strategy_usage.get(strategy, 0) + 1

        # Calculate switch frequency
        if len(self.switch_history) > 1:
            time_span = (self.switch_history[-1]['timestamp'] - 
                        self.switch_history[0]['timestamp']).total_seconds()
            switch_frequency = len(self.switch_history) / (time_span / 3600) if time_span > 0 else 0
        else:
            switch_frequency = 0

        return {
            'total_switches': len(self.switch_history),
            'switch_frequency_per_hour': round(switch_frequency, 2),
            'regime_distribution': regime_counts,
            'strategy_usage': strategy_usage,
            'strategy_stats': self.strategy_performance,
            'current_strategy': self.current_strategy_name,
            'last_switch_time': datetime.fromtimestamp(self.last_switch_time) if self.last_switch_time > 0 else None
        }
    
    def update_strategy_result(self, strategy_name, result):
        """
        Update performance tracking for a strategy based on trade result.
        
        Args:
            strategy_name (str): Name of the strategy
            result (str): 'win' or 'loss'
        """
        if strategy_name in self.strategy_performance:
            if result == 'win':
                self.strategy_performance[strategy_name]['wins'] += 1
            elif result == 'loss':
                self.strategy_performance[strategy_name]['losses'] += 1

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
        Get list of all available professional scalping strategies.

        Returns:
            dict: Strategy names with descriptions
        """
        return {
            'breakout_scalping': 'Captures rapid breakouts with volume confirmation',
            'momentum_scalping': 'Trades strong momentum moves with RSI/MACD',
            'ma_scalping': 'Bounces and crossovers on moving averages',
            'dip_scalping': 'Buys dips in uptrends, sells rallies in downtrends',
            'range_scalping': 'Oscillations between support/resistance'
        }

    def _intelligent_strategy_selection(self, prepared_data, regime_info, kb_results, signal_info, news_data):
        """
        Intelligent strategy selection based on market conditions.
        
        Strategy Selection Criteria:
        1. Breakout Scalping: High volatility + consolidation breakout
        2. Momentum Scalping: Strong trend + high momentum indicators
        3. MA Scalping: Clear trend + MA structure
        4. Dip Scalping: Strong trend with pullbacks
        5. Range Scalping: Low volatility + sideways action

        Args:
            prepared_data (pd.DataFrame): Data with regime indicators
            regime_info (dict): Regime detection results
            kb_results (list): Knowledge base query results
            signal_info (dict): Current signal information
            news_data (dict): News sentiment data

        Returns:
            dict: Selection result with strategy and confidence
        """
        if len(prepared_data) < 50:
            # Default to momentum scalping if insufficient data
            return {
                'selected_strategy': 'momentum_scalping',
                'confidence': 50.0,
                'votes': {'momentum_scalping': 1},
                'factors': {'insufficient_data': True},
                'total_votes': 1
            }

        latest = prepared_data.iloc[-1]
        recent_data = prepared_data.tail(20)
        
        # Extract market metrics
        atr_val = latest.get('ATR', 2.5)
        close_price = latest.get('close', 2000)
        atr_relative = atr_val / close_price
        
        rsi_val = latest.get('RSI_14', 50)
        bb_width = latest.get('BB_width', 0.02)
        adx_val = latest.get('ADX', 20)
        
        # Detect market conditions
        is_high_volatility = atr_relative > 0.004  # >0.4% ATR
        is_low_volatility = atr_relative < 0.0025  # <0.25% ATR
        is_trending = adx_val > 25
        is_ranging = adx_val < 20
        is_momentum = (rsi_val > 60 or rsi_val < 40) and adx_val > 20
        
        # Calculate price range oscillation (for range detection)
        recent_highs = recent_data['high']
        recent_lows = recent_data['low']
        price_range = (recent_highs.max() - recent_lows.min()) / close_price
        is_consolidating = price_range < 0.02  # <2% range
        
        # Voting system for strategy selection
        strategy_votes = {
            'breakout_scalping': 0,
            'momentum_scalping': 0,
            'ma_scalping': 0,
            'dip_scalping': 0,
            'range_scalping': 0
        }
        
        selection_factors = {}
        
        # BREAKOUT SCALPING votes
        if is_high_volatility and is_consolidating:
            strategy_votes['breakout_scalping'] += 3
            selection_factors['breakout_consolidation'] = True
        if regime_info['regime'] in ['volatile', 'breakout']:
            strategy_votes['breakout_scalping'] += 2
        
        # MOMENTUM SCALPING votes
        if is_momentum and is_high_volatility:
            strategy_votes['momentum_scalping'] += 3
            selection_factors['strong_momentum'] = True
        if rsi_val > 65 or rsi_val < 35:
            strategy_votes['momentum_scalping'] += 2
        if regime_info['regime'] == 'volatile':
            strategy_votes['momentum_scalping'] += 1
        
        # MA SCALPING votes
        if is_trending and not is_high_volatility:
            strategy_votes['ma_scalping'] += 3
            selection_factors['clear_trend'] = True
        if regime_info['regime'] == 'trending':
            strategy_votes['ma_scalping'] += 2
        if 40 <= rsi_val <= 60:  # Balanced RSI in trend
            strategy_votes['ma_scalping'] += 1
        
        # DIP SCALPING votes
        if is_trending and (rsi_val < 40 or rsi_val > 60):
            strategy_votes['dip_scalping'] += 3
            selection_factors['trend_with_dips'] = True
        if adx_val > 30:  # Very strong trend
            strategy_votes['dip_scalping'] += 2
        
        # RANGE SCALPING votes
        if is_ranging and is_low_volatility:
            strategy_votes['range_scalping'] += 3
            selection_factors['sideways_market'] = True
        if is_consolidating:
            strategy_votes['range_scalping'] += 2
        if bb_width < 0.015:  # Tight Bollinger Bands
            strategy_votes['range_scalping'] += 2
        if regime_info['regime'] == 'ranging':
            strategy_votes['range_scalping'] += 1
        
        # Add KB-based votes if available
        if kb_results:
            kb_votes = self._calculate_kb_votes_scalping(kb_results)
            for strategy, votes in kb_votes.items():
                strategy_votes[strategy] += votes
            selection_factors['kb_contribution'] = sum(kb_votes.values())
        
        # Select strategy with highest votes
        total_votes = sum(strategy_votes.values())
        
        if total_votes == 0:
            # No clear winner, default to momentum scalping (most versatile)
            selected_strategy = 'momentum_scalping'
            confidence = 50.0
        else:
            selected_strategy = max(strategy_votes, key=strategy_votes.get)
            confidence = min(100.0, (strategy_votes[selected_strategy] / total_votes) * 100)
        
        # Add market metrics to factors
        selection_factors.update({
            'regime': regime_info['regime'],
            'atr_relative': round(atr_relative * 100, 3),
            'rsi': round(rsi_val, 1),
            'adx': round(adx_val, 1),
            'bb_width': round(bb_width, 4),
            'volatility': 'high' if is_high_volatility else 'low' if is_low_volatility else 'medium',
            'trend_strength': 'strong' if is_trending else 'weak' if is_ranging else 'medium'
        })
        
        return {
            'selected_strategy': selected_strategy,
            'confidence': round(confidence, 1),
            'votes': strategy_votes,
            'factors': selection_factors,
            'total_votes': total_votes
        }
    
    def _calculate_kb_votes_scalping(self, kb_results):
        """
        Calculate strategy votes from knowledge base for scalping strategies.

        Args:
            kb_results (list): KB query results

        Returns:
            dict: Strategy votes from KB
        """
        votes = {
            'breakout_scalping': 0,
            'momentum_scalping': 0,
            'ma_scalping': 0,
            'dip_scalping': 0,
            'range_scalping': 0
        }

        if not kb_results:
            return votes

        for doc in kb_results:
            doc_text = doc.get('document', '').lower()

            # Strategy keywords mapping
            if any(kw in doc_text for kw in ['breakout', 'break', 'consolidation', 'squeeze']):
                votes['breakout_scalping'] += 1
            if any(kw in doc_text for kw in ['momentum', 'strong move', 'acceleration', 'impulse']):
                votes['momentum_scalping'] += 1
            if any(kw in doc_text for kw in ['moving average', 'ma', 'ema', 'crossover', 'bounce']):
                votes['ma_scalping'] += 1
            if any(kw in doc_text for kw in ['dip', 'pullback', 'retracement', 'correction']):
                votes['dip_scalping'] += 1
            if any(kw in doc_text for kw in ['range', 'sideways', 'consolidat', 'support', 'resistance']):
                votes['range_scalping'] += 1

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
    # Example usage and testing
    import pandas as pd
    import numpy as np

    print("=" * 80)
    print("PROFESSIONAL SCALPING STRATEGY SELECTOR TEST")
    print("=" * 80)

    # Create sample data (5-minute XAUUSD candles)
    dates = pd.date_range('2024-01-01', periods=200, freq='5min')
    base_price = 2050
    prices = base_price + np.cumsum(np.random.randn(200) * 2)

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 1,
        'high': prices + abs(np.random.randn(200) * 2),
        'low': prices - abs(np.random.randn(200) * 2),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 200)
    }, index=dates)

    # Create and test selector
    selector = StrategySelector(cooldown_sec=60)  # 1-minute cooldown for testing

    print("\n📊 AVAILABLE STRATEGIES:")
    for name, desc in selector.get_available_strategies().items():
        print(f"  - {name}: {desc}")

    # Select strategy
    print("\n🔍 SELECTING STRATEGY...")
    selection = selector.select_strategy(sample_data)
    
    print(f"\n✅ Selected Strategy: {selection['selected_strategy']}")
    print(f"   Regime: {selection['regime_info']['regime']} "
          f"(confidence: {selection['regime_info']['confidence']:.1f}%)")
    print(f"   Selection Confidence: {selection['selection_info']['confidence']:.1f}%")
    print(f"   Votes: {selection['selection_info']['votes']}")

    # Generate signal
    print("\n📈 GENERATING SIGNAL...")
    signal = selector.generate_signal(sample_data)
    
    print(f"\n   Signal: {'BUY' if signal['signal'] == 1 else 'SELL' if signal['signal'] == -1 else 'HOLD'}")
    print(f"   Confidence: {signal['confidence']:.1f}%")
    print(f"   Entry: {signal.get('entry')}")
    print(f"   SL: {signal.get('sl')}")
    print(f"   TP: {signal.get('tp')}")
    print(f"   Strategy Used: {signal.get('strategy_used')}")

    # Get performance
    print("\n📊 PERFORMANCE SUMMARY:")
    performance = selector.get_strategy_performance()
    print(f"   Total Switches: {performance['total_switches']}")
    print(f"   Current Strategy: {performance['current_strategy']}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
