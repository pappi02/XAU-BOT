"""Gate C step 1 must size against the REAL instrument's contract_size.

Found testing a second symbol (US500, contract_size 1.0): the shared
``ZERO_COST`` constant hardcodes gold's contract_size (100.0), so step 1 sized
every trade as if 100 units per lot when the real instrument was 1 -- 100x too
few lots per unit of risk, rounding almost everything below the broker's
minimum. Invisible on gold, where the hardcoded default happened to already
match.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.costs import ZERO_COST, CostModel


class TestZeroCostVariant(unittest.TestCase):
    def test_carries_the_real_point_and_contract_size(self):
        us500 = CostModel(point=0.01, contract_size=1.0)
        variant = us500.zero_cost_variant()
        self.assertEqual(variant.contract_size, 1.0)
        self.assertEqual(variant.point, 0.01)

    def test_every_cost_is_zeroed(self):
        variant = CostModel(commission_per_lot_round_turn=7.0).zero_cost_variant()
        self.assertEqual(variant.commission_per_lot_round_turn, 0.0)
        self.assertEqual(variant.swap_long_points, 0.0)
        self.assertEqual(variant.swap_short_points, 0.0)
        self.assertEqual(variant.slippage_mean_points, 0.0)
        self.assertEqual(variant.slippage_sd_points, 0.0)
        self.assertEqual(variant.latency_bars, 0)
        self.assertTrue(all(v == 0.0 for v in variant.session_spread_points.values()))

    def test_gold_shaped_model_matches_the_legacy_constant(self):
        gold_zero = CostModel().zero_cost_variant()      # gold's own defaults
        self.assertEqual(gold_zero.contract_size, ZERO_COST.contract_size)
        self.assertEqual(gold_zero.point, ZERO_COST.point)

    def test_gauntlet_step1_sizes_against_the_real_contract_size(self):
        # Integration: a non-gold contract_size must not starve step 1 of
        # trades the way it did before this fix.
        from backtest.gauntlet import Gauntlet

        class StubResult:
            trades = [object()] * 50
            net_pnls = [1.0] * 50

            def reconciles(self):
                return True

            def expectancy(self):
                return 1.0

        seen_contract_sizes = []

        class StubBacktester:
            def __init__(self, costs, overrides):
                seen_contract_sizes.append(costs.contract_size)

            def run(self, df):
                return StubResult()

        import pandas as pd
        df = pd.DataFrame({"close": range(10)},
                          index=pd.date_range("2025-01-01", periods=10, freq="h", tz="UTC"))
        gauntlet = Gauntlet(df, None, None, cost_model=CostModel(contract_size=1.0),
                            backtester_factory=lambda c, o: StubBacktester(c, o))
        gauntlet.step1_zero_cost()
        self.assertEqual(seen_contract_sizes, [1.0])


if __name__ == "__main__":
    unittest.main()
