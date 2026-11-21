"""Gauntlet in live-rules mode: factory, caching, sensitivity over config keys."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.costs import CostModel
from backtest.gauntlet import Gauntlet


def trade(pnl, when, session="London"):
    return SimpleNamespace(net_pnl=pnl, entry_time=when, session=session)


class StubResult:
    def __init__(self, pnls, start):
        self.trades = [trade(p, start + timedelta(days=i),
                             "Asian" if i % 2 else "London") for i, p in enumerate(pnls)]
        self.net_pnls = list(pnls)

    def expectancy(self):
        return sum(self.net_pnls) / len(self.net_pnls) if self.net_pnls else 0.0

    def reconciles(self):
        return True

    def profit_factor(self):
        return 1.5

    def cost_breakdown(self):
        return {"total_costs": 1.0, "gross_pnl": 2.0}


class StubBacktester:
    runs = []

    def __init__(self, costs, overrides, pnls):
        self.overrides, self.pnls = overrides, pnls

    def run(self, df):
        StubBacktester.runs.append((len(df), dict(self.overrides)))
        return StubResult(self.pnls, df.index[0].to_pydatetime())


class TestGauntletLiveMode(unittest.TestCase):
    def setUp(self):
        StubBacktester.runs = []
        self.df = pd.DataFrame({"close": range(800)},
                               index=pd.date_range("2025-01-01", periods=800, freq="h", tz="UTC"))

    def gauntlet(self, pnls):
        costs = CostModel()
        return Gauntlet(self.df, None, None, cost_model=costs, min_trades=5,
                        backtester_factory=lambda c, o: StubBacktester(c, o, pnls),
                        sensitivity_parameters={"MIN_ENTRY_STRENGTH": 65.0})

    def test_all_steps_run_and_pass_on_a_consistent_edge(self):
        g = self.gauntlet([2.0, -1.0] * 20)
        results = g.run(stop_on_failure=False)
        self.assertEqual(len(results), 7)
        self.assertTrue(all(r.passed for r in results[:6]), [str(r) for r in results])
        self.assertIn("MIN_ENTRY_STRENGTH -20%", results[5].metrics["variants"])

    def test_full_run_is_cached(self):
        g = self.gauntlet([2.0, -1.0] * 20)
        g.run(stop_on_failure=False)
        full_runs = [r for r in StubBacktester.runs if r[0] == len(self.df) and not r[1]]
        # Step 1 uses ZERO_COST (a different cost model), so exactly two full,
        # un-overridden runs happen: zero-cost and the cached realistic one.
        self.assertEqual(len(full_runs), 2)

    def test_sensitivity_overrides_reach_the_factory(self):
        g = self.gauntlet([2.0, -1.0] * 20)
        g.step6_parameter_sensitivity()
        values = sorted(r[1]["MIN_ENTRY_STRENGTH"] for r in StubBacktester.runs if r[1])
        self.assertEqual(values, [52.0, 78.0])

    def test_losing_edge_stops_at_gate_c(self):
        g = self.gauntlet([-1.0] * 40)
        results = g.run()
        self.assertEqual(results[-1].number, 2)
        self.assertIn("Gate C", g.verdict())

    def test_regime_split_uses_trade_sessions(self):
        g = self.gauntlet([5.0, -1.0] * 20)
        step = g.step7_regime_split()
        self.assertEqual(set(step.metrics["by_session"]), {"London", "Asian"})


if __name__ == "__main__":
    unittest.main()
