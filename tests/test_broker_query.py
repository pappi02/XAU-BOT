"""One safe way to ask "what is open" -- and both real callers use it.

Phase 12 follow-up: an audit found RiskManager.open_risk_fraction and
current_open_positions_count called mt5.positions_get() directly, repeating
the exact H-04 mistake (a disconnected terminal reading as "zero open
positions / zero open risk") that TradeExecutor.get_open_positions had
already been fixed to avoid. Fixed by extracting the safe query to one
module both now call.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config, fake_mt5

from execution.broker_query import BrokerQueryFailed, positions_or_raise, terminal_is_connected
from risk.risk_manager import RiskManager


class TestPositionsOrRaise(unittest.TestCase):
    def test_none_with_connected_terminal_is_empty(self):
        mt5 = fake_mt5(positions_get=MagicMock(return_value=None))
        self.assertEqual(positions_or_raise(mt5), [])

    def test_none_with_disconnected_terminal_is_unknown(self):
        mt5 = fake_mt5(positions_get=MagicMock(return_value=None))
        mt5.terminal_info.return_value = None
        with self.assertRaises(BrokerQueryFailed):
            positions_or_raise(mt5)

    def test_raising_query_is_unknown(self):
        mt5 = fake_mt5(positions_get=MagicMock(side_effect=RuntimeError("down")))
        with self.assertRaises(BrokerQueryFailed):
            positions_or_raise(mt5)

    def test_real_positions_pass_through(self):
        mt5 = fake_mt5(positions_get=MagicMock(return_value=[MagicMock(ticket=1)]))
        result = positions_or_raise(mt5, symbol="XAUUSD")
        self.assertEqual(len(result), 1)
        mt5.positions_get.assert_called_with(symbol="XAUUSD")

    def test_terminal_is_connected_swallows_exceptions(self):
        mt5 = MagicMock()
        mt5.terminal_info.side_effect = RuntimeError("boom")
        self.assertFalse(terminal_is_connected(mt5))


class TestRiskManagerUsesTheSafeQuery(unittest.TestCase):
    """RiskManager must fail the same way TradeExecutor does, not fail open."""

    def setUp(self):
        self.config = fake_config()
        self.mt5 = fake_mt5(positions_get=MagicMock(return_value=None))
        self.mt5.terminal_info.return_value = None       # disconnected
        self.rm = RiskManager(self.mt5, self.config)

    def test_open_risk_fraction_raises_when_state_is_unknown(self):
        with self.assertRaises(BrokerQueryFailed):
            self.rm.open_risk_fraction("XAUUSD")

    def test_current_open_positions_count_raises_when_state_is_unknown(self):
        with self.assertRaises(BrokerQueryFailed):
            self.rm.current_open_positions_count("XAUUSD")

    def test_open_risk_fraction_computes_correctly_when_connected(self):
        self.mt5.terminal_info.return_value = MagicMock(connected=True)
        pos = MagicMock(volume=0.1, price_open=2000.0, sl=1990.0)
        self.mt5.positions_get.return_value = [pos]
        # contract_size loads a real SymbolSpec from fake_mt5's symbol_info.
        fraction = self.rm.open_risk_fraction("XAUUSDm")
        expected_risk = abs(2000.0 - 1990.0) * 100.0 * 0.1     # contract_size 100
        expected_fraction = expected_risk / 10000.0            # fake account equity
        self.assertAlmostEqual(fraction, expected_fraction)

    def test_enter_trade_refuses_when_the_first_position_query_fails(self):
        # The existing, earlier guard in enter_trade.
        from fakes import make_executor

        mt5 = fake_mt5(positions_get=MagicMock(return_value=None))
        mt5.terminal_info.return_value = None
        ex = make_executor(mt5=mt5, config=self.config)
        with self.assertRaises(RuntimeError) as ctx:
            ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0, volume=0.1)
        self.assertIn("position state is unknown", str(ctx.exception))

    def test_enter_trade_refuses_when_the_portfolio_risk_query_fails(self):
        # Specifically exercises the try/except added around
        # check_portfolio_risk / current_open_positions_count: the FIRST
        # position query (get_open_positions) succeeds, but a later one
        # (inside check_portfolio_risk) fails -- a connection dropped between
        # the two calls in the same enter_trade invocation.
        from fakes import fake_risk_manager, make_executor
        from execution.broker_query import BrokerQueryFailed

        rm = fake_risk_manager(
            check_portfolio_risk=MagicMock(side_effect=BrokerQueryFailed("gone")))
        ex = make_executor(mt5=fake_mt5(), config=self.config, risk_manager=rm)
        with self.assertRaises(RuntimeError) as ctx:
            ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0, volume=0.1)
        self.assertIn("position state is unknown", str(ctx.exception))
        self.assertIn("gone", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
