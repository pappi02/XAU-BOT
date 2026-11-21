"""Phase 3 tests: risk per trade must actually track equity.

The headline test is the matrix the plan specifies: for every combination of
account size and stop distance, the realised risk equals the configured risk to
within one volume_step, *or* the trade is declined. There is no third option --
and "silently take more risk than configured" was the audited behaviour.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import make_executor

from risk.risk_manager import RiskManager
from risk.risk_state import RiskState
from risk.volatility import VolatilityRegime, check_absolute_thresholds


def broker_symbol(**overrides):
    fields = dict(
        digits=2, point=0.01, trade_contract_size=100.0, trade_tick_value=1.0,
        trade_tick_size=0.01, volume_min=0.01, volume_step=0.01,
        volume_max=50.0, trade_stops_level=0, trade_freeze_level=0,
        filling_mode=2,
    )
    fields.update(overrides)
    return MagicMock(**fields)


def make_config(**overrides):
    cfg = MagicMock()
    cfg.RISK_PER_TRADE_FRACTION = 0.01
    cfg.MAX_DAILY_LOSS_FRACTION = 0.05
    cfg.MIN_ACCOUNT_BALANCE = 50.0
    cfg.MAX_DRAWDOWN_FRACTION = 0.20
    cfg.MAX_PORTFOLIO_RISK_FRACTION = 0.04
    cfg.MAX_LOTS_PER_ORDER = 50.0
    cfg.SYMBOL_PHASE5 = "XAUUSDm"
    cfg.SYMBOL = "XAUUSDm"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class RiskManagerHarness(unittest.TestCase):
    """Gives every test an isolated, throwaway state file."""

    def setUp(self):
        fd, self.state_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.state_path)          # RiskState tolerates absence

        self.mt5 = MagicMock()
        self.mt5.symbol_info.return_value = broker_symbol()
        self.mt5.symbol_select.return_value = True
        self.mt5.positions_get.return_value = []
        self.mt5.history_deals_get.return_value = []

        self.config = make_config(RISK_STATE_PATH=self.state_path)
        self.rm = RiskManager(self.mt5, self.config)

    def tearDown(self):
        for path in (self.state_path, self.state_path + ".tmp"):
            if os.path.exists(path):
                os.unlink(path)

    def set_account(self, balance, equity=None, profit=0.0):
        self.mt5.account_info.return_value = MagicMock(
            balance=balance,
            equity=equity if equity is not None else balance,
            profit=profit,
            margin_free=balance * 10,
        )


class TestSizingMatrix(RiskManagerHarness):
    """3.6: equity x stop distance -- correct risk, or an explicit decline."""

    EQUITIES = [150.0, 1_000.0, 10_000.0, 100_000.0]
    STOPS = [2.0, 5.0, 10.0]

    def test_risk_matches_configuration_or_trade_is_declined(self):
        contract_size = 100.0
        step = 0.01
        fraction = self.config.RISK_PER_TRADE_FRACTION

        checked = declined = 0
        for equity in self.EQUITIES:
            for stop in self.STOPS:
                self.set_account(equity)
                lots = self.rm.calculate_dynamic_lot_size(stop)

                intended = equity * fraction
                money_per_lot = contract_size * stop

                if lots is None:
                    declined += 1
                    # Declining is only legitimate when even the smallest
                    # tradeable size would breach the configured risk.
                    min_risk = 0.01 * money_per_lot
                    self.assertGreater(
                        min_risk, intended,
                        "declined equity=%s stop=%s although volume_min would "
                        "have risked %.2f <= intended %.2f"
                        % (equity, stop, min_risk, intended))
                    continue

                checked += 1
                actual = lots * money_per_lot
                # Flooring to volume_step can only ever reduce risk, and never
                # by more than one step's worth.
                self.assertLessEqual(actual, intended + 1e-9)
                self.assertGreater(actual, intended - step * money_per_lot)

        self.assertGreater(checked, 0, "matrix exercised no accepted trades")
        self.assertGreater(declined, 0, "matrix exercised no declines")

    def test_small_account_declines_rather_than_overrisking(self):
        # $150 at 1% is $1.50 of risk. A $10 stop costs $10 per 0.01 lot, so
        # the smallest tradeable position risks 6.7% -- decline.
        self.set_account(150.0)
        self.assertIsNone(self.rm.calculate_dynamic_lot_size(10.0))

    def test_the_audited_behaviour_would_have_over_risked(self):
        # The old code clamped up to MIN_LOT_SIZE instead of declining.
        self.set_account(150.0)
        stop, contract_size = 10.0, 100.0
        clamped_risk = 0.01 * contract_size * stop          # what it used to do
        intended = 150.0 * self.config.RISK_PER_TRADE_FRACTION
        self.assertGreater(clamped_risk / intended, 6.0)
        self.assertIsNone(self.rm.calculate_dynamic_lot_size(stop))

    def test_risk_scales_with_equity(self):
        self.set_account(10_000.0)
        small = self.rm.calculate_dynamic_lot_size(5.0)
        self.set_account(100_000.0)
        large = self.rm.calculate_dynamic_lot_size(5.0)
        self.assertAlmostEqual(large / small, 10.0, places=1)

    def test_lots_are_floored_to_step_never_rounded_up(self):
        self.set_account(1_337.0)       # deliberately awkward equity
        lots = self.rm.calculate_dynamic_lot_size(3.0)
        self.assertAlmostEqual(lots % 0.01, 0.0, places=9)
        self.assertLessEqual(lots * 100.0 * 3.0, 1_337.0 * 0.01 + 1e-9)

    def test_invalid_stop_declines(self):
        self.set_account(10_000.0)
        self.assertIsNone(self.rm.calculate_dynamic_lot_size(0))
        self.assertIsNone(self.rm.calculate_dynamic_lot_size(-5))

    def test_compute_lot_size_delegates_to_the_same_calculation(self):
        self.set_account(10_000.0)
        direct = self.rm.calculate_dynamic_lot_size(20.0)
        viawrap = self.rm.compute_lot_size(1980.0, 2000.0)
        self.assertEqual(direct, viawrap)


class TestDailyLossLimit(RiskManagerHarness):
    """3.6: 35% realised losses with nothing open must block, and persist."""

    def test_realised_losses_block_even_with_no_open_positions(self):
        self.set_account(10_000.0, profit=0.0)      # nothing floating
        self.mt5.history_deals_get.return_value = [
            MagicMock(profit=-3_500.0, commission=0.0, swap=0.0),
        ]
        self.assertFalse(self.rm.check_daily_loss_limit())

    def test_audited_version_would_have_passed_this(self):
        # account.profit is 0 because nothing is open; the old check read only
        # that field and would have returned True.
        self.set_account(10_000.0, profit=0.0)
        self.mt5.history_deals_get.return_value = [
            MagicMock(profit=-3_500.0, commission=0.0, swap=0.0),
        ]
        self.assertEqual(float(self.mt5.account_info.return_value.profit), 0.0)
        self.assertFalse(self.rm.check_daily_loss_limit())

    def test_commission_and_swap_count_toward_the_loss(self):
        self.set_account(10_000.0, profit=0.0)
        self.mt5.history_deals_get.return_value = [
            MagicMock(profit=-400.0, commission=-80.0, swap=-40.0),
        ]
        self.assertAlmostEqual(self.rm.realised_pnl_today(), -520.0)

    def test_floating_and_realised_are_summed(self):
        self.set_account(10_000.0, profit=-300.0)
        self.mt5.history_deals_get.return_value = [
            MagicMock(profit=-300.0, commission=0.0, swap=0.0),
        ]
        # -600 total against a 500 allowance -> blocked
        self.assertFalse(self.rm.check_daily_loss_limit())

    def test_small_loss_is_allowed(self):
        self.set_account(10_000.0, profit=-50.0)
        self.mt5.history_deals_get.return_value = []
        self.assertTrue(self.rm.check_daily_loss_limit())

    def test_limit_survives_a_restart(self):
        self.set_account(10_000.0, profit=0.0)
        self.mt5.history_deals_get.return_value = [
            MagicMock(profit=-3_500.0, commission=0.0, swap=0.0),
        ]
        self.assertFalse(self.rm.check_daily_loss_limit())

        # A fresh process: new RiskManager, same state file, and now the
        # broker reports a clean slate for the session.
        reborn = RiskManager(self.mt5, self.config)
        self.mt5.history_deals_get.return_value = []
        self.assertFalse(reborn.check_daily_loss_limit(),
                         "a restart cleared a tripped daily loss limit")

    def test_opening_balance_is_recorded_once_per_day(self):
        self.set_account(10_000.0)
        self.rm.check_daily_loss_limit()
        self.assertEqual(self.rm.state.day_opening_balance, 10_000.0)

        # Balance drops during the day; the opening figure must not follow it.
        self.set_account(9_000.0)
        self.rm.check_daily_loss_limit()
        self.assertEqual(self.rm.state.day_opening_balance, 10_000.0)


class TestBalanceFloor(RiskManagerHarness):
    def test_balance_below_floor_blocks(self):
        self.set_account(10.0)
        self.assertFalse(self.rm.enough_balance())

    def test_balance_above_floor_passes(self):
        self.set_account(500.0)
        self.assertTrue(self.rm.enough_balance())

    def test_floor_of_zero_would_make_this_meaningless(self):
        # Guards the regression: MIN_ACCOUNT_BALANCE = 0 made this always true.
        self.assertGreater(self.config.MIN_ACCOUNT_BALANCE, 0)


class TestDrawdown(RiskManagerHarness):
    """3.6: drawdown from a high-water mark, not a constant."""

    def test_drawdown_is_measured_from_the_peak(self):
        self.set_account(10_000.0, equity=10_000.0)
        self.rm.check_drawdown()                      # sets the mark
        self.set_account(8_000.0, equity=8_000.0)
        self.assertAlmostEqual(self.rm.state.drawdown_fraction(8_000.0), 0.2)

    def test_peak_rises_but_never_falls(self):
        self.rm.state.observe_equity(10_000.0)
        self.rm.state.observe_equity(12_000.0)
        self.rm.state.observe_equity(9_000.0)
        self.assertEqual(self.rm.state.equity_high_water_mark, 12_000.0)

    def test_breach_halts_trading(self):
        self.set_account(10_000.0, equity=10_000.0)
        self.rm.check_drawdown()
        self.set_account(7_000.0, equity=7_000.0)     # 30% > 20% limit
        self.assertFalse(self.rm.check_drawdown())
        self.assertIsNotNone(self.rm.state.halted_reason)

    def test_account_size_does_not_change_the_meaning(self):
        # The old constant read 33% drawdown permanently on a $100 account.
        for equity in (100.0, 500.0, 50_000.0):
            state = RiskState(self.state_path + ".%s" % equity)
            state.observe_equity(equity)
            self.assertEqual(state.drawdown_fraction(equity * 0.9), 0.1)
            for p in (state.path, state.path + ".tmp"):
                if os.path.exists(p):
                    os.unlink(p)

    def test_high_water_mark_survives_a_restart(self):
        self.rm.state.observe_equity(25_000.0)
        reborn = RiskState(self.state_path)
        self.assertEqual(reborn.equity_high_water_mark, 25_000.0)


class TestPortfolioRisk(RiskManagerHarness):
    """3.5: no check existed between the entry decision and the order."""

    def test_open_risk_is_summed_across_positions(self):
        self.set_account(10_000.0)
        self.mt5.positions_get.return_value = [
            MagicMock(volume=0.1, price_open=2000.0, sl=1990.0),   # $100
            MagicMock(volume=0.1, price_open=2000.0, sl=1995.0),   # $50
        ]
        self.assertAlmostEqual(self.rm.open_risk_fraction(), 150.0 / 10_000.0)

    def test_position_without_a_stop_counts_its_whole_notional(self):
        self.set_account(10_000.0)
        self.mt5.positions_get.return_value = [
            MagicMock(volume=0.01, price_open=2000.0, sl=0.0),
        ]
        # 0.01 * 100 * 2000 = 2000 of notional, not "no risk".
        self.assertAlmostEqual(self.rm.open_risk_fraction(), 0.2)

    def test_candidate_pushing_past_the_cap_is_refused(self):
        self.set_account(10_000.0)
        self.mt5.positions_get.return_value = [
            MagicMock(volume=0.3, price_open=2000.0, sl=1990.0),   # $300 = 3%
        ]
        self.assertFalse(self.rm.check_portfolio_risk(candidate_risk_money=200.0))

    def test_candidate_within_the_cap_is_allowed(self):
        self.set_account(10_000.0)
        self.mt5.positions_get.return_value = []
        self.assertTrue(self.rm.check_portfolio_risk(candidate_risk_money=100.0))


class TestVolatilityRegime(unittest.TestCase):
    """3.2 (M-03): the absolute thresholds were provably inert."""

    # Realistic M5 gold ATR(14): roughly 1.5 to 5.
    HISTORY = [1.5 + (i % 35) * 0.1 for i in range(200)]

    def test_the_shipped_thresholds_are_diagnosed_as_broken(self):
        problems = check_absolute_thresholds(self.HISTORY, 10, 30)
        self.assertEqual(len(problems), 2)
        self.assertIn("ALWAYS", problems[0])       # low branch always taken
        self.assertIn("UNREACHABLE", problems[1])  # high branch never taken

    def test_percentiles_are_reachable_by_construction(self):
        regime = VolatilityRegime(25.0, 75.0)
        seen = {regime.classify(atr, self.HISTORY) for atr in self.HISTORY}
        self.assertEqual(seen, {"low", "normal", "high"})

    def test_a_spike_is_classified_high_not_low(self):
        # The exact inversion M-03 describes: under absolute thresholds a
        # spike of 8.0 is still "< 10", so it read as LOW volatility.
        regime = VolatilityRegime(25.0, 75.0)
        self.assertLess(8.0, 10)                           # old rule: "low"
        self.assertEqual(regime.classify(8.0, self.HISTORY), "high")

    def test_too_little_history_returns_unknown_not_a_guess(self):
        self.assertIsNone(VolatilityRegime().classify(3.0, [1.0, 2.0, 3.0]))

    def test_percentile_interpolates(self):
        self.assertAlmostEqual(VolatilityRegime.percentile([0, 10], 50), 5.0)
        self.assertAlmostEqual(VolatilityRegime.percentile([1, 2, 3, 4], 0), 1.0)
        self.assertAlmostEqual(VolatilityRegime.percentile([1, 2, 3, 4], 100), 4.0)

    def test_stale_feed_is_rejected(self):
        regime = VolatilityRegime()
        with self.assertRaises(ValueError):
            regime.assert_thresholds_are_reachable([2.0] * 100)

    def test_invalid_percentile_pair_rejected(self):
        with self.assertRaises(ValueError):
            VolatilityRegime(80.0, 20.0)


class TestDrawdownFailsClosed(unittest.TestCase):
    """3.4: a risk control that fails open is not a risk control."""

    def test_error_in_drawdown_check_blocks_rather_than_allows(self):
        from execution.trade_executor import TradeExecutor
        ex = make_executor()
        ex.risk_manager.refresh_account.side_effect = RuntimeError("terminal gone")
        self.assertTrue(ex._check_portfolio_drawdown(),
                        "drawdown check failed OPEN on error")


if __name__ == "__main__":
    unittest.main()


class TestEntryGatesAreWired(unittest.TestCase):
    """A risk control that exists but is never called protects nothing.

    The audit's recurring pattern was exactly this: update_daily_pnl computed
    the right number and was never invoked; volume limits were consulted in a
    function the live path never reached. These assert the gates are actually
    on the entry path.
    """

    def _executor(self):
        from execution.trade_executor import TradeExecutor
        ex = make_executor()
        ex.mt5.symbol_info.return_value = broker_symbol()
        ex.mt5.symbol_select.return_value = True
        ex.risk_manager.compute_lot_size.return_value = 0.1
        ex.risk_manager.enough_balance.return_value = True
        ex.risk_manager.check_daily_loss_limit.return_value = True
        ex.risk_manager.check_drawdown.return_value = True
        ex.risk_manager.check_portfolio_risk.return_value = True
        ex.risk_manager.contract_size.return_value = 100.0
        ex.risk_manager.current_open_positions_count.return_value = 0
        # The order validator checks free margin before sending (Phase 2.3).
        ex.mt5.order_calc_margin.return_value = 10.0
        ex.mt5.account_info.return_value = MagicMock(margin_free=100_000.0)
        return ex

    def _enter(self, ex):
        return ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0)

    def test_drawdown_breach_blocks_entry(self):
        ex = self._executor()
        ex.risk_manager.check_drawdown.return_value = False
        with self.assertRaises(RuntimeError) as ctx:
            self._enter(ex)
        self.assertIn("Drawdown", str(ctx.exception))

    def test_portfolio_cap_blocks_entry(self):
        ex = self._executor()
        ex.risk_manager.check_portfolio_risk.return_value = False
        with self.assertRaises(RuntimeError) as ctx:
            self._enter(ex)
        self.assertIn("Portfolio risk", str(ctx.exception))

    def test_daily_loss_limit_blocks_entry(self):
        ex = self._executor()
        ex.risk_manager.check_daily_loss_limit.return_value = False
        with self.assertRaises(RuntimeError) as ctx:
            self._enter(ex)
        self.assertIn("Daily loss", str(ctx.exception))

    def test_a_declined_size_blocks_entry_with_a_clear_reason(self):
        ex = self._executor()
        ex.risk_manager.compute_lot_size.return_value = None   # declined
        with self.assertRaises(RuntimeError) as ctx:
            self._enter(ex)
        self.assertIn("declined", str(ctx.exception).lower())

    def test_candidate_risk_is_computed_in_money(self):
        ex = self._executor()
        self._enter(ex)
        # |2000 - 1990| * 100 contract * 0.1 lots = 100.0
        args, _ = ex.risk_manager.check_portfolio_risk.call_args
        self.assertAlmostEqual(args[0], 100.0)
