"""Trading costs (Phase 9.2).

The audited backtester modelled **no costs at all**. On a high-churn M5 strategy
that is not a small inaccuracy -- it is the difference between the answer and
its opposite. Gold's spread alone is frequently larger than the move the
strategy is trying to capture, and it is paid on every single round trip.

Everything here is deliberately explicit and configurable, because the honest
answer to "is this profitable?" is extremely sensitive to these numbers, and a
reader must be able to see exactly what was assumed.
"""

import random
from dataclasses import dataclass, field


# Spread in POINTS by session, for XAUUSD. These are typical retail figures,
# not measurements from your broker: calibrate them from the spread the live
# bot now logs on every entry decision (Phase 2.4) before trusting any result.
DEFAULT_SESSION_SPREAD_POINTS = {
    "Asian": 45.0,              # thin book, wide quotes
    "London": 25.0,
    "London/NY overlap": 18.0,  # tightest
    "New York": 25.0,
    "Other": 50.0,              # rollover, pre-open
}


@dataclass
class CostModel:
    """Spread, commission, swap and slippage.

    Attributes:
        session_spread_points: spread by session name, in points.
        commission_per_lot_round_turn: account-currency cost per lot, both ways.
        swap_long_points / swap_short_points: per lot per night, in points.
        slippage_mean_points / slippage_sd_points: execution slippage, modelled
            as a distribution rather than zero. Assuming zero slippage flatters
            every strategy, and flatters high-frequency ones most.
        latency_bars: bars between the decision and the fill. The audited model
            filled at the decision bar's close, which is not obtainable.
    """

    session_spread_points: dict = field(
        default_factory=lambda: dict(DEFAULT_SESSION_SPREAD_POINTS))
    commission_per_lot_round_turn: float = 7.0
    swap_long_points: float = -12.0
    swap_short_points: float = -6.0
    slippage_mean_points: float = 2.0
    slippage_sd_points: float = 3.0
    latency_bars: int = 1
    point: float = 0.01
    contract_size: float = 100.0

    def spread_price(self, session):
        """Spread for a session, in price units."""
        points = self.session_spread_points.get(
            session, self.session_spread_points.get("Other", 50.0))
        return points * self.point

    def half_spread_price(self, session):
        return self.spread_price(session) / 2.0

    def commission(self, lots):
        return abs(float(lots)) * self.commission_per_lot_round_turn

    def swap(self, lots, nights, is_long):
        """Overnight financing. Negative is a cost."""
        if nights <= 0:
            return 0.0
        points = self.swap_long_points if is_long else self.swap_short_points
        return points * self.point * self.contract_size * abs(float(lots)) * nights

    def slippage_price(self, rng=None):
        """A slippage draw, in price units. Always adverse."""
        rng = rng or random
        points = rng.gauss(self.slippage_mean_points, self.slippage_sd_points)
        return max(0.0, points) * self.point

    def describe(self):
        return {
            "session_spread_points": dict(self.session_spread_points),
            "commission_per_lot_round_turn": self.commission_per_lot_round_turn,
            "swap_long_points": self.swap_long_points,
            "swap_short_points": self.swap_short_points,
            "slippage_mean_points": self.slippage_mean_points,
            "slippage_sd_points": self.slippage_sd_points,
            "latency_bars": self.latency_bars,
        }

    def zero_cost_variant(self):
        """A copy with every cost zeroed, but THIS instrument's point/contract_size kept.

        Phase 12 follow-up (found while backtesting a second symbol, US500):
        the module-level ``ZERO_COST`` constant below hardcodes gold's
        ``point=0.01, contract_size=100.0`` defaults. Gate C's step 1 used it
        regardless of which symbol was under test, so on US500 (real
        contract_size=1.0) sizing divided risk by a contract size 100x too
        large, rounded almost every trade below the broker's minimum lot, and
        step 1 saw 3 trades over 14 years instead of hundreds -- invisible on
        gold, where the hardcoded defaults happened to already match. Gate C
        now builds its zero-cost run from the REAL cost model via this method
        instead of the shared constant.
        """
        return CostModel(
            session_spread_points={k: 0.0 for k in self.session_spread_points},
            commission_per_lot_round_turn=0.0, swap_long_points=0.0,
            swap_short_points=0.0, slippage_mean_points=0.0,
            slippage_sd_points=0.0, latency_bars=0,
            point=self.point, contract_size=self.contract_size,
        )


# Deprecated: hardcodes gold's point/contract_size. Kept only because existing
# tests reference it directly with gold-shaped data, where it is still
# correct. New code should call ``cost_model.zero_cost_variant()`` instead,
# which carries the real instrument's point/contract_size forward.
ZERO_COST = CostModel(
    session_spread_points={k: 0.0 for k in DEFAULT_SESSION_SPREAD_POINTS},
    commission_per_lot_round_turn=0.0,
    swap_long_points=0.0,
    swap_short_points=0.0,
    slippage_mean_points=0.0,
    slippage_sd_points=0.0,
    latency_bars=0,
)
"""A frictionless model, for gauntlet step 1 ONLY.

Step 1 asks whether the machinery executes trades and the arithmetic
reconciles. It says nothing whatever about profitability, and a positive
zero-cost result is not evidence of an edge -- that is what step 2 is for.
"""
