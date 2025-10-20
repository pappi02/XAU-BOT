import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.risk_manager import RiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock config
        self.mock_config = Mock()
        self.mock_config.MAX_DAILY_LOSS_PCT = 0.05  # 5%
        self.mock_config.MIN_ACCOUNT_BALANCE = 1000.0
        self.mock_config.RISK_PER_TRADE_PCT = 0.02  # 2%
        self.mock_config.CONTRACT_SIZE = 100000  # Standard lot size
        self.mock_config.SYMBOL_PHASE5 = "XAUUSD"

        # Add dynamic lot sizing config attributes
        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.DEFAULT_RISK_MODE = "balanced"
        self.mock_config.RISK_MODE_AGGRESSIVE_MULTIPLIER = 2.0
        self.mock_config.RISK_MODE_CONSERVATIVE_MULTIPLIER = 0.5
        self.mock_config.SIGNAL_STRENGTH_HIGH_THRESHOLD = 80
        self.mock_config.SIGNAL_STRENGTH_LOW_THRESHOLD = 50
        self.mock_config.SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5
        self.mock_config.SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.ATR_HIGH_MULTIPLIER = 0.6
        self.mock_config.ATR_LOW_MULTIPLIER = 1.2
        self.mock_config.SESSION_ASIAN_MULTIPLIER = 0.8
        self.mock_config.SESSION_LONDON_MULTIPLIER = 1.2
        self.mock_config.SESSION_NEWYORK_MULTIPLIER = 1.2
        self.mock_config.WINNING_STREAK_MULTIPLIER = 1.2
        self.mock_config.LOSING_STREAK_MULTIPLIER = 0.7
        self.mock_config.NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
        self.mock_config.NEWS_MEDIUM_IMPACT_MULTIPLIER = 0.8
        self.mock_config.TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
        self.mock_config.TRADE_TYPE_TREND_MULTIPLIER = 1.2
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0

        # Mock MT5 module
        self.mock_mt5 = Mock()

        # Create RiskManager instance
        self.risk_manager = RiskManager(self.mock_mt5, self.mock_config)

    def test_refresh_account_success(self):
        """Test successful account refresh."""
        mock_account = Mock()
        mock_account.balance = 5000.0
        mock_account.equity = 4800.0
        self.mock_mt5.account_info.return_value = mock_account

        account = self.risk_manager.refresh_account()

        self.assertEqual(account.balance, 5000.0)
        self.assertEqual(account.equity, 4800.0)
        self.mock_mt5.account_info.assert_called_once()

    def test_refresh_account_failure(self):
        """Test account refresh failure."""
        self.mock_mt5.account_info.return_value = None

        with self.assertRaises(RuntimeError):
            self.risk_manager.refresh_account()

    def test_check_daily_loss_limit_within_limit(self):
        """Test daily loss limit check when within limit."""
        # Mock account
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Mock history deals (no losses)
        self.mock_mt5.history_deals_get.return_value = []

        result = self.risk_manager.check_daily_loss_limit()

        self.assertTrue(result)
        self.assertEqual(self.risk_manager.daily_pnl, 0.0)

    def test_check_daily_loss_limit_exceeded(self):
        """Test daily loss limit check when exceeded."""
        # Mock account
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Mock history deals with losses exceeding limit
        mock_deal = Mock()
        mock_deal.profit = -600.0  # Loss of $600, limit is 5% of 10000 = $500
        self.mock_mt5.history_deals_get.return_value = [mock_deal]

        result = self.risk_manager.check_daily_loss_limit()

        self.assertFalse(result)
        self.assertEqual(self.risk_manager.daily_pnl, -600.0)

    def test_enough_balance_sufficient(self):
        """Test balance check with sufficient funds."""
        mock_account = Mock()
        mock_account.balance = 1500.0
        self.mock_mt5.account_info.return_value = mock_account

        result = self.risk_manager.enough_balance()

        self.assertTrue(result)

    def test_enough_balance_insufficient(self):
        """Test balance check with insufficient funds."""
        mock_account = Mock()
        mock_account.balance = 500.0
        self.mock_mt5.account_info.return_value = mock_account

        result = self.risk_manager.enough_balance()

        self.assertFalse(result)

    def test_current_open_positions_count(self):
        """Test counting open positions."""
        mock_positions = [Mock(), Mock(), Mock()]  # 3 positions
        self.mock_mt5.positions_get.return_value = mock_positions

        count = self.risk_manager.current_open_positions_count("XAUUSD")

        self.assertEqual(count, 3)
        self.mock_mt5.positions_get.assert_called_once_with(symbol="XAUUSD")

    def test_current_open_positions_count_none(self):
        """Test counting open positions when none returned."""
        self.mock_mt5.positions_get.return_value = None

        count = self.risk_manager.current_open_positions_count("XAUUSD")

        self.assertEqual(count, 0)

    def test_compute_lot_size_normal(self):
        """Test normal lot size computation."""
        # Mock account
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Mock symbol info
        mock_symbol = Mock()
        mock_symbol.volume_min = 0.01
        mock_symbol.volume_max = 100.0
        mock_symbol.volume_step = 0.01
        self.mock_mt5.symbol_info.return_value = mock_symbol

        entry_price = 2000.0
        stop_loss_price = 1980.0  # 20 point stop

        lot_size = self.risk_manager.compute_lot_size(stop_loss_price, entry_price)

        # Expected calculation:
        # risk_amount = 10000 * 0.02 = 200
        # price_distance = 20
        # usd_risk_per_lot = 100000 * 20 = 2,000,000
        # lots = 200 / 2,000,000 = 0.0001
        # But this is very small, will be adjusted to min_lot = 0.01
        self.assertEqual(lot_size, 0.01)

    def test_compute_lot_size_invalid_distance(self):
        """Test lot size computation with invalid price distance."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        entry_price = 2000.0
        stop_loss_price = 2000.0  # Same price, invalid

        lot_size = self.risk_manager.compute_lot_size(stop_loss_price, entry_price)

        self.assertIsNone(lot_size)

    def test_compute_lot_size_symbol_info_unavailable(self):
        """Test lot size computation when symbol info is unavailable."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        self.mock_mt5.symbol_info.return_value = None

        entry_price = 2000.0
        stop_loss_price = 1980.0

        lot_size = self.risk_manager.compute_lot_size(stop_loss_price, entry_price)

        # Should return rounded lots without symbol constraints
        self.assertIsInstance(lot_size, float)

    def test_calculate_dynamic_lot_size_basic(self):
        """Test basic dynamic lot size calculation."""
        # Mock account
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Add dynamic lot sizing config attributes
        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.DEFAULT_RISK_MODE = "balanced"
        self.mock_config.SIGNAL_STRENGTH_HIGH_THRESHOLD = 80
        self.mock_config.SIGNAL_STRENGTH_LOW_THRESHOLD = 50
        self.mock_config.SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5
        self.mock_config.SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.ATR_HIGH_MULTIPLIER = 0.6
        self.mock_config.ATR_LOW_MULTIPLIER = 1.2
        self.mock_config.SESSION_ASIAN_MULTIPLIER = 0.8
        self.mock_config.SESSION_LONDON_MULTIPLIER = 1.2
        self.mock_config.SESSION_NEWYORK_MULTIPLIER = 1.2
        self.mock_config.WINNING_STREAK_MULTIPLIER = 1.2
        self.mock_config.LOSING_STREAK_MULTIPLIER = 0.7
        self.mock_config.NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
        self.mock_config.NEWS_MEDIUM_IMPACT_MULTIPLIER = 0.8
        self.mock_config.TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
        self.mock_config.TRADE_TYPE_TREND_MULTIPLIER = 1.2
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0
        self.mock_config.CONTRACT_SIZE = 100.0

        # Mock positions_get to return empty list (no correlated positions)
        self.mock_mt5.positions_get.return_value = []

        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=20.0,
            signal_strength=75.0,
            atr_value=15.0,
            session="London",
            recent_perf="neutral",
            news_impact="low",
            trade_type="trend"
        )

        # Expected calculation:
        # Base risk: 10000 * (1.0/100) = 100
        # USD risk per lot: 100 * 20 = 2000
        # Base lot: 100 / 2000 = 0.05
        # Signal strength (75 > 50, < 80): no multiplier (neutral)
        # ATR (15 > 10, < 30): no multiplier (neutral)
        # Session London: *1.2
        # Recent perf neutral: no multiplier
        # News low: no multiplier
        # Trade type trend: *1.2
        # No correlated positions: no multiplier
        # Final: 0.05 * 1.2 * 1.2 = 0.072
        # Rounded to 0.07
        self.assertAlmostEqual(lot_size, 0.07, places=2)

    def test_calculate_dynamic_lot_size_high_signal_strength(self):
        """Test dynamic lot size with high signal strength."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Setup config as above
        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.SIGNAL_STRENGTH_HIGH_THRESHOLD = 80
        self.mock_config.SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.SESSION_ASIAN_MULTIPLIER = 0.8
        self.mock_config.WINNING_STREAK_MULTIPLIER = 1.2
        self.mock_config.NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
        self.mock_config.TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0
        self.mock_config.CONTRACT_SIZE = 100.0

        self.mock_mt5.positions_get.return_value = []

        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=20.0,
            signal_strength=85.0,  # High signal strength
            atr_value=15.0,
            session="Asian",
            recent_perf="neutral",
            news_impact="low",
            trade_type="trend"
        )

        # Base lot: 0.05
        # High signal: *1.5
        # Asian session: *0.8
        # Trade type trend: *1.2
        # Final: 0.05 * 1.5 * 0.8 * 1.2 = 0.072 → 0.07
        self.assertAlmostEqual(lot_size, 0.07, places=2)

    def test_calculate_dynamic_lot_size_low_signal_strength(self):
        """Test dynamic lot size with low signal strength."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.SIGNAL_STRENGTH_LOW_THRESHOLD = 50
        self.mock_config.SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.SESSION_LONDON_MULTIPLIER = 1.2
        self.mock_config.WINNING_STREAK_MULTIPLIER = 1.2
        self.mock_config.NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
        self.mock_config.TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0
        self.mock_config.CONTRACT_SIZE = 100.0

        self.mock_mt5.positions_get.return_value = []

        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=20.0,
            signal_strength=40.0,  # Low signal strength
            atr_value=15.0,
            session="London",
            recent_perf="neutral",
            news_impact="low",
            trade_type="trend"
        )

        # Base lot: 0.05
        # Low signal: *0.7
        # London session: *1.2
        # Trade type trend: *1.2
        # Final: 0.05 * 0.7 * 1.2 * 1.2 = 0.0504 → 0.05
        self.assertAlmostEqual(lot_size, 0.05, places=2)

    def test_calculate_dynamic_lot_size_correlation_risk(self):
        """Test dynamic lot size with correlation risk."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.SIGNAL_STRENGTH_HIGH_THRESHOLD = 80
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.SESSION_LONDON_MULTIPLIER = 1.2
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0
        self.mock_config.CONTRACT_SIZE = 100.0

        # Mock 3 open positions (exceeds MAX_CORRELATED_POSITIONS)
        mock_positions = [Mock(), Mock(), Mock()]
        self.mock_mt5.positions_get.return_value = mock_positions

        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=20.0,
            signal_strength=75.0,
            atr_value=15.0,
            session="London",
            recent_perf="neutral",
            news_impact="low",
            trade_type="trend"
        )

        # Base lot: 0.05
        # London session: *1.2
        # Trade type trend: *1.2
        # Correlation risk (3 > 2 positions): *0.7
        # Final: 0.05 * 1.2 * 1.2 * 0.7 = 0.0504 → 0.05
        self.assertAlmostEqual(lot_size, 0.05, places=2)

    def test_calculate_dynamic_lot_size_disabled(self):
        """Test dynamic lot size when disabled."""
        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = False

        # Mock account for fallback calculation
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        # Mock symbol info for fallback calculation
        mock_symbol = Mock()
        mock_symbol.volume_min = 0.01
        mock_symbol.volume_max = 100.0
        mock_symbol.volume_step = 0.01
        self.mock_mt5.symbol_info.return_value = mock_symbol

        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=20.0,
            signal_strength=75.0,
            atr_value=15.0,
            session="London",
            recent_perf="neutral",
            news_impact="low",
            trade_type="trend"
        )

        # Should return None (fallback to basic calculation)
        self.assertIsNone(lot_size)

    def test_calculate_dynamic_lot_size_limits(self):
        """Test dynamic lot size enforces min/max limits."""
        mock_account = Mock()
        mock_account.balance = 1000000.0  # Very large balance
        self.mock_mt5.account_info.return_value = mock_account

        self.mock_config.DYNAMIC_LOT_SIZING_ENABLED = True
        self.mock_config.BASE_RISK_PERCENT = 1.0
        self.mock_config.SIGNAL_STRENGTH_HIGH_THRESHOLD = 80
        self.mock_config.ATR_HIGH_THRESHOLD = 30
        self.mock_config.ATR_LOW_THRESHOLD = 10
        self.mock_config.SESSION_LONDON_MULTIPLIER = 1.2
        self.mock_config.WINNING_STREAK_MULTIPLIER = 1.2
        self.mock_config.NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
        self.mock_config.TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
        self.mock_config.CORRELATION_RISK_MULTIPLIER = 0.7
        self.mock_config.MAX_CORRELATED_POSITIONS = 2
        self.mock_config.MIN_LOT_SIZE = 0.01
        self.mock_config.MAX_LOT_SIZE = 5.0
        self.mock_config.CONTRACT_SIZE = 100.0

        self.mock_mt5.positions_get.return_value = []

        # Test max limit
        lot_size = self.risk_manager.calculate_dynamic_lot_size(
            stop_loss_distance=1.0,  # Very small SL for large lot
            signal_strength=90.0,
            atr_value=5.0,
            session="London",
            recent_perf="winning",
            news_impact="low",
            trade_type="trend"
        )

        # Should be capped at MAX_LOT_SIZE
        self.assertEqual(lot_size, 5.0)

    def test_get_current_market_session(self):
        """Test market session detection."""
        # Mock datetime.utcnow to return specific hours
        with patch('risk.risk_manager.datetime') as mock_datetime:
            # Asian session (00:00-09:00)
            mock_datetime.utcnow.return_value.hour = 6
            session = self.risk_manager.get_current_market_session()
            self.assertEqual(session, "Asian")

            # London session (08:00-16:00)
            mock_datetime.utcnow.return_value.hour = 12
            session = self.risk_manager.get_current_market_session()
            self.assertEqual(session, "London")

            # New York session (13:30-20:00)
            mock_datetime.utcnow.return_value.hour = 15
            session = self.risk_manager.get_current_market_session()
            self.assertEqual(session, "New York")

            # Other time
            mock_datetime.utcnow.return_value.hour = 22
            session = self.risk_manager.get_current_market_session()
            self.assertEqual(session, "Other")

    def test_get_recent_performance(self):
        """Test recent performance analysis."""
        # Currently returns "neutral" as placeholder
        perf = self.risk_manager.get_recent_performance()
        self.assertEqual(perf, "neutral")

    def test_get_news_impact_level(self):
        """Test news impact level conversion."""
        # Bullish/bearish -> medium
        impact = self.risk_manager.get_news_impact_level("bullish")
        self.assertEqual(impact, "medium")

        impact = self.risk_manager.get_news_impact_level("bearish")
        self.assertEqual(impact, "medium")

        # Neutral -> low
        impact = self.risk_manager.get_news_impact_level("neutral")
        self.assertEqual(impact, "low")

if __name__ == '__main__':
    unittest.main()
