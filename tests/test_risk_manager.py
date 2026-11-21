import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import tempfile

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
        self.mock_config.MAX_TOTAL_POSITIONS = 2
        self.mock_config.MAX_LOTS_PER_ORDER = 5.0

        # Mock MT5 module
        self.mock_mt5 = Mock()
        # Phase 2.1: contract size is now READ from the broker, not taken from
        # config.CONTRACT_SIZE (which was deleted). Supply a realistic spec.
        self.mock_mt5.symbol_info.return_value = Mock(
            digits=2, point=0.01, trade_contract_size=100.0,
            trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01,
            volume_step=0.01, volume_max=50.0, trade_stops_level=0,
            trade_freeze_level=0, filling_mode=2,
        )
        self.mock_mt5.symbol_select.return_value = True

        # Phase 3: RiskManager persists risk state. Point it at a throwaway
        # file so tests never read or write the repo's risk_state.json.
        self._state_dir = tempfile.mkdtemp()
        self.mock_config.RISK_STATE_PATH = os.path.join(
            self._state_dir, "risk_state.json")
        self.mock_config.MAX_DAILY_LOSS_FRACTION = 0.05
        self.mock_config.MAX_DRAWDOWN_FRACTION = 0.20
        self.mock_config.MAX_PORTFOLIO_RISK_FRACTION = 0.04
        self.mock_config.RISK_PER_TRADE_FRACTION = 0.01

        # Create RiskManager instance
        self.risk_manager = RiskManager(self.mock_mt5, self.mock_config)

    def tearDown(self):
        import shutil
        shutil.rmtree(getattr(self, "_state_dir", ""), ignore_errors=True)

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

    # NOTE (Phase 1.7): these two tests were written against a version of
    # check_daily_loss_limit that summed history_deals_get(). The current
    # implementation reads the account's FLOATING P&L (account.profit) instead,
    # and no longer sets self.daily_pnl. The fixtures below match what the code
    # actually does; the history_deals_get mock is left in place to show it is
    # deliberately unused.

    def test_check_daily_loss_limit_within_limit(self):
        """Floating loss inside the 5% limit is allowed."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        mock_account.profit = -300.0   # allowed loss is 5% of 10000 = 500
        self.mock_mt5.account_info.return_value = mock_account
        self.mock_mt5.history_deals_get.return_value = []

        self.assertTrue(self.risk_manager.check_daily_loss_limit())

    def test_check_daily_loss_limit_exceeded(self):
        """Floating loss beyond the 5% limit stops trading."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        mock_account.profit = -600.0   # exceeds the 500 allowance
        self.mock_mt5.account_info.return_value = mock_account
        self.mock_mt5.history_deals_get.return_value = []

        self.assertFalse(self.risk_manager.check_daily_loss_limit())

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

        # Mock symbol info -- must now carry the full contract spec, since
        # Phase 2.1 reads contract_size from it rather than from config.
        mock_symbol = Mock(
            digits=2, point=0.01, trade_contract_size=100.0,
            trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01,
            volume_step=0.01, volume_max=100.0, trade_stops_level=0,
            trade_freeze_level=0, filling_mode=2,
        )
        self.mock_mt5.symbol_info.return_value = mock_symbol

        entry_price = 2000.0
        stop_loss_price = 1980.0  # 20 point stop

        lot_size = self.risk_manager.compute_lot_size(stop_loss_price, entry_price)

        # Expected calculation, with contract_size READ from the broker (100 oz
        # per lot for gold, not the FX 100000 that audit C-04 found) and the
        # single Phase 3.1 risk parameter RISK_PER_TRADE_FRACTION = 0.01:
        #   risk_amount      = 10000 * 0.01 = 100
        #   price_distance   = 20
        #   usd_risk_per_lot = 100 * 20     = 2000
        #   lots             = 100 / 2000   = 0.05   (exactly 1% of equity)
        #
        # This assertion used to read 0.01, because the wrong contract size made
        # the computed size 0.0001 -- 1000x too small -- which was then clamped
        # up to the broker minimum. The bot was risking a floor-value position
        # on every trade regardless of what the risk settings said.
        self.assertEqual(lot_size, 0.05)

    def test_compute_lot_size_invalid_distance(self):
        """Test lot size computation with invalid price distance."""
        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        entry_price = 2000.0
        stop_loss_price = 2000.0  # Same price, invalid

        lot_size = self.risk_manager.compute_lot_size(stop_loss_price, entry_price)

        self.assertIsNone(lot_size)

    def test_compute_lot_size_refuses_when_symbol_info_unavailable(self):
        """Phase 2.1: refuse to size a trade we cannot read the contract for.

        Previously this returned a lot size anyway, computed from a configured
        CONTRACT_SIZE that was wrong by 1000x. If the broker will not tell us
        what a lot is, guessing is the one thing we must not do.
        """
        from execution.symbol_spec import SymbolSpecError

        mock_account = Mock()
        mock_account.balance = 10000.0
        self.mock_mt5.account_info.return_value = mock_account

        self.mock_mt5.symbol_info.return_value = None
        self.mock_mt5.symbol_select.return_value = False

        with self.assertRaises(SymbolSpecError):
            self.risk_manager.compute_lot_size(1980.0, 2000.0)

    # ---------------------------------------------------------------------
    # Phase 3.1 replaced the multiplier-based sizing entirely. The six tests
    # that lived here asserted the behaviour of SIGNAL_STRENGTH_*, ATR_*,
    # SESSION_*, CORRELATION_RISK_* and DYNAMIC_LOT_SIZING_ENABLED multipliers,
    # all of which were deleted -- they had no evidence behind them and the ATR
    # pair was provably inert (M-03). Keeping them would be asserting that the
    # bug is still present. The replacement coverage is the equity x stop
    # matrix in tests/test_risk_phase3.py.
    # ---------------------------------------------------------------------

    def test_sizing_no_longer_accepts_the_ignored_heuristic_arguments(self):
        """Phase 12.5: an argument silently ignored invites false belief.

        These seven were accepted and discarded from Phase 3.1 until 12.5.
        Passing one now fails loudly instead of doing nothing quietly.
        """
        self.mock_mt5.account_info.return_value = Mock(
            balance=10000.0, equity=10000.0, profit=0.0)
        with self.assertRaises(TypeError):
            self.risk_manager.calculate_dynamic_lot_size(
                10.0, signal_strength=95, recent_perf="winning")

    def test_sizing_is_the_documented_formula(self):
        self.mock_mt5.account_info.return_value = Mock(
            balance=10000.0, equity=10000.0, profit=0.0)
        # 10000 * 1% = 100 risk; 100 oz * 10 stop = 1000 per lot -> 0.10 lots
        self.assertAlmostEqual(
            self.risk_manager.calculate_dynamic_lot_size(10.0), 0.10)


    def test_get_current_market_session(self):
        """Sessions follow London and New York local time, including DST."""
        from datetime import datetime, timezone
        cases = [
            # January: London = UTC, New York = UTC-5.
            ((2026, 1, 15, 6, 0), "Asian"),
            ((2026, 1, 15, 12, 0), "London"),
            # 13:00-16:00 is the London/NY OVERLAP, not plain New York (M-06).
            ((2026, 1, 15, 15, 0), "London/NY overlap"),
            ((2026, 1, 15, 18, 0), "New York"),
            ((2026, 1, 15, 23, 0), "Other"),
            # July: London = UTC+1, New York = UTC-4 -- every edge an hour earlier.
            ((2026, 7, 15, 7, 30), "London"),
            ((2026, 7, 15, 12, 45), "London/NY overlap"),
            ((2026, 7, 15, 15, 30), "New York"),
            ((2026, 7, 15, 21, 30), "Other"),
        ]
        for parts, expected in cases:
            with patch('risk.risk_manager.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(*parts, tzinfo=timezone.utc)
                self.assertEqual(self.risk_manager.get_current_market_session(),
                                 expected, parts)

    def test_fake_performance_helpers_are_gone(self):
        """Phase 12.5 (audit M-07): get_recent_performance returned the literal
        "neutral"; get_news_impact_level fed an ignored argument. Real loss-
        streak protection lives in PositionStateStore.consecutive_losses()."""
        self.assertFalse(hasattr(self.risk_manager, "get_recent_performance"))
        self.assertFalse(hasattr(self.risk_manager, "get_news_impact_level"))

if __name__ == '__main__':
    unittest.main()
