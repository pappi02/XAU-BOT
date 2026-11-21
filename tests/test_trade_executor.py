import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.trade_executor import TradeExecutor

class TestTradeExecutor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock config
        self.mock_config = Mock()
        self.mock_config.ORDER_DEVIATION_POINTS = 10
        self.mock_config.ORDER_MAX_ATTEMPTS = 3
        self.mock_config.MAX_CONCURRENT_POSITIONS = 10
        self.mock_config.MAX_ENTRY_SPREAD_POINTS = 50  # Phase 2.4 spread gate

        # Mock MT5 module
        self.mock_mt5 = Mock()
        self.mock_mt5.ORDER_TYPE_BUY = 0
        self.mock_mt5.ORDER_TYPE_SELL = 1
        self.mock_mt5.TRADE_ACTION_DEAL = 1
        self.mock_mt5.ORDER_TIME_GTC = 0
        self.mock_mt5.ORDER_FILLING_IOC = 0
        self.mock_mt5.TRADE_RETCODE_DONE = 10009
        self.mock_mt5.POSITION_TYPE_BUY = 0
        # TradeExecutor.__init__ iterates open positions to seed scaling data.
        # Without this, positions_get() returns a bare Mock -- truthy but not
        # iterable -- and every test in this class dies in setUp (Phase 1.7).
        self.mock_mt5.positions_get.return_value = []

        # Phase 2: the executor now reads the contract specification from the
        # broker instead of trusting config.CONTRACT_SIZE, and validates every
        # order against it. Supply a realistic XAUUSD spec.
        self.mock_mt5.symbol_info.return_value = MagicMock(
            name="XAUUSD", digits=2, point=0.01, trade_contract_size=100.0,
            trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01,
            volume_step=0.01, volume_max=50.0, trade_stops_level=0,
            trade_freeze_level=0, filling_mode=2, bid=2000.40, ask=2000.50,
        )
        self.mock_mt5.symbol_select.return_value = True
        self.mock_mt5.SYMBOL_FILLING_FOK = 1
        self.mock_mt5.SYMBOL_FILLING_IOC = 2
        self.mock_mt5.ORDER_FILLING_FOK = 1
        self.mock_mt5.ORDER_FILLING_RETURN = 2
        self.mock_mt5.order_calc_margin.return_value = 10.0
        self.mock_mt5.account_info.return_value = MagicMock(margin_free=100000.0)

        # Mock risk manager
        self.mock_risk_manager = Mock()
        # Phase 3: enter_trade now consults drawdown and portfolio-risk gates,
        # and sizes the candidate's risk in money via contract_size().
        self.mock_risk_manager.check_drawdown.return_value = True
        self.mock_risk_manager.check_portfolio_risk.return_value = True
        self.mock_risk_manager.contract_size.return_value = 100.0

        # Create TradeExecutor instance
        self.executor = TradeExecutor(self.mock_mt5, self.mock_config, self.mock_risk_manager)

        # __init__ calls positions_get() once to seed scaling data. Reset so
        # each test's call-count assertions cover only its own calls.
        self.mock_mt5.reset_mock()

    def test_place_market_order_success_first_attempt(self):
        """Test successful market order placement on first attempt."""
        # Mock tick data
        mock_tick = Mock()
        mock_tick.ask = 2000.50
        mock_tick.bid = 2000.40
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        # Mock successful order result
        mock_result = Mock()
        mock_result.retcode = 10009  # TRADE_RETCODE_DONE
        self.mock_mt5.order_send.return_value = mock_result

        result = self.executor._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)

        self.assertEqual(result, mock_result)
        self.mock_mt5.order_send.assert_called_once()

    def test_place_market_order_success_after_retry(self):
        """Test successful market order placement after retries."""
        # Mock tick data
        mock_tick = Mock()
        mock_tick.ask = 2000.50
        mock_tick.bid = 2000.40
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        # Phase 6.1: only unambiguously non-executing retcodes are retried.
        # This test used 10006 (REJECT) -- a hard rejection that resending
        # cannot fix, and retrying it was part of audit H-02. 10004 is REQUOTE,
        # which genuinely means "did not execute, try again".
        mock_fail_result = Mock()
        mock_fail_result.retcode = 10004          # REQUOTE -- retryable
        mock_success_result = Mock()
        mock_success_result.retcode = 10009
        mock_success_result.volume = 0.05
        mock_success_result.price = 2000.40

        self.mock_mt5.order_send.side_effect = [mock_fail_result, mock_fail_result, mock_success_result]
        self.mock_mt5.positions_get.return_value = []     # nothing filled yet
        self.mock_mt5.history_orders_get.return_value = []

        result = self.executor._place_market_order("XAUUSD", False, 0.05, 2010.0, 1990.0)

        self.assertEqual(result, mock_success_result)
        self.assertEqual(self.mock_mt5.order_send.call_count, 3)

    def test_place_market_order_failure_all_retries(self):
        """Test market order placement failure after all retries."""
        # Mock tick data
        mock_tick = Mock()
        mock_tick.ask = 2000.50
        mock_tick.bid = 2000.40
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        mock_result = Mock()
        mock_result.retcode = 10004               # REQUOTE -- retryable
        self.mock_mt5.order_send.return_value = mock_result
        self.mock_mt5.positions_get.return_value = []
        self.mock_mt5.history_orders_get.return_value = []

        with self.assertRaises(RuntimeError):
            self.executor._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)

        self.assertEqual(self.mock_mt5.order_send.call_count, 3)

    def test_place_market_order_no_tick_data(self):
        """Test market order placement when tick data is unavailable."""
        self.mock_mt5.symbol_info_tick.return_value = None

        with self.assertRaises(RuntimeError):
            self.executor._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)

    def test_enter_trade_buy_signal(self):
        """Test entering a BUY trade."""
        # Setup mocks
        self.mock_risk_manager.compute_lot_size.return_value = 0.1
        self.mock_risk_manager.enough_balance.return_value = True
        self.mock_risk_manager.check_daily_loss_limit.return_value = True
        self.mock_risk_manager.current_open_positions_count.return_value = 2

        # Mock tick and order success
        mock_tick = Mock()
        mock_tick.ask = 2000.50
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        mock_result = Mock()
        mock_result.retcode = 10009
        self.mock_mt5.order_send.return_value = mock_result

        result = self.executor.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0, 2020.0)

        self.assertEqual(result, mock_result)
        self.mock_risk_manager.compute_lot_size.assert_called_once_with(1990.0, 2000.0)

    def test_enter_trade_sell_signal(self):
        """Test entering a SELL trade."""
        # Setup mocks
        self.mock_risk_manager.compute_lot_size.return_value = 0.05
        self.mock_risk_manager.enough_balance.return_value = True
        self.mock_risk_manager.check_daily_loss_limit.return_value = True
        self.mock_risk_manager.current_open_positions_count.return_value = 1

        # Mock tick and order success
        mock_tick = Mock()
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        mock_result = Mock()
        mock_result.retcode = 10009
        self.mock_mt5.order_send.return_value = mock_result

        result = self.executor.enter_trade("XAUUSD", "SELL", 2000.0, 2010.0, 1980.0)

        self.assertEqual(result, mock_result)
        self.mock_risk_manager.compute_lot_size.assert_called_once_with(2010.0, 2000.0)

    def test_enter_trade_insufficient_balance(self):
        """Test trade entry rejection due to insufficient balance."""
        self.mock_risk_manager.compute_lot_size.return_value = 0.1
        self.mock_risk_manager.enough_balance.return_value = False

        with self.assertRaises(RuntimeError):
            self.executor.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0)

    def test_enter_trade_daily_loss_limit_exceeded(self):
        """Test trade entry rejection due to daily loss limit."""
        self.mock_risk_manager.compute_lot_size.return_value = 0.1
        self.mock_risk_manager.enough_balance.return_value = True
        self.mock_risk_manager.check_daily_loss_limit.return_value = False

        with self.assertRaises(RuntimeError):
            self.executor.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0)

    def test_enter_trade_max_positions_exceeded(self):
        """Test trade entry rejection due to max concurrent positions."""
        self.mock_risk_manager.compute_lot_size.return_value = 0.1
        self.mock_risk_manager.enough_balance.return_value = True
        self.mock_risk_manager.check_daily_loss_limit.return_value = True
        self.mock_risk_manager.current_open_positions_count.return_value = 10  # At limit

        with self.assertRaises(RuntimeError):
            self.executor.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0)

    def test_enter_trade_invalid_lot_size(self):
        """Test trade entry rejection due to invalid lot size."""
        self.mock_risk_manager.compute_lot_size.return_value = None

        with self.assertRaises(RuntimeError):
            self.executor.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0)

    def test_close_all_positions_no_positions(self):
        """Test closing positions when none exist."""
        self.mock_mt5.positions_get.return_value = None

        self.executor.close_all_positions("XAUUSD")

        self.mock_mt5.positions_get.assert_called_once_with(symbol="XAUUSD")

    def test_close_all_positions_with_positions(self):
        """Test closing existing positions."""
        # Mock positions
        mock_position = Mock()
        mock_position.ticket = 12345
        mock_position.volume = 0.1
        mock_position.type = 0  # BUY position

        self.mock_mt5.positions_get.return_value = [mock_position]

        # Mock tick data
        mock_tick = Mock()
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        # Mock successful close order
        mock_result = Mock()
        self.mock_mt5.order_send.return_value = mock_result

        self.executor.close_all_positions("XAUUSD")

        self.mock_mt5.order_send.assert_called_once()

if __name__ == '__main__':
    unittest.main()
