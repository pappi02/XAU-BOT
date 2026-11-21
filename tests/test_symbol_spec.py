"""Phase 2 tests: the broker truth layer.

All doubles. The whole point of SymbolSpec is that instrument facts are read
rather than configured, so these tests feed it the values a broker would report
and assert the arithmetic that follows.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import make_executor

from execution.symbol_spec import (
    SymbolSpec,
    SymbolSpecError,
    money_to_price,
    price_to_money,
)
from execution.order_validator import (
    OrderValidator,
    Rejection,
    check_margin,
    choose_filling_mode,
    enforce_stops_level,
    normalize_volume,
)


def gold_spec(**overrides):
    """A realistic XAUUSD spec: 2 digits, 0.01 point, 100 oz per lot."""
    fields = dict(
        name="XAUUSDm",
        digits=2,
        point=0.01,
        contract_size=100.0,
        tick_value=1.0,
        tick_size=0.01,
        volume_min=0.01,
        volume_step=0.01,
        volume_max=50.0,
        stops_level_points=0,
        freeze_level_points=0,
        filling_modes=2,          # IOC
    )
    fields.update(overrides)
    return SymbolSpec(**fields)


def broker_info(**overrides):
    """A mock symbol_info() result."""
    fields = dict(
        name="XAUUSDm", digits=2, point=0.01, trade_contract_size=100.0,
        trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01,
        volume_step=0.01, volume_max=50.0, trade_stops_level=0,
        trade_freeze_level=0, filling_mode=2,
    )
    fields.update(overrides)
    return MagicMock(**fields)


class TestMoneyConversion(unittest.TestCase):
    """2.2: the plan's worked examples, which the old code got wrong by 1000x."""

    def test_price_to_money_micro_lot(self):
        spec = gold_spec()
        self.assertAlmostEqual(price_to_money(spec, 1.00, 0.01), 1.00)

    def test_price_to_money_standard_lot(self):
        spec = gold_spec()
        self.assertAlmostEqual(price_to_money(spec, 1.00, 1.00), 100.00)

    def test_old_fx_constant_would_have_been_wrong_by_1000x(self):
        # The shipped bug: CONTRACT_SIZE = 100000 instead of 100.
        correct = price_to_money(gold_spec(), 1.00, 1.00)
        wrong = price_to_money(gold_spec(contract_size=100000.0), 1.00, 1.00)
        self.assertEqual(wrong / correct, 1000.0)

    def test_round_trip(self):
        spec = gold_spec()
        self.assertAlmostEqual(
            money_to_price(spec, price_to_money(spec, 2.5, 0.3), 0.3), 2.5)

    def test_money_to_price_rejects_zero_lots(self):
        with self.assertRaises(SymbolSpecError):
            money_to_price(gold_spec(), 100.0, 0)


class TestSymbolSpecLoad(unittest.TestCase):
    """2.1: read the spec, never configure it."""

    def test_loads_fields_from_broker(self):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = broker_info()
        spec = SymbolSpec.load(mt5, "XAUUSDm")
        self.assertEqual(spec.contract_size, 100.0)
        self.assertEqual(spec.digits, 2)
        self.assertEqual(spec.point, 0.01)

    def test_three_digit_broker_is_honoured_not_assumed(self):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = broker_info(digits=3, point=0.001)
        spec = SymbolSpec.load(mt5, "XAUUSDm")
        self.assertEqual(spec.digits, 3)
        self.assertEqual(spec.round_price(1950.12345), 1950.123)

    def test_unknown_symbol_raises_with_a_useful_message(self):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = None
        mt5.symbol_select.return_value = False
        with self.assertRaises(SymbolSpecError) as ctx:
            SymbolSpec.load(mt5, "NOPE")
        self.assertIn("not available", str(ctx.exception))

    def test_symbol_not_in_market_watch_is_selected_then_reread(self):
        mt5 = MagicMock()
        mt5.symbol_info.side_effect = [None, broker_info()]
        mt5.symbol_select.return_value = True
        spec = SymbolSpec.load(mt5, "XAUUSDm")
        mt5.symbol_select.assert_called_once_with("XAUUSDm", True)
        self.assertEqual(spec.contract_size, 100.0)

    def test_contract_size_mismatch_is_loud(self):
        # A broker changing contract size is exactly the C-04 failure mode.
        mt5 = MagicMock()
        mt5.symbol_info.return_value = broker_info(trade_contract_size=1000.0)
        with self.assertRaises(SymbolSpecError) as ctx:
            SymbolSpec.load(mt5, "XAUUSDm", expected_contract_size=100.0)
        self.assertIn("contract_size", str(ctx.exception))

    def test_nonsense_spec_is_rejected(self):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = broker_info(point=0.0)
        with self.assertRaises(SymbolSpecError):
            SymbolSpec.load(mt5, "XAUUSDm")

    def test_spec_is_immutable(self):
        with self.assertRaises(Exception):
            gold_spec().contract_size = 999.0


class TestVolumeNormalisation(unittest.TestCase):
    """2.6: volume_step in {0.01, 0.1}, including below-min rejection."""

    def test_rounds_down_never_up(self):
        spec = gold_spec(volume_step=0.01)
        # 0.1749 must not become 0.18 -- that would exceed authorised risk.
        self.assertAlmostEqual(normalize_volume(spec, 0.1749), 0.17)

    def test_step_of_one_tenth(self):
        spec = gold_spec(volume_step=0.1, volume_min=0.1)
        self.assertAlmostEqual(normalize_volume(spec, 0.37), 0.3)

    def test_below_minimum_is_rejected_not_bumped_up(self):
        spec = gold_spec(volume_min=0.1, volume_step=0.1)
        result = normalize_volume(spec, 0.04)
        self.assertIsInstance(result, Rejection)
        self.assertIn("below broker minimum", result.reason)

    def test_above_maximum_is_capped(self):
        spec = gold_spec(volume_max=5.0)
        self.assertAlmostEqual(normalize_volume(spec, 12.0), 5.0)

    def test_zero_and_negative_rejected(self):
        spec = gold_spec()
        self.assertIsInstance(normalize_volume(spec, 0), Rejection)
        self.assertIsInstance(normalize_volume(spec, -1), Rejection)

    def test_floating_point_noise_does_not_lose_a_step(self):
        spec = gold_spec(volume_step=0.01)
        self.assertAlmostEqual(normalize_volume(spec, 0.03), 0.03)


class TestStopsLevel(unittest.TestCase):
    """2.6: with stops_level=50, a $0.20 stop is widened -- never sent as-is."""

    def test_too_close_buy_stop_is_widened(self):
        spec = gold_spec(stops_level_points=50)     # 50 * 0.01 = $0.50
        sl, tp = enforce_stops_level(spec, price=1950.00, sl=1949.80,
                                     tp=None, is_buy=True)
        self.assertLessEqual(sl, 1949.50)

    def test_too_close_sell_stop_is_widened(self):
        spec = gold_spec(stops_level_points=50)
        sl, tp = enforce_stops_level(spec, price=1950.00, sl=1950.20,
                                     tp=None, is_buy=False)
        self.assertGreaterEqual(sl, 1950.50)

    def test_stop_is_never_dropped(self):
        spec = gold_spec(stops_level_points=500)
        sl, tp = enforce_stops_level(spec, price=1950.00, sl=1949.99,
                                     tp=None, is_buy=True)
        self.assertIsNotNone(sl)

    def test_already_distant_stop_is_left_alone(self):
        spec = gold_spec(stops_level_points=50)
        sl, tp = enforce_stops_level(spec, price=1950.00, sl=1940.00,
                                     tp=1970.00, is_buy=True)
        self.assertAlmostEqual(sl, 1940.00)
        self.assertAlmostEqual(tp, 1970.00)

    def test_take_profit_is_widened_too(self):
        spec = gold_spec(stops_level_points=50)
        sl, tp = enforce_stops_level(spec, price=1950.00, sl=None,
                                     tp=1950.10, is_buy=True)
        self.assertGreaterEqual(tp, 1950.50)

    def test_prices_are_rounded_to_symbol_digits_not_hardcoded_two(self):
        spec = gold_spec(digits=3, point=0.001)
        sl, tp = enforce_stops_level(spec, price=1950.0, sl=1949.12345,
                                     tp=None, is_buy=True)
        self.assertEqual(sl, 1949.123)


class TestFillingMode(unittest.TestCase):
    """2.3: an FOK-only broker must get a compliant request, not 10030 forever."""

    def _mt5(self):
        mt5 = MagicMock()
        mt5.SYMBOL_FILLING_FOK = 1
        mt5.SYMBOL_FILLING_IOC = 2
        mt5.ORDER_FILLING_FOK = "FOK"
        mt5.ORDER_FILLING_IOC = "IOC"
        mt5.ORDER_FILLING_RETURN = "RETURN"
        return mt5

    def test_ioc_preferred_when_supported(self):
        mt5 = self._mt5()
        self.assertEqual(choose_filling_mode(mt5, gold_spec(filling_modes=2)),
                         "IOC")

    def test_fok_only_broker_gets_fok(self):
        mt5 = self._mt5()
        self.assertEqual(choose_filling_mode(mt5, gold_spec(filling_modes=1)),
                         "FOK")

    def test_both_supported_prefers_ioc(self):
        mt5 = self._mt5()
        self.assertEqual(choose_filling_mode(mt5, gold_spec(filling_modes=3)),
                         "IOC")

    def test_neither_flag_falls_back_to_return(self):
        mt5 = self._mt5()
        self.assertEqual(choose_filling_mode(mt5, gold_spec(filling_modes=0)),
                         "RETURN")


class TestMarginCheck(unittest.TestCase):
    """2.3: order_calc_margin appeared nowhere in the audited code."""

    def _mt5(self, required, free):
        mt5 = MagicMock()
        mt5.order_calc_margin.return_value = required
        mt5.account_info.return_value = MagicMock(margin_free=free)
        mt5.ORDER_TYPE_BUY = 0
        return mt5

    def test_within_budget_passes(self):
        mt5 = self._mt5(required=100.0, free=1000.0)
        self.assertIsNone(check_margin(mt5, gold_spec(), 0, 0.1, 1950.0))

    def test_over_budget_rejected(self):
        mt5 = self._mt5(required=500.0, free=1000.0)   # cap is 25% = 250
        result = check_margin(mt5, gold_spec(), 0, 1.0, 1950.0)
        self.assertIsInstance(result, Rejection)
        self.assertIn("margin", result.reason)

    def test_margin_call_failure_is_a_rejection_not_a_crash(self):
        mt5 = self._mt5(required=None, free=1000.0)
        self.assertIsInstance(check_margin(mt5, gold_spec(), 0, 0.1, 1950.0),
                              Rejection)


class TestOrderValidator(unittest.TestCase):
    """The whole path: normalise a request or refuse it."""

    def _mt5(self):
        mt5 = MagicMock()
        mt5.ORDER_TYPE_BUY = 0
        mt5.ORDER_TYPE_SELL = 1
        mt5.SYMBOL_FILLING_FOK = 1
        mt5.SYMBOL_FILLING_IOC = 2
        mt5.ORDER_FILLING_IOC = "IOC"
        mt5.ORDER_FILLING_FOK = "FOK"
        mt5.order_calc_margin.return_value = 10.0
        mt5.account_info.return_value = MagicMock(margin_free=10000.0)
        return mt5

    def test_valid_order_is_normalised(self):
        mt5 = self._mt5()
        v = OrderValidator(mt5, gold_spec(stops_level_points=50))
        out = v.normalize(mt5.ORDER_TYPE_BUY, volume=0.1749, price=1950.004,
                          sl=1945.0, tp=1960.0)
        self.assertNotIsInstance(out, Rejection)
        self.assertAlmostEqual(out["volume"], 0.17)
        self.assertAlmostEqual(out["price"], 1950.00)
        self.assertEqual(out["type_filling"], "IOC")

    def test_inverted_stop_is_rejected(self):
        mt5 = self._mt5()
        v = OrderValidator(mt5, gold_spec())
        out = v.normalize(mt5.ORDER_TYPE_BUY, volume=0.1, price=1950.0,
                          sl=1960.0, tp=1970.0)
        self.assertIsInstance(out, Rejection)
        self.assertIn("stop loss is above entry", out.reason)

    def test_rejection_is_falsey_so_callers_can_branch_on_it(self):
        self.assertFalse(Rejection("nope"))

    def test_undersized_volume_rejected_before_any_margin_call(self):
        mt5 = self._mt5()
        v = OrderValidator(mt5, gold_spec(volume_min=0.1, volume_step=0.1))
        out = v.normalize(mt5.ORDER_TYPE_BUY, volume=0.01, price=1950.0)
        self.assertIsInstance(out, Rejection)
        mt5.order_calc_margin.assert_not_called()




class TestSpreadGate(unittest.TestCase):
    """2.4: there was no spread filter anywhere in the audited codebase."""

    def test_spread_is_reported_in_points(self):
        mt5 = MagicMock()
        mt5.symbol_info_tick.return_value = MagicMock(bid=1950.00, ask=1950.35)
        self.assertAlmostEqual(gold_spec().spread_points(mt5), 35.0)

    def test_missing_tick_is_unknown_not_zero(self):
        mt5 = MagicMock()
        mt5.symbol_info_tick.return_value = None
        self.assertIsNone(gold_spec().spread_points(mt5))

    def test_unreadable_tick_is_unknown_not_zero(self):
        # A zero here would look like the tightest possible spread and wave
        # every order through the gate.
        mt5 = MagicMock()
        mt5.symbol_info_tick.return_value = MagicMock(bid=None, ask=None)
        self.assertIsNone(gold_spec().spread_points(mt5))


class TestTicketIdentity(unittest.TestCase):
    """2.5 (L-08): result.order is the ORDER ticket, not the position ticket."""

    def _executor(self):
        from execution.trade_executor import TradeExecutor
        return make_executor()

    def test_position_ticket_preferred_over_order_ticket(self):
        from execution.trade_executor import MAGIC
        ex = self._executor()
        ex.mt5.positions_get.return_value = [
            MagicMock(ticket=555, magic=MAGIC, time=2000),
        ]
        resolved = ex._resolve_position_ticket("XAUUSDm", MagicMock(order=111))
        self.assertEqual(resolved, 555)

    def test_newest_of_our_positions_is_chosen(self):
        from execution.trade_executor import MAGIC
        ex = self._executor()
        ex.mt5.positions_get.return_value = [
            MagicMock(ticket=100, magic=MAGIC, time=1000),
            MagicMock(ticket=300, magic=MAGIC, time=3000),
            MagicMock(ticket=200, magic=MAGIC, time=2000),
        ]
        self.assertEqual(
            ex._resolve_position_ticket("XAUUSDm", MagicMock(order=1)), 300)

    def test_other_bots_positions_are_ignored(self):
        from execution.trade_executor import MAGIC
        ex = self._executor()
        ex.mt5.positions_get.return_value = [
            MagicMock(ticket=999, magic=12345, time=9999),   # not ours
            MagicMock(ticket=777, magic=MAGIC, time=1000),
        ]
        self.assertEqual(
            ex._resolve_position_ticket("XAUUSDm", MagicMock(order=1)), 777)

    def test_falls_back_to_order_ticket_when_nothing_found(self):
        ex = self._executor()
        ex.mt5.positions_get.return_value = []
        self.assertEqual(
            ex._resolve_position_ticket("XAUUSDm", MagicMock(order=42)), 42)


class TestMoneyPerPriceVerification(unittest.TestCase):
    """Sizing uses contract_size; the broker's profit calculator is the judge."""

    def setUp(self):
        from execution import symbol_spec
        symbol_spec._WARNED.clear()

    def _mt5(self, profit, **info):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = broker_info(**info)
        mt5.order_calc_profit.return_value = profit
        return mt5

    def test_calculator_confirming_contract_size_passes(self):
        # The real demo spec: tick_value 0.1 per 0.01 tick, contract 100,
        # order_calc_profit = 100.0 (measured 2026-09-13).
        spec = SymbolSpec.load(self._mt5(100.0, trade_tick_value=0.1), "XAUUSD")
        self.assertEqual(spec.contract_size, 100.0)

    def test_calculator_contradicting_contract_size_refuses(self):
        with self.assertRaises(SymbolSpecError):
            SymbolSpec.load(self._mt5(10.0), "XAUUSD")

    def test_no_calculator_warns_once_on_mismatch(self):
        mt5 = self._mt5(None, trade_tick_value=0.1)
        with self.assertLogs("execution.symbol_spec", "WARNING") as logs:
            SymbolSpec.load(mt5, "XAUUSDm")
            SymbolSpec.load(mt5, "XAUUSDm")
        self.assertEqual(len(logs.output), 1)

    def test_unusable_tick_data_has_no_ratio(self):
        self.assertIsNone(gold_spec(tick_value=0.0).tick_value_ratio())


if __name__ == "__main__":
    unittest.main()
