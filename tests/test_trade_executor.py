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
        self.mock_config.ORDER_DEVIATION = 10
        self.mock_config.ORDER_RETRY = 3
        self.mock_config.MAX_CONCURRENT_POSITIONS = 10

        # Mock MT5 module
        self.mock_mt5 = Mock()
        self.mock_mt5.ORDER_TYPE_BUY = 0
        self.mock_mt5.ORDER_TYPE_SELL = 1
        self.mock_mt5.TRADE_ACTION_DEAL = 1
        self.mock_mt5.ORDER_TIME_GTC = 0
        self.mock_mt5.ORDER_FILLING_IOC = 0
        self.mock_mt5.TRADE_RETCODE_DONE = 10009
        self.mock_mt5.POSITION_TYPE_BUY = 0

        # Mock risk manager
        self.mock_risk_manager = Mock()

        # Create TradeExecutor instance
        self.executor = TradeExecutor(self.mock_mt5, self.mock_config, self.mock_risk_manager)

    def test_place_market_order_success_first_attempt(self):
        """Test successful market order placement on first attempt."""
        # Mock tick data
        mock_tick = Mock()
        mock_tick.ask = 2000.50
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
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        # Mock order results: fail twice, succeed on third
        mock_fail_result = Mock()
        mock_fail_result.retcode = 10006  # Some failure code
        mock_success_result = Mock()
        mock_success_result.retcode = 10009

        self.mock_mt5.order_send.side_effect = [mock_fail_result, mock_fail_result, mock_success_result]

        result = self.executor._place_market_order("XAUUSD", False, 0.05, 2010.0, 1990.0)

        self.assertEqual(result, mock_success_result)
        self.assertEqual(self.mock_mt5.order_send.call_count, 3)

    def test_place_market_order_failure_all_retries(self):
        """Test market order placement failure after all retries."""
        # Mock tick data
        mock_tick = Mock()
        mock_tick.ask = 2000.50
        mock_tick.bid = 2000.40
        self.mock_mt5.symbol_info_tick.return_value = mock_tick

        # Mock failed order results
        mock_result = Mock()
        mock_result.retcode = 10006
        self.mock_mt5.order_send.return_value = mock_result

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
