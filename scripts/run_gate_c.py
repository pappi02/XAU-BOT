"""Run the Phase 9.4 validation gauntlet against real historical data.

100% OFFLINE. Reads data/historical/XAUUSD_M5.csv and _spec.json, saved by
scripts/fetch_historical_data.py. Makes no broker connection at all.

The cost model is calibrated from what is actually in the data:

  * Spread by session -- the mean of the real per-bar 'spread' column
    (broker points), bucketed into the same session boundaries Phase 5.6
    fixed (the London/NY overlap counted separately, not folded into NY).
  * Swap long/short -- read from the real symbol spec captured at fetch time.
  * Commission and slippage remain the CostModel module's documented retail
    assumptions: this demo account's raw feed does not expose either, so
    they are flagged as unverified rather than presented as measured.

**Caveat that matters more than any number below:** demo-account spreads are
frequently tighter than the live equivalent -- some brokers use it as a
selling point. Measured 9-10 points here is materially better than the
15-50 points assumed as a generic placeholder in Phase 2's config comments.
Whatever Gate C says, re-verify the spread assumption against a live account
statement before trusting the verdict at live size.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config
from backtest.costs import CostModel
from backtest.gauntlet import Gauntlet
from backtest.live_engine import LiveRulesBacktester, prepare_frame
from backtest.report import format_report, performance_report, save_report, trade_records
from utils.economic_calendar import EconomicCalendar
from utils.market_time import BrokerClock, market_session
from data.quality import DataQualityError, required_warmup_bars, validate_for_trading
from strategies.strategy_basic import BasicTradingStrategy
from strategies.strategy_breakout import BreakoutStrategy
from strategies.strategy_trend import TrendFollowingStrategy
from strategies.trade_plan import plan_trend_entry
from execution.bar_gate import timeframe_seconds

# Timeframe, symbol and strategy can each be overridden (e.g.
# `--symbol US500 --timeframe H1 --strategy trend`) to test a mechanism
# against different data. Needs data already fetched for that symbol/
# timeframe (see scripts/fetch_historical_data.py --symbol --timeframe).
TIMEFRAME = (sys.argv[sys.argv.index("--timeframe") + 1]
            if "--timeframe" in sys.argv else config.TIMEFRAME).upper()
BAR_SECONDS = timeframe_seconds(TIMEFRAME)
SYMBOL = (sys.argv[sys.argv.index("--symbol") + 1]
         if "--symbol" in sys.argv else config.SYMBOL).upper()

# Strategy can be overridden (e.g. `--strategy breakout`) to test a different
# hypothesis (docs/STRATEGY-HYPOTHESIS.md) against the same data, costs, entry
# gates, sizing and exits. Default is Hypothesis 1, the live bot's strategy.
STRATEGY_NAME = (sys.argv[sys.argv.index("--strategy") + 1]
                 if "--strategy" in sys.argv else "basic").lower()

REPORT_SUFFIX = "-%s" % SYMBOL.lower() if SYMBOL != config.SYMBOL.upper() else ""
REPORT_SUFFIX += "-%s" % TIMEFRAME.lower() if TIMEFRAME != config.TIMEFRAME.upper() else ""
REPORT_SUFFIX += "-%s" % STRATEGY_NAME if STRATEGY_NAME != "basic" else ""

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "historical", "%s_%s.csv"
                         % (SYMBOL, TIMEFRAME))
SPEC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "historical", "%s_spec.json" % SYMBOL)


def session_of(timestamp):
    """DST-aware session of a UTC bar time (same function the live bot uses)."""
    return market_session(timestamp)


def build_cost_model(df, spec):
    """Spread measured from the data; swap from the real spec; the rest documented defaults."""
    sessions = pd.Series([session_of(t) for t in df.index], index=df.index)
    measured = df.groupby(sessions)["spread"].mean().to_dict()

    print("Measured mean spread by session (broker points):")
    for name, value in sorted(measured.items()):
        print("   %-20s %6.2f" % (name, value))

    model = CostModel()
    for name in list(model.session_spread_points):
        if name in measured:
            model.session_spread_points[name] = float(measured[name])
        else:
            print("   %-20s no bars in this session in the data -- keeping "
                  "the generic default %.1f" % (name, model.session_spread_points[name]))

    if spec.get("swap_long") is not None:
        model.swap_long_points = float(spec["swap_long"])
    if spec.get("swap_short") is not None:
        model.swap_short_points = float(spec["swap_short"])
    model.point = float(spec.get("point", model.point))
    model.contract_size = float(spec.get("trade_contract_size", model.contract_size))

    print("\nCommission %.2f/lot round-turn and slippage (mean %.1f, sd %.1f "
          "points) are UNVERIFIED defaults -- this feed does not expose them."
          % (model.commission_per_lot_round_turn, model.slippage_mean_points,
             model.slippage_sd_points))
    return model


SENSITIVITY_PARAMETERS = {
    "MIN_ENTRY_STRENGTH": config.MIN_ENTRY_STRENGTH,
    "EXIT_REVERSAL_MIN_STRENGTH": config.EXIT_REVERSAL_MIN_STRENGTH,
    "ATR_SPIKE_MULTIPLIER": config.ATR_SPIKE_MULTIPLIER,
    "MAX_POSITION_AGE_SECONDS": config.MAX_POSITION_AGE_SECONDS,
    "RISK_PER_TRADE_FRACTION": config.RISK_PER_TRADE_FRACTION,
}

# Hypothesis 3's meaningful knobs are different (the exit factors ATR_SPIKE_
# MULTIPLIER/EXIT_REVERSAL_MIN_STRENGTH govern are switched off, and
# MAX_POSITION_AGE_SECONDS is overridden to 90 days -- varying it +/-20%
# around the vanilla 24h default would reintroduce a short time exit for that
# one sensitivity run and silently retest something else).
TREND_SENSITIVITY_PARAMETERS = {
    "MIN_ENTRY_STRENGTH": config.MIN_ENTRY_STRENGTH,
    "RISK_PER_TRADE_FRACTION": config.RISK_PER_TRADE_FRACTION,
    "TREND_INITIAL_SL_ATR_MULT": config.TREND_INITIAL_SL_ATR_MULT,
    "TREND_TRAIL_ATR_MULT": config.TREND_TRAIL_ATR_MULT,
}

# Account protections switched off, for the diagnostic run only.
DIAGNOSTIC_OVERRIDES = {
    "MAX_DRAWDOWN_FRACTION": 1.0,
    "EMERGENCY_CLOSE_DRAWDOWN_FRACTION": 1.0,
    "MAX_DAILY_LOSS_FRACTION": 1.0,
    "MAX_CONSECUTIVE_LOSSES": 10 ** 9,
}

# Hypothesis 3 (trend following, docs/STRATEGY-HYPOTHESIS.md) always needs
# these, halts-off or not: the discretionary exits below assume a short-
# horizon position and would cut a developing trend on the noise the
# chandelier trailing stop is meant to ride through. Portfolio drawdown
# protection is deliberately NOT here -- that stays on.
TREND_STRATEGY_OVERRIDES = {
    "VOLATILITY_SPIKE_ENABLED": False,
    "BREAK_OF_STRUCTURE_ENABLED": False,
    "SESSION_END_CLOSE": False,          # trend positions ride through weekends
    "MAX_POSITION_AGE_SECONDS": 90 * 86400,   # no fixed time exit
}

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "docs", "reports")


def main():
    if not os.path.exists(DATA_PATH):
        print("No data at %s -- run scripts/fetch_historical_data.py first." % DATA_PATH)
        return 1

    raw = pd.read_csv(DATA_PATH, index_col=0, parse_dates=True)
    spec = {}
    if os.path.exists(SPEC_PATH):
        with open(SPEC_PATH, encoding="utf-8") as fh:
            spec = json.load(fh)

    # Bar times in the CSV are broker SERVER time (New York + 7 h), not UTC.
    clock = BrokerClock.from_config(config)
    df = raw.copy()
    df.index = clock.index_to_utc(df.index.tz_localize(None) if df.index.tz is not None else df.index)
    print("Loaded %d bars: %s -> %s UTC (%.2f years)"
          % (len(df), df.index[0], df.index[-1],
             (df.index[-1] - df.index[0]).days / 365.25))

    plan_fn = None
    base_overrides = {}
    if STRATEGY_NAME == "breakout":
        strategy = BreakoutStrategy(channel_period=20, atr_expansion_min=1.1,
                                    rsi_period=config.RSI_PERIOD)
        warmup = required_warmup_bars(strategy.channel_period, config.RSI_PERIOD,
                                      strategy.channel_period, config.ATR_PERIOD)
    elif STRATEGY_NAME == "trend":
        strategy = TrendFollowingStrategy(trend_period=200, channel_period=20,
                                          rsi_period=config.RSI_PERIOD)
        warmup = required_warmup_bars(strategy.trend_period, config.RSI_PERIOD,
                                      strategy.channel_period, config.ATR_PERIOD)
        plan_fn = plan_trend_entry
        base_overrides = TREND_STRATEGY_OVERRIDES
    elif STRATEGY_NAME == "basic":
        strategy = BasicTradingStrategy(ema_fast=config.EMA_FAST, ema_slow=config.EMA_SLOW,
                                        rsi_period=config.RSI_PERIOD, bb_period=config.BB_PERIOD,
                                        bb_std=config.BB_STD_DEV)
        warmup = required_warmup_bars(config.EMA_SLOW, config.RSI_PERIOD,
                                      config.BB_PERIOD, config.ATR_PERIOD)
    else:
        print("Unknown --strategy %r -- known: basic, breakout, trend" % STRATEGY_NAME)
        return 1
    print("Strategy: %s" % STRATEGY_NAME)

    # Hypothesis 3's initial ATR-based stop (2.5x ATR) is wider than
    # Hypotheses 1/2's, and at $1,000 (the user's actual demo balance) nearly
    # every qualifying signal was declined below the broker's minimum lot --
    # measured: 0 of 52 candidates sized on a 20,000-bar H1 sample. A trend-
    # following account is realistically capitalised well beyond a $1,000
    # scalping-sized account, so this test uses $10,000. Hypotheses 1/2 keep
    # $1,000 to match the account this project is actually validating.
    INITIAL_BALANCE = 10000.0 if STRATEGY_NAME == "trend" else 1000.0
    print("Initial balance: $%.2f%s" % (INITIAL_BALANCE,
          " (larger than the $1,000 demo balance -- see comment above)"
          if STRATEGY_NAME == "trend" else ""))

    try:
        quality = validate_for_trading(df, BAR_SECONDS, min_bars=warmup, check_staleness=False)
    except DataQualityError as exc:
        print("DATA QUALITY FAILURE: %s" % exc)
        return 1
    print("Data quality: %s" % quality)

    prepared = prepare_frame(df, strategy, config, already_utc=True).iloc[max(warmup, 300):]
    print("After warm-up trim: %d usable bars." % len(prepared))

    cost_model = build_cost_model(df, spec)
    spec_fields = {k: v for k, v in spec.items()
                   if k in ("digits", "point", "trade_contract_size", "trade_tick_value",
                            "trade_tick_size", "volume_min", "volume_step", "volume_max",
                            "trade_stops_level", "trade_freeze_level", "filling_mode")} or None
    # No calendar file: the live bot's recurring New York-time schedule.
    calendar = EconomicCalendar(path=os.path.join(REPORT_DIR, "no-calendar-file.json"))

    def factory(costs, overrides):
        merged = dict(base_overrides)
        merged.update(overrides)
        return LiveRulesBacktester(strategy, config, calendar=calendar, overrides=merged,
                                   cost_model=costs, initial_balance=INITIAL_BALANCE,
                                   spec_fields=spec_fields, timeframe=TIMEFRAME, plan_fn=plan_fn)

    def edge_factory(costs, overrides):
        # The gauntlet judges the STRATEGY's edge, so every step runs with the
        # account halts disabled. With them on, a sticky drawdown halt after
        # four months ended the run and step 2 "passed" on those four months
        # alone (2026-09-13). The halts are judged by the live-rules report.
        merged = dict(DIAGNOSTIC_OVERRIDES)
        merged.update(overrides)
        return factory(costs, merged)

    sensitivity_parameters = (TREND_SENSITIVITY_PARAMETERS if STRATEGY_NAME == "trend"
                              else SENSITIVITY_PARAMETERS)
    gauntlet = Gauntlet(prepared, None, session_of, initial_balance=INITIAL_BALANCE,
                        cost_model=cost_model, min_trades=30,
                        backtester_factory=edge_factory,
                        sensitivity_parameters=sensitivity_parameters)

    def publish(result, stem, title, note):
        report = performance_report(
            trade_records(result.trades), result.initial_balance,
            {"blocked_entries": result.blocked, "halts": result.halts,
             "declined_trades": result.declined_trades, "bars": result.bars,
             "reconciles": result.reconciles(), "notes": note})
        text = format_report(report, title)
        print("\n" + text)
        os.makedirs(REPORT_DIR, exist_ok=True)
        save_report(report, text, os.path.join(REPORT_DIR, stem))

    costs_note = ("costs: measured session spreads, real swap, unverified "
                  "commission/slippage")

    # DIAGNOSTIC: the same rules with the account halts disabled, so the rules'
    # expectancy is measured over the whole sample rather than only until the
    # first halt. Not a configuration anyone should run.
    if "--skip-diagnostic" not in sys.argv:
        print("\nRunning the DIAGNOSTIC backtest (account halts disabled)...")
        # Identical to the gauntlet's full realistic-cost run: reuse it.
        publish(gauntlet._backtest(prepared, cost_model),
                "backtest-xauusd%s-live-rules-no-halts" % REPORT_SUFFIX,
                "XAUUSD %s backtest -- DIAGNOSTIC: live rules, halts disabled" % TIMEFRAME,
                "DIAGNOSTIC ONLY: drawdown/daily-loss/loss-streak halts disabled; "
                + costs_note)
    if "--diagnostic-only" in sys.argv:
        return 0

    # Exactly what the live bot would have done, halts included.
    if "--skip-live-report" in sys.argv:
        pass
    else:
        print("\nRunning the full realistic-cost backtest (live rules)...")
        publish(factory(cost_model, {}).run(prepared),
                "backtest-xauusd%s-live-rules" % REPORT_SUFFIX,
                "XAUUSD %s backtest -- live rules, realistic costs" % TIMEFRAME,
                "live rules incl. sticky drawdown halt; " + costs_note)

    print("\n" + "=" * 70)
    print("RUNNING THE GAUNTLET (stops at the first failure)")
    print("=" * 70)
    results = gauntlet.run(stop_on_failure=True)
    lines = ["Timeframe: %s | data: %s bars, %s -> %s"
            % (TIMEFRAME, len(prepared), prepared.index[0], prepared.index[-1])]
    for r in results:
        lines.append(str(r))
        for key, value in r.metrics.items():
            lines.append("    %s = %s" % (key, value))
    lines.append("VERDICT: %s" % gauntlet.verdict())
    print("\n".join(lines))
    with open(os.path.join(REPORT_DIR, "gauntlet-xauusd%s-live-rules.txt" % REPORT_SUFFIX),
              "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # Evidence for the Phase 13 live guardrail (execution/rollout.py). Only a
    # run of the live bot's actual strategy (basic) at its configured
    # TIMEFRAME counts as the recorded Gate C, so an exploratory
    # --timeframe/--strategy run does not silently unlock live trading.
    if TIMEFRAME == config.TIMEFRAME.upper() and STRATEGY_NAME == "basic":
        from datetime import datetime, timezone
        from execution.rollout import record_gate
        passed = bool(results) and len(results) == 7 and all(r.passed for r in results)
        record_gate("gate_c", {
            "passed": passed, "verdict": gauntlet.verdict(),
            "data": "%s -> %s, %d bars" % (prepared.index[0], prepared.index[-1], len(prepared)),
            "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    else:
        print("\n(strategy=%s timeframe=%s differs from the live bot's basic/%s -- "
              "this run is exploratory and was NOT recorded as Gate C.)"
              % (STRATEGY_NAME, TIMEFRAME, config.TIMEFRAME))
    return 0


if __name__ == "__main__":
    sys.exit(main())
