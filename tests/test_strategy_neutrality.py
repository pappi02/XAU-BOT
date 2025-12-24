#!/usr/bin/env python3
"""
Test script to verify strategy selection neutrality.
"""

from strategies.strategy_selector import StrategySelector
import pandas as pd
import numpy as np

def test_strategy_neutrality():
    """Test the updated strategy selection neutrality."""
    print('Testing updated strategy selection neutrality...')

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='H')
    prices = 1800 + np.cumsum(np.random.randn(200) * 1)

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 1,
        'high': prices + abs(np.random.randn(200) * 2),
        'low': prices - abs(np.random.randn(200) * 2),
        'close': prices
    }, index=dates)

    # Create selector
    selector = StrategySelector(cooldown_sec=60)

    # Test selection
    selection = selector.select_strategy(sample_data)
    print(f'Selected strategy: {selection["selected_strategy"]}')
    print(f'Regime: {selection["regime_info"]["regime"]} (confidence: {selection["regime_info"]["confidence"]})')
    print(f'Votes: {selection["selection_info"]["votes"]}')
    print(f'Confidence: {selection["selection_info"]["confidence"]}%')

    # Test signal generation
    signal = selector.generate_signal(sample_data)
    print(f'Signal: {signal["signal"]} (strength: {signal["strength"]})')
    print(f'Strategy used: {signal.get("strategy_used")}')

    print('Test completed successfully!')

if __name__ == "__main__":
    test_strategy_neutrality()
