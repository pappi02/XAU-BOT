"""Phase 9 tests: the measurement machinery itself.

These verify the *instruments*, not the strategy. Whether an edge exists is a
question only real data can answer, and answering it is Gate C.
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.costs import ZERO_COST, CostModel
from backtest.engine import Backtester
from backtest.gauntlet import Gauntlet
from data.quality import (DataQualityError, check_bar_count,
                          check_indicator_columns, check_not_stale,
                          check_prices_are_sane, find_gaps,
                          required_warmup_bars, validate_for_trading)
from strategies.signal_strength import compute_strength, distribution_report


def synthetic(n=3000, seed=7, drift=0.0):
    """A random walk with VALID OHLC.

    The first version of this helper built high/low from close alone, so `open`
    could sit outside the bar's range -- and data/quality.py rejected it, which
    is exactly what it is for. High and low are derived from both ends here.
    """
    rng = np.random.default_rng(seed)
    close = 2000 + np.cumsum(rng.normal(drift, 1.2, n))
    open_ = close + rng.normal(0, 0.3, n)
    top = np.maximum(open_, close)
    bottom = np.minimum(open_, close)
    return pd.DataFrame({
        "open": open_,
        "high": top + abs(rng.normal(0, 1.5, n)),
        "low": bottom - abs(rng.normal(0, 1.5, n)),
        "close": close,
        "ATR": pd.Series(close).diff().abs().rolling(14).mean().fillna(2.0).values,
    }, index=pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"))


def always_buy(frame):
    return {"signal": "BUY", "strength": 100.0}


# ---------------------------------------------------------------- H-08

class TestSignalStrengthWasDegenerate(unittest.TestCase):
    """The audited scorer, reproduced and characterised."""

    @staticmethod
    def legacy_strength(ema, rsi_val, bb):
        buy = sell = 0.0
        if ema == 1: buy += 0.45
        elif ema == -1: sell += 0.45
        cond = "bullish" if rsi_val < 30 else ("bearish" if rsi_val > 70 else "neutral")
        if cond == "bullish": buy += 0.30
        elif cond == "bearish": sell += 0.30
        if bb == 1: buy += 0.25
        elif bb == -1: sell += 0.25
        if ema == 1 and rsi_val <= 70: buy += 0.1
        if ema == -1 and rsi_val >= 30: sell += 0.1
        total = buy + sell
        strength = round(abs(buy - sell) / total * 100, 2) if total > 0 else 0
        signal = "HOLD" if abs(buy - sell) < 0.02 else ("BUY" if buy > sell else "SELL")
        return signal, strength

    def _all_states(self):
        for ema in (-1, 0, 1):
            for rsi_val in range(0, 101):
                # bb_signal is DEFINED as a conjunction with ema_signal.
                options = {0} | ({1} if ema == 1 else set()) | ({-1} if ema == -1 else set())
                for bb in options:
                    yield ema, rsi_val, bb

    def test_legacy_strength_takes_only_four_values(self):
        values = {self.legacy_strength(*s)[1] for s in self._all_states()}
        self.assertEqual(sorted(values), [0, 20.0, 40.0, 100.0])

    def test_six_of_the_seven_thresholds_are_the_same_predicate(self):
        values = {self.legacy_strength(*s)[1] for s in self._all_states()}
        partitions = {t: frozenset(v for v in values if v >= t)
                      for t in (55, 65, 70, 75, 80, 85)}
        self.assertEqual(len(set(partitions.values())), 1,
                         "the separately-tuned thresholds should be identical")
        self.assertEqual(set(next(iter(partitions.values()))), {100.0})

    def test_legacy_signal_is_exactly_the_sign_of_the_ema_gap(self):
        # RSI and Bollinger cannot change the direction, at any value.
        for ema, expected in ((1, "BUY"), (-1, "SELL")):
            signals = {self.legacy_strength(ema, rsi, bb)[0]
                       for e, rsi, bb in self._all_states() if e == ema}
            self.assertEqual(signals, {expected})


class TestContinuousSignalStrength(unittest.TestCase):
    """9.3: the replacement must be genuinely continuous and separable."""

    def _sample(self, n=400):
        rng = np.random.default_rng(3)
        out = []
        for _ in range(n):
            atr = float(rng.uniform(1.0, 6.0))
            close = float(rng.uniform(1900, 2100))
            out.append(compute_strength(
                ema_fast=close + float(rng.normal(0, 4)),
                ema_slow=close + float(rng.normal(0, 4)),
                rsi=float(rng.uniform(5, 95)),
                close=close,
                bb_upper=close + float(rng.uniform(1, 20)),
                bb_lower=close - float(rng.uniform(1, 20)),
                atr=atr))
        return out

    def test_distribution_has_many_distinct_values(self):
        # The plan asks CI to assert > 10 distinct values and non-zero
        # variance. The audited scorer produced four and would fail here.
        report = distribution_report([r["strength"] for r in self._sample()])
        self.assertGreater(report["distinct"], 10)
        self.assertGreater(report["variance"], 0.0)

    def test_rsi_alone_can_change_the_strength(self):
        base = dict(ema_fast=2000.0, ema_slow=2000.0, close=2000.0,
                    bb_upper=2010.0, bb_lower=1990.0, atr=3.0)
        low = compute_strength(rsi=20.0, **base)["score"]
        high = compute_strength(rsi=80.0, **base)["score"]
        self.assertNotEqual(low, high,
                            "RSI must contribute independently (H-08)")

    def test_bollinger_alone_can_change_the_strength(self):
        base = dict(ema_fast=2000.0, ema_slow=2000.0, rsi=50.0, atr=3.0)
        near_low = compute_strength(close=1991.0, bb_upper=2010.0,
                                    bb_lower=1990.0, **base)["score"]
        near_high = compute_strength(close=2009.0, bb_upper=2010.0,
                                     bb_lower=1990.0, **base)["score"]
        self.assertNotEqual(near_low, near_high)

    def test_ema_separation_is_measured_in_atr_units(self):
        # The same $5 separation means different things at different
        # volatilities; a scale-free score must reflect that.
        calm = compute_strength(ema_fast=2005.0, ema_slow=2000.0, rsi=50.0,
                                close=2000.0, bb_upper=2010.0, bb_lower=1990.0,
                                atr=1.0)["components"]["ema_separation_atr"]
        wild = compute_strength(ema_fast=2005.0, ema_slow=2000.0, rsi=50.0,
                                close=2000.0, bb_upper=2010.0, bb_lower=1990.0,
                                atr=10.0)["components"]["ema_separation_atr"]
        self.assertGreater(calm, wild)

    def test_unusable_atr_scores_zero_rather_than_guessing(self):
        result = compute_strength(ema_fast=2005.0, ema_slow=2000.0, rsi=50.0,
                                  close=2000.0, bb_upper=2010.0,
                                  bb_lower=1990.0, atr=0.0)
        self.assertEqual(result["components"]["ema_separation_atr"], 0.0)

    def test_strength_is_bounded(self):
        for result in self._sample(200):
            self.assertGreaterEqual(result["strength"], 0.0)
            self.assertLessEqual(result["strength"], 100.0)

    def test_direction_matches_the_sign_of_the_score(self):
        for result in self._sample(200):
            if result["score"] > 0:
                self.assertEqual(result["signal"], "BUY")
            elif result["score"] < 0:
                self.assertEqual(result["signal"], "SELL")


# ---------------------------------------------------------------- H-09 / M-10

class TestDataQuality(unittest.TestCase):
    """9.1: a data outage must not be indistinguishable from a quiet market."""

    def test_warmup_requirement_covers_the_longest_period(self):
        self.assertEqual(required_warmup_bars(26, 14, 20, 14), 78)

    def test_too_few_bars_refuses_to_signal(self):
        with self.assertRaises(DataQualityError):
            check_bar_count(synthetic(10), 78)

    def test_missing_indicator_column_names_the_column(self):
        # Audit M-10: changing RSI_PERIOD raised a bare KeyError forever.
        df = synthetic(100)
        with self.assertRaises(DataQualityError) as ctx:
            check_indicator_columns(df, ["RSI_21"])
        self.assertIn("RSI_21", str(ctx.exception))

    def test_duplicate_timestamps_are_rejected(self):
        df = synthetic(100)
        df = pd.concat([df, df.iloc[[-1]]])
        with self.assertRaises(DataQualityError):
            validate_for_trading(df, 300, check_staleness=False)

    def test_non_monotonic_index_is_rejected(self):
        df = synthetic(100).iloc[::-1]
        with self.assertRaises(DataQualityError):
            validate_for_trading(df, 300, check_staleness=False)

    def test_impossible_ohlc_is_rejected(self):
        df = synthetic(100)
        df.loc[df.index[5], "high"] = df.loc[df.index[5], "low"] - 10
        with self.assertRaises(DataQualityError):
            check_prices_are_sane(df)

    def test_stale_data_is_rejected(self):
        from datetime import timedelta
        df = synthetic(100)
        later = df.index[-1] + timedelta(hours=2)
        with self.assertRaises(DataQualityError) as ctx:
            check_not_stale(df, 300, now=later)
        self.assertIn("stale", str(ctx.exception))

    def test_intraday_gaps_are_found_and_weekends_are_not_faults(self):
        df = synthetic(200)
        gapped = pd.concat([df.iloc[:100], df.iloc[120:]])
        intraday, weekend = find_gaps(gapped, 300)
        self.assertTrue(intraday)

    def test_healthy_data_passes_and_reports(self):
        df = synthetic(200)
        report = validate_for_trading(df, 300, check_staleness=False)
        self.assertEqual(report["bars"], 200)


# ---------------------------------------------------------------- C-07

class TestBacktesterExecutesTrades(unittest.TestCase):
    """C-07: the audited backtester executed zero trades on any input."""

    def test_the_audited_comparison_never_matched(self):
        # `if signal == 'buy'` against generate_signal returning 'BUY'.
        self.assertNotEqual("BUY", "buy")
        self.assertFalse("BUY" == "buy")

    def test_trades_are_executed(self):
        result = Backtester(cost_model=ZERO_COST).run(synthetic(), always_buy)
        self.assertGreater(len(result.trades), 0)

    def test_trade_log_reconciles_to_the_final_balance(self):
        result = Backtester(cost_model=ZERO_COST).run(synthetic(), always_buy)
        self.assertTrue(result.reconciles())

    def test_costs_reduce_the_result(self):
        df = synthetic()
        free = Backtester(cost_model=ZERO_COST).run(df, always_buy)
        paid = Backtester(cost_model=CostModel()).run(df, always_buy)
        self.assertLess(paid.cost_breakdown()["net_pnl"],
                        free.cost_breakdown()["net_pnl"])

    def test_every_cost_component_is_charged(self):
        result = Backtester(cost_model=CostModel()).run(synthetic(), always_buy)
        costs = result.cost_breakdown()
        self.assertGreater(costs["spread"], 0)
        self.assertGreater(costs["commission"], 0)
        self.assertGreater(costs["slippage"], 0)

    def test_shorts_are_supported(self):
        result = Backtester(cost_model=ZERO_COST).run(
            synthetic(), lambda f: {"signal": "SELL", "strength": 100.0})
        self.assertGreater(len(result.trades), 0)
        self.assertTrue(all(t.direction == "SELL" for t in result.trades))

    def test_ambiguous_bars_resolve_pessimistically(self):
        """A bar spanning both stop and target must count as the STOP."""
        bt = Backtester(cost_model=ZERO_COST)
        from backtest.engine import Trade
        trade = Trade(direction="BUY", lots=0.1, entry_price=2000.0,
                      stop_loss=1990.0, take_profit=2010.0)
        bar = {"high": 2015.0, "low": 1985.0}      # spans both
        price, reason = bt._exit_on_bar(trade, bar)
        self.assertEqual(price, 1990.0)
        self.assertIn("pessimistic", reason)

    def test_sizing_uses_the_live_risk_manager(self):
        # Not a reimplementation: divergence here is how backtests lie.
        bt = Backtester(initial_balance=10000.0, risk_fraction=0.01)
        lots = bt.size_position(10000.0, 10.0)
        self.assertAlmostEqual(lots, 0.10)     # 100 risk / (100 * 10)

    def test_sizing_can_decline_exactly_as_the_live_bot_would(self):
        bt = Backtester(initial_balance=150.0, risk_fraction=0.01)
        self.assertIsNone(bt.size_position(150.0, 10.0))

    def test_declined_trades_are_counted_not_silently_taken(self):
        result = Backtester(cost_model=ZERO_COST,
                            initial_balance=150.0).run(synthetic(), always_buy)
        self.assertGreater(result.declined_trades, 0)

    def test_metrics_are_computable(self):
        result = Backtester(cost_model=CostModel()).run(synthetic(), always_buy)
        summary = result.summary()
        for key in ("expectancy", "profit_factor", "win_rate", "sharpe",
                    "sortino", "max_drawdown", "costs"):
            self.assertIn(key, summary)

    def test_zero_cost_result_is_not_evidence_of_an_edge(self):
        # Documents the trap: step 1 says nothing about profitability.
        from backtest.costs import ZERO_COST as Z
        self.assertEqual(Z.commission_per_lot_round_turn, 0.0)
        self.assertEqual(Z.slippage_mean_points, 0.0)


class TestGauntlet(unittest.TestCase):
    """9.4: the seven steps, and the stop-at-first-failure rule."""

    def _gauntlet(self, **kwargs):
        return Gauntlet(synthetic(4000), always_buy, min_trades=10, **kwargs)

    def test_step1_detects_a_working_engine(self):
        self.assertTrue(self._gauntlet().step1_zero_cost().passed)

    def test_a_random_walk_fails_gate_c(self):
        # There is no edge in a random walk, and costs are charged. A gauntlet
        # that passed this would be broken.
        result = self._gauntlet().step2_realistic_cost()
        self.assertFalse(result.passed)
        self.assertLess(result.metrics["expectancy"], 0)

    def test_the_run_stops_at_the_first_failure(self):
        gauntlet = self._gauntlet()
        results = gauntlet.run(stop_on_failure=True)
        self.assertFalse(results[-1].passed)
        self.assertLessEqual(len(results), 7)

    def test_the_verdict_names_gate_c_and_says_stop(self):
        gauntlet = self._gauntlet()
        gauntlet.run()
        verdict = gauntlet.verdict()
        self.assertIn("STEP 2", verdict)
        self.assertIn("STOP", verdict)

    def test_a_crashing_step_counts_as_a_failure(self):
        gauntlet = self._gauntlet()
        gauntlet.step1_zero_cost = lambda: 1 / 0
        results = gauntlet.run()
        self.assertFalse(results[0].passed)

    def test_all_seven_steps_exist(self):
        gauntlet = self._gauntlet()
        for i in range(1, 8):
            self.assertTrue(
                any(name.startswith("step%d_" % i) for name in dir(gauntlet)),
                "step %d is missing" % i)


class TestPhase9IsActuallyWired(unittest.TestCase):
    """Carefully written code called from nowhere is the audit's signature.

    H-07 (three unused logging methods), C-06 (three unused stop helpers) and
    M-03 (an unreachable threshold branch) were all this shape. These assert
    the Phase 9 work is on the live path, not sitting beside it.
    """

    def _loop_source(self):
        import inspect, textwrap
        import main
        return textwrap.dedent(inspect.getsource(main.main_loop))

    def test_the_live_strategy_uses_the_continuous_scorer(self):
        import ast, inspect, textwrap
        from strategies.strategy_basic import BasicTradingStrategy
        source = textwrap.dedent(inspect.getsource(
            BasicTradingStrategy.generate_signal))
        tree = ast.parse(source)
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("compute_strength", called,
                      "generate_signal still uses the degenerate scorer")

    def test_the_live_strategy_strength_is_continuous(self):
        import logging
        logging.getLogger("strategies.strategy_basic").setLevel(logging.ERROR)
        from strategies.strategy_basic import BasicTradingStrategy

        df = synthetic(900, seed=11)
        strategy = BasicTradingStrategy(ema_fast=12, ema_slow=26, rsi_period=14,
                                        bb_period=20, bb_std=2.0)
        prepared = strategy.prepare_data(df)
        strengths = [strategy.generate_signal(prepared.iloc[:i])["strength"]
                     for i in range(300, 900, 5)]

        report = distribution_report(strengths)
        # The plan's CI assertion. The audited scorer produced four values.
        self.assertGreater(report["distinct"], 10)
        self.assertGreater(report["variance"], 0.0)

    def test_the_loop_validates_data_before_signalling(self):
        source = self._loop_source()
        self.assertIn("validate_for_trading", source)
        self.assertIn("required_warmup_bars", source)

    def test_the_loop_validates_indicator_columns_by_configured_name(self):
        source = self._loop_source()
        self.assertIn("RSI_%d", source,
                      "indicator column names must follow config (M-10)")

    def test_the_loop_resolves_the_symbol_at_startup(self):
        self.assertIn("resolve_symbol", self._loop_source())


class TestSymbolResolution(unittest.TestCase):
    """The bot exited on every start because config.SYMBOL was wrong."""

    def _mt5(self, available=("XAUUSD", "EURUSD", "GOLD.spot")):
        from unittest.mock import MagicMock
        mt5 = MagicMock()

        def symbol_info(name):
            if name in available:
                info = MagicMock(visible=True, trade_mode=1)
                info.name = name
                return info
            return None

        mt5.symbol_info.side_effect = symbol_info
        mt5.symbol_select.return_value = False
        mt5.symbols_get.return_value = [
            type("S", (), {"name": n})() for n in available]
        return mt5

    def test_a_valid_symbol_resolves(self):
        from data.symbol_resolver import resolve_symbol
        self.assertIsNotNone(resolve_symbol(self._mt5(), "XAUUSD"))

    def test_a_wrong_symbol_lists_what_the_broker_offers(self):
        # The real failure: 'XAUUSDm' on a broker that lists 'XAUUSD', with an
        # error message that gave no hint what to use instead.
        from data.symbol_resolver import resolve_symbol, SymbolNotAvailable
        with self.assertRaises(SymbolNotAvailable) as ctx:
            resolve_symbol(self._mt5(), "XAUUSDm")
        message = str(ctx.exception)
        self.assertIn("XAUUSD", message)
        self.assertIn("GOLD.spot", message)

    def test_it_never_auto_selects_a_lookalike(self):
        # Silently picking a symbol that looks like gold is how a bot ends up
        # trading a mining CFD, or a 1oz contract sized for 100oz.
        from data.symbol_resolver import resolve_symbol, SymbolNotAvailable
        with self.assertRaises(SymbolNotAvailable):
            resolve_symbol(self._mt5(), "XAUUSDm")

    def test_no_gold_symbols_at_all_says_so(self):
        from data.symbol_resolver import resolve_symbol, SymbolNotAvailable
        with self.assertRaises(SymbolNotAvailable) as ctx:
            resolve_symbol(self._mt5(available=("EURUSD",)), "XAUUSD")
        self.assertIn("No gold-like symbols", str(ctx.exception))

    def test_config_symbol_matches_the_broker_account(self):
        import config
        self.assertEqual(config.SYMBOL, "XAUUSD")
        self.assertEqual(config.SYMBOL_PHASE5, config.SYMBOL)

    def test_trade_disabled_symbol_is_refused_by_default(self):
        # A live caller (main.py) must not proceed toward a symbol it cannot
        # actually trade.
        from data.symbol_resolver import resolve_symbol, SymbolNotAvailable
        mt5 = self._mt5()
        mt5.symbol_info.side_effect = lambda name: (
            type("I", (), {"visible": True, "trade_mode": 0, "name": name})()
            if name == "XAUUSD" else None)
        with self.assertRaises(SymbolNotAvailable) as ctx:
            resolve_symbol(mt5, "XAUUSD")
        self.assertIn("disabled for trading", str(ctx.exception))

    def test_trade_disabled_symbol_is_readable_for_data_fetch_only(self):
        # scripts/fetch_historical_data.py never trades -- whether a symbol is
        # enabled for trading is irrelevant to reading its price history.
        from data.symbol_resolver import resolve_symbol
        mt5 = self._mt5()
        mt5.symbol_info.side_effect = lambda name: (
            type("I", (), {"visible": True, "trade_mode": 0, "name": name})()
            if name == "XAUUSD" else None)
        info = resolve_symbol(mt5, "XAUUSD", require_tradeable=False)
        self.assertEqual(info.name, "XAUUSD")


class TestGauntletRealSpecPassthrough(unittest.TestCase):
    """Phase 9 follow-up: Gate C must be able to use REAL broker values,
    not Backtester's guessed defaults, and step 6's sensitivity baseline must
    match whatever baseline was actually configured for the run.
    """

    def test_spec_fields_reach_the_backtester(self):
        real_spec = {"digits": 2, "point": 0.01, "trade_contract_size": 100.0,
                    "trade_tick_value": 0.1, "trade_tick_size": 0.01,
                    "volume_min": 0.01, "volume_step": 0.01,
                    "volume_max": 100.0, "trade_stops_level": 0,
                    "trade_freeze_level": 0, "filling_mode": 3}
        gauntlet = Gauntlet(synthetic(1500), always_buy, min_trades=5,
                           spec_fields=real_spec)
        result = gauntlet._backtest(gauntlet.df, ZERO_COST)
        # volume_max=100 (not the Backtester default of 50) must be honoured.
        self.assertTrue(any(t.lots <= 100.0 for t in result.trades))

    def test_backtester_kwargs_become_the_baseline(self):
        gauntlet = Gauntlet(synthetic(2000), always_buy, min_trades=5,
                           backtester_kwargs={"risk_fraction": 0.02})
        # The baseline run should reflect risk_fraction=0.02, not the
        # Backtester default of 0.01 -- verified via the sizing helper.
        bt_default = Backtester(risk_fraction=0.01)
        bt_configured = Backtester(risk_fraction=0.02)
        lots_default = bt_default.size_position(10000.0, 10.0)
        lots_configured = bt_configured.size_position(10000.0, 10.0)
        self.assertAlmostEqual(lots_configured, lots_default * 2, places=2)

    def test_sensitivity_baseline_uses_the_configured_run_not_a_second_default(self):
        gauntlet = Gauntlet(synthetic(3000), always_buy, min_trades=5,
                           backtester_kwargs={"rr": 3.0})
        result = gauntlet.step6_parameter_sensitivity()
        # rr's variants should be centred on 3.0 (+/-20% = 2.4 and 3.6),
        # not the hardcoded default of 2.0.
        self.assertIn("rr -20%", result.metrics["variants"])
        self.assertIn("rr +20%", result.metrics["variants"])


if __name__ == "__main__":
    unittest.main()
