"""The validation gauntlet (Phase 9.4).

Seven steps, run in order, **stopping at the first failure**. Step 2 is Gate C:
if expectancy after realistic costs is not positive, the plan says stop, and
stopping is a legitimate and valuable outcome.

Steps 3-7 exist because step 2 passing is weak evidence. A strategy tuned until
it works on the data you tuned it on will pass step 2 by construction. Out-of-
sample, walk-forward, Monte Carlo, sensitivity and regime analysis are what
separate an edge from a curve fit, and the plan is explicit that they must not
be skipped just because step 2 passed.

**This module cannot tell you whether your strategy works.** It can only run
the tests honestly against data you supply. Gate C needs 2+ years of real M5
gold data from the broker; against synthetic data it verifies the machinery,
nothing more.
"""

import logging
import math
import random
from dataclasses import dataclass, field

from .costs import CostModel
from .engine import Backtester

logger = logging.getLogger("xau_bot")


@dataclass
class StepResult:
    number: int
    name: str
    passed: bool
    detail: str = ""
    metrics: dict = field(default_factory=dict)

    def __str__(self):
        return "Step %d (%s): %s -- %s" % (
            self.number, self.name, "PASS" if self.passed else "FAIL", self.detail)


class Gauntlet:
    """Runs the seven validation steps in order."""

    def __init__(self, df, signal_fn, session_fn=None, initial_balance=1000.0,
                 cost_model=None, min_trades=30, seed=42, spec_fields=None,
                 backtester_kwargs=None, backtester_factory=None,
                 sensitivity_parameters=None):
        self.df = df
        self.signal_fn = signal_fn
        self.session_fn = session_fn
        self.initial_balance = initial_balance
        self.cost_model = cost_model or CostModel()
        self.min_trades = min_trades
        self.rng = random.Random(seed)
        self.results = []
        # Real broker-reported contract spec (Phase 9 follow-up), so sizing
        # uses actual values rather than Backtester's guessed defaults. Also
        # the baseline for step 6's parameter-sensitivity variants, so "+/-20%"
        # is relative to what was actually run, not a second, silently
        # different default.
        self.spec_fields = spec_fields
        self.backtester_kwargs = dict(backtester_kwargs or {})
        # Live-rules mode: ``backtester_factory(cost_model, overrides)`` builds
        # a backtester running the live bot's rules; step 6 then varies the
        # live config values in ``sensitivity_parameters``.
        self.backtester_factory = backtester_factory
        self.sensitivity_parameters = sensitivity_parameters
        self.last_full_result = None

    def _backtest(self, df, costs, **kwargs):
        if self.backtester_factory is not None:
            # The full-data realistic-cost run is deterministic (seeded) and
            # steps 2, 5, 6 and 7 all need it: run it once.
            full = df is self.df and costs is self.cost_model and not kwargs
            if full and self.last_full_result is not None:
                return self.last_full_result
            result = self.backtester_factory(costs, kwargs).run(df)
            if full:
                self.last_full_result = result
            return result
        merged = dict(self.backtester_kwargs)
        merged.update(kwargs)
        if self.spec_fields:
            merged.setdefault("spec_fields", self.spec_fields)
        return Backtester(cost_model=costs, initial_balance=self.initial_balance,
                          **merged).run(df, self.signal_fn, self.session_fn)

    # ------------------------------------------------------------- step 1

    def step1_zero_cost(self):
        """Non-zero trades, and the trade log reconciles to the final balance.

        This is the C-07 regression: the audited backtester executed zero
        trades on any input and reported 0.00%.

        Zero-cost, but built from THIS run's real cost model (point,
        contract_size) via ``zero_cost_variant()`` -- not the shared
        ``ZERO_COST`` constant, which hardcodes gold's contract_size and
        silently mis-sized every trade on a symbol whose contract size
        differs (found testing US500: contract_size 1.0 vs gold's 100.0).
        """
        result = self._backtest(self.df, self.cost_model.zero_cost_variant())
        trades = len(result.trades)
        reconciles = result.reconciles()
        passed = trades >= self.min_trades and reconciles
        detail = ("%d trades (need >= %d), reconciles=%s"
                  % (trades, self.min_trades, reconciles))
        return StepResult(1, "zero-cost sanity", passed, detail,
                          {"trades": trades, "reconciles": reconciles,
                           "expectancy": result.expectancy()})

    # ------------------------------------------------------------- step 2

    def step2_realistic_cost(self):
        """**Gate C.** Positive expectancy after spread, commission, swap, slippage."""
        result = self._backtest(self.df, self.cost_model)
        expectancy = result.expectancy()
        costs = result.cost_breakdown()
        passed = len(result.trades) >= self.min_trades and expectancy > 0
        detail = ("expectancy %.4f per trade over %d trades; costs %.2f vs "
                  "gross %.2f" % (expectancy, len(result.trades),
                                  costs["total_costs"], costs["gross_pnl"]))
        return StepResult(2, "realistic-cost expectancy", passed, detail,
                          {"expectancy": expectancy,
                           "trades": len(result.trades),
                           "profit_factor": result.profit_factor(),
                           "costs": costs})

    # ------------------------------------------------------------- step 3

    def step3_out_of_sample(self, holdout=0.3, tolerance=0.5):
        """Out-of-sample expectancy within a stated fraction of in-sample."""
        split = int(len(self.df) * (1 - holdout))
        in_sample = self._backtest(self.df.iloc[:split], self.cost_model)
        out_sample = self._backtest(self.df.iloc[split:], self.cost_model)

        ins, oos = in_sample.expectancy(), out_sample.expectancy()
        if ins <= 0:
            return StepResult(3, "out-of-sample", False,
                              "in-sample expectancy is %.4f -- nothing to "
                              "validate against" % ins,
                              {"in_sample": ins, "out_of_sample": oos})

        ratio = oos / ins
        passed = oos > 0 and ratio >= tolerance
        detail = ("in-sample %.4f, out-of-sample %.4f (ratio %.2f, need >= %.2f)"
                  % (ins, oos, ratio, tolerance))
        return StepResult(3, "out-of-sample", passed, detail,
                          {"in_sample": ins, "out_of_sample": oos, "ratio": ratio})

    # ------------------------------------------------------------- step 4

    def step4_walk_forward(self, windows=4):
        """Consistent SIGN of expectancy across rolling windows.

        Sign, not magnitude. A strategy that makes money in three windows and
        loses it in the fourth does not have an edge that survives regime
        change -- it has an edge in three regimes.
        """
        size = len(self.df) // windows
        expectancies = []
        for i in range(windows):
            chunk = self.df.iloc[i * size:(i + 1) * size]
            if len(chunk) < 100:
                continue
            expectancies.append(self._backtest(chunk, self.cost_model).expectancy())

        if not expectancies:
            return StepResult(4, "walk-forward", False, "no usable windows", {})

        positive = sum(1 for e in expectancies if e > 0)
        passed = positive == len(expectancies)
        detail = ("%d of %d windows positive: %s"
                  % (positive, len(expectancies),
                     ", ".join("%.4f" % e for e in expectancies)))
        return StepResult(4, "walk-forward", passed, detail,
                          {"expectancies": expectancies})

    # ------------------------------------------------------------- step 5

    def step5_monte_carlo(self, iterations=1000, percentile=95,
                          max_drawdown_fraction=0.30):
        """Bootstrap the trade SEQUENCE and check the 95th-percentile drawdown.

        The realised order of trades is one sample from many possible orders.
        Reshuffling asks: how bad would the drawdown have been if the losers
        had clustered differently? They will, eventually.
        """
        result = self._backtest(self.df, self.cost_model)
        pnls = result.net_pnls
        if len(pnls) < self.min_trades:
            return StepResult(5, "Monte Carlo", False,
                              "only %d trades" % len(pnls), {})

        drawdowns = []
        for _ in range(iterations):
            shuffled = self.rng.sample(pnls, len(pnls))
            equity, peak, worst = self.initial_balance, self.initial_balance, 0.0
            for pnl in shuffled:
                equity += pnl
                peak = max(peak, equity)
                if peak > 0:
                    worst = max(worst, (peak - equity) / peak)
            drawdowns.append(worst)

        drawdowns.sort()
        index = min(len(drawdowns) - 1,
                    int(len(drawdowns) * percentile / 100.0))
        p_drawdown = drawdowns[index]
        passed = p_drawdown <= max_drawdown_fraction
        detail = ("%dth-percentile drawdown %.1f%% (limit %.1f%%)"
                  % (percentile, p_drawdown * 100, max_drawdown_fraction * 100))
        return StepResult(5, "Monte Carlo", passed, detail,
                          {"p%d_drawdown" % percentile: p_drawdown,
                           "median_drawdown": drawdowns[len(drawdowns) // 2]})

    # ------------------------------------------------------------- step 6

    def step6_parameter_sensitivity(self, parameters=None, delta=0.2):
        """No parameter whose +/-20% change flips the sign of expectancy.

        A cliff means the result is an artefact of that exact value. Real edges
        are broad; curve fits are sharp.
        """
        # Defaults, overridden by whatever baseline was actually configured
        # for this run, so "+/-20%" is relative to the real baseline rather
        # than a second, silently different one.
        defaults = {"sl_atr_multiple": 2.0, "rr": 2.0, "risk_fraction": 0.01}
        defaults.update({k: v for k, v in self.backtester_kwargs.items()
                         if k in defaults})
        parameters = parameters or self.sensitivity_parameters or defaults
        baseline = self._backtest(self.df, self.cost_model).expectancy()
        flips, table = [], {}

        for name, value in parameters.items():
            for direction, factor in (("-20%", 1 - delta), ("+20%", 1 + delta)):
                kwargs = {name: value * factor}
                try:
                    expectancy = self._backtest(self.df, self.cost_model,
                                                **kwargs).expectancy()
                except TypeError:
                    continue
                table["%s %s" % (name, direction)] = expectancy
                if baseline != 0 and (expectancy > 0) != (baseline > 0):
                    flips.append("%s %s" % (name, direction))

        passed = not flips
        detail = ("baseline %.4f; sign flips: %s"
                  % (baseline, ", ".join(flips) if flips else "none"))
        return StepResult(6, "parameter sensitivity", passed, detail,
                          {"baseline": baseline, "variants": table,
                           "flips": flips})

    # ------------------------------------------------------------- step 7

    def step7_regime_split(self, max_share=0.6):
        """No single regime may carry most of the profit.

        If one session or one year supplies everything, the strategy is that
        regime's artefact -- and the regime will end.
        """
        result = self._backtest(self.df, self.cost_model)
        if not result.trades:
            return StepResult(7, "regime split", False, "no trades", {})

        by_session, by_year = {}, {}
        for trade in result.trades:
            session = (getattr(trade, "session", None)
                       or (self.session_fn(trade.entry_time) if self.session_fn else "all"))
            by_session[session] = by_session.get(session, 0.0) + trade.net_pnl
            try:
                year = trade.entry_time.year
            except AttributeError:
                year = "unknown"
            by_year[year] = by_year.get(year, 0.0) + trade.net_pnl

        total_profit = sum(v for v in by_session.values() if v > 0)
        worst = None
        if total_profit > 0:
            for name, pnl in by_session.items():
                if pnl > 0 and pnl / total_profit > max_share:
                    worst = (name, pnl / total_profit)

        passed = worst is None
        detail = ("profit by session: %s"
                  % ", ".join("%s %.2f" % kv for kv in sorted(by_session.items())))
        if worst:
            detail += " -- %s carries %.0f%% of gross profit" % (worst[0],
                                                                 worst[1] * 100)
        return StepResult(7, "regime split", passed, detail,
                          {"by_session": by_session, "by_year": by_year})

    # ---------------------------------------------------------------- run

    def run(self, stop_on_failure=True):
        """Run every step in order. Returns the list of StepResults."""
        steps = [self.step1_zero_cost, self.step2_realistic_cost,
                 self.step3_out_of_sample, self.step4_walk_forward,
                 self.step5_monte_carlo, self.step6_parameter_sensitivity,
                 self.step7_regime_split]

        self.results = []
        for step in steps:
            try:
                outcome = step()
            except Exception as exc:          # a crashing step is a failing step
                outcome = StepResult(len(self.results) + 1, step.__name__,
                                     False, "raised %s: %s"
                                     % (type(exc).__name__, exc))
            self.results.append(outcome)
            logger.info("%s", outcome)

            if not outcome.passed and stop_on_failure:
                logger.warning("Gauntlet stopped at step %d. Later steps are "
                               "not run: they would be measuring a strategy "
                               "that has already failed.", outcome.number)
                break
        return self.results

    def verdict(self):
        """A short human summary, including the Gate C decision."""
        if not self.results:
            return "not run"
        failed = [r for r in self.results if not r.passed]
        if not failed:
            return "ALL %d STEPS PASSED" % len(self.results)

        first = failed[0]
        if first.number == 2:
            return ("FAILED AT STEP 2 (Gate C): %s. The plan's guidance is to "
                    "STOP -- do not proceed to demo or live. Options: a "
                    "different hypothesis, a higher timeframe where the spread "
                    "is a smaller fraction of the expected move, or conclude "
                    "there is no edge. The last is a legitimate outcome."
                    % first.detail)
        return "FAILED AT STEP %d (%s): %s" % (first.number, first.name,
                                               first.detail)
