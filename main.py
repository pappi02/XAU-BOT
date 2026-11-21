"""
Main entry point for XAU/USD Trading Bot Phase 5 (Adaptive + Scalable Version)
"""

import json
import os
import sys
import time

import pandas as pd
import MetaTrader5 as mt5

# Import project modules
import config
from logger_config import setup_logger, DecisionLog
from data.connect_mt5 import (connect_mt5, disconnect_mt5,
                              AccountIdentityError, is_connected,
                              reconnect_with_backoff)
from data.fetch_candles import get_candles
from data.symbol_resolver import resolve_symbol, SymbolNotAvailable
from utils.config_validation import ConfigError, assert_valid
from data.quality import (DataQualityError, required_warmup_bars,
                          validate_for_trading)
from strategies.strategy_basic import BasicTradingStrategy
from utils.indicators import atr
from datetime import datetime, timezone
from strategies.exit_rules import entry_too_close_to_weekly_close
from strategies.trade_plan import (ATR_RATIO_WINDOW_BARS, news_blocks_entry,
                                   plan_entry)
from utils.news_reader import (get_latest_forex_news, sentiment_of,
                               NewsRefresher)
from utils.economic_calendar import EconomicCalendar
from execution.trade_executor import TradeExecutor
from execution.bar_gate import BarGate
from execution.control import (CircuitBreaker, HealthReport,
                               KillSwitch, ShutdownHandler,
                               broker_snapshot, publish_candles)
from risk.risk_manager import RiskManager
from trade_logger import trade_logger

# Set up logger
logger = setup_logger(level=config.LOG_LEVEL)

# === Settings ===
# Phase 1.3 removed TRAILING_STOP_ENABLED, SCALING_ENABLED and
# AUTO_CLOSE_ENABLED from here -- they silently overrode config.py (audit M-08).
# Phase 4.1 removed the last one, MAX_OPEN_TRADES = 12, which disagreed with
# config.MAX_CONCURRENT_POSITIONS = 100. Both now come from config, and both
# are 1. config.py is the single source of truth for every setting.


def adaptive_wait(last_atr, timeframe="M5"):
    """Adjust sleep interval based on volatility (ATR)."""
    if pd.isna(last_atr):
        return 60
    if last_atr < 2:  # Low volatility
        return 180
    elif 2 <= last_atr <= 6:
        return 90
    else:
        return 45 if timeframe == "M1" else 60


# manage_positions() lived here and is DELETED (Phase 5 follow-up).
#
# It was a SECOND trailing-stop implementation -- it built its own
# TRADE_ACTION_SLTP request and called _send_order directly, in parallel with
# TradeExecutor.manage_open_positions(). Nothing called it any more once Phase
# 5.2 wired the executor's version into the loop, so it was dead code that
# looked authoritative: exactly the shape of the duplicate-definition problems
# the audit found (M-08). It also bypassed the Phase 2.3 order validation.
#
# Its scaling block is superseded by TradeExecutor's adaptive scaling.

# The dead main_loop_legacy_gated() lived here. It was retained through Phases
# 1-3 because it held the entry gates the live loop was missing. Phase 4.1 has
# now ported those gates into main_loop() -- strength floor, position cap,
# per-bar dedupe and the signal-reversal hold -- so the dead copy is deleted.
# Its text survives in git history and in docs/phase4-entry-gating.md.


def main_loop():
    """
    Phase 5 Enhanced Bot — includes full connection and safety checks
    """

    # --- Step 1: Connect to the account, failing closed ---
    # Phase 1.6 (H-06): this used to be `if MT5_ACCOUNT and MT5_PASSWORD and
    # MT5_SERVER:` -- so a missing credential skipped the login entirely and the
    # bot traded whatever account the terminal already had open. connect_mt5
    # now raises AccountIdentityError on a missing credential, and refuses a
    # live account unless ALLOW_LIVE=true. It also performs the initialize().
    logger.info("🔐 Connecting to MT5...")
    if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD,
                       config.MT5_SERVER, config.MT5_TIMEOUT_MS):
        logger.error("❌ Failed to connect to MT5 account. Exiting Phase 5.")
        return
    logger.info("✅ Connected to MT5 account")

    # --- Step 3: Confirm the symbol is tradeable on THIS account ---
    #
    # config.SYMBOL was 'XAUUSDm' against a broker that lists 'XAUUSD', so the
    # bot exited here on every start with no hint what the right name was.
    # resolve_symbol lists the broker's gold-like symbols when it fails.
    try:
        resolve_symbol(mt5, config.SYMBOL)
    except SymbolNotAvailable as exc:
        logger.error("%s", exc)
        disconnect_mt5()
        return

    # --- Step 4: Instantiate managers and strategy ---
    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)

    # MT5 stamps everything in broker server time. A wrong offset silently
    # breaks position age, feed staleness and the weekend close, so a
    # measurable mismatch refuses to start.
    clock_status, clock_message = executor.clock.verify(mt5, config.SYMBOL_PHASE5)
    if clock_status == "mismatch":
        logger.error("%s", clock_message)
        disconnect_mt5()
        return
    logger.info("Clock: %s", clock_message)
    strategy = BasicTradingStrategy(
        ema_fast=config.EMA_FAST,
        ema_slow=config.EMA_SLOW,
        rsi_period=config.RSI_PERIOD,
        bb_period=config.BB_PERIOD,
        bb_std=config.BB_STD_DEV
    )

    logger.info("🚀 Phase 5 Bot initialized and running...")

    # Phase 8: observability and control.
    decisions = DecisionLog()
    breaker = CircuitBreaker(
        threshold=getattr(config, "CIRCUIT_BREAKER_THRESHOLD", 5))
    kill_switch = KillSwitch()
    health = HealthReport()
    shutdown = ShutdownHandler().install()

    # Phase 10 (H-05): a real economic calendar. There was none at all, so the
    # bot traded straight into CPI, NFP and FOMC.
    calendar = None
    if getattr(config, "ECONOMIC_CALENDAR_ENABLED", False):
        calendar = EconomicCalendar(config.ECONOMIC_CALENDAR_PATH)
        upcoming = calendar.next_event()
        if upcoming:
            logger.info("Next high-impact event: %s at %s",
                        upcoming.name, upcoming.when)

    # Phase 10: fetch news OFF the trading thread. Even with a timeout, up to
    # 8 seconds of the loop could be spent waiting on a socket -- during which
    # no position is managed and no stop is checked.
    news_refresher = NewsRefresher().start()

    # Phase 4.2: one decision per closed bar, and one entry per bar.
    bar_gate = BarGate(config.TIMEFRAME)
    logger.info("Bar gate armed for %s (%d second bars)",
                config.TIMEFRAME, bar_gate.bar_seconds)

    # Checked once, as soon as enough ATR history exists (Step 7, below).
    volatility_regime_checked = False

    try:
        while True:
            try:
                # --- Step 4a: Control checks (Phase 8.2 / 8.3) ---
                if shutdown.should_stop:
                    logger.info("Shutdown requested -- leaving the loop.")
                    break

                if breaker.is_tripped:
                    logger.critical("Circuit breaker is tripped. Not trading. "
                                    "Investigate, then restart.")
                    # BUG FIX: this wrote kill_switch=True whenever the
                    # BREAKER was tripped, reporting the wrong control as
                    # engaged. Report each control's real state.
                    health.update(connected=is_connected(),
                                  circuit_breaker=breaker.status(),
                                  kill_switch=kill_switch.is_engaged())
                    time.sleep(60)
                    continue

                # --- Step 4b: Verify the terminal is still there (Phase 6.4) ---
                #
                # Without this, a dropped connection makes every query return
                # None, which the old code read as "no positions" -- so the bot
                # would keep trading against an account it could not see.
                if not is_connected():
                    logger.error("MT5 terminal disconnected. Halting trading "
                                 "and attempting to reconnect.")
                    if not reconnect_with_backoff(config.MT5_ACCOUNT,
                                                  config.MT5_PASSWORD,
                                                  config.MT5_SERVER,
                                                  config.MT5_TIMEOUT_MS):
                        logger.error("Reconnect failed. Not trading; will retry.")
                        time.sleep(60)
                        continue
                    logger.info("Reconnected; resuming.")

                # --- Step 4c: Record realised P&L from the broker (Phase 7.2) ---
                #
                # H-07: the audited bot recorded only its OWN closes, using the
                # floating P&L read before the close order was sent. Trades
                # closed by a server-side stop were never recorded at all --
                # and stop-outs are the loss-heavy tail, so the win rate was
                # biased upward BY CONSTRUCTION. This polls the broker's own
                # deal history, which includes every close however it happened.
                try:
                    recorded = executor.sync_broker_deals()
                    if recorded:
                        logger.info("Recorded %d closing deal(s) from the broker.",
                                    recorded)
                except Exception as ex:
                    logger.exception("Deal sync failed: %s", ex)

                # --- Step 5: Fetch historical data safely ---
                timeframe_map = {
                    'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                    'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4, 'D1': mt5.TIMEFRAME_D1,
                    'W1': mt5.TIMEFRAME_W1, 'MN': mt5.TIMEFRAME_MN1
                }
                mt5_timeframe = timeframe_map.get(config.TIMEFRAME.upper(), mt5.TIMEFRAME_M5)

                df = get_candles(config.SYMBOL_PHASE5, mt5_timeframe, config.NUM_CANDLES,
                                 clock=executor.clock)
                if df is None or df.empty:
                    logger.warning("⚠️ No data fetched or empty dataframe — retrying in 30 seconds...")
                    time.sleep(30)
                    continue

                # get_candles drops the still-forming bar, so this is the
                # newest CLOSED bar -- the one every decision keys on.
                bar_time = df.index[-1]
                logger.info("%d closed candles | bar %s | last close $%.2f",
                            len(df), bar_time, df['close'].iloc[-1])

                # --- Step 5b: Validate the data before trusting it (Phase 9.1) ---
                #
                # H-09: with too few bars the indicators come back NaN, the
                # strategy returns HOLD, and a data outage becomes
                # indistinguishable from a quiet market. "I cannot decide" must
                # be a different answer from "I decide to do nothing".
                warmup = required_warmup_bars(config.EMA_SLOW, config.RSI_PERIOD,
                                              config.BB_PERIOD, config.ATR_PERIOD)
                try:
                    quality = validate_for_trading(df, bar_gate.bar_seconds,
                                                   min_bars=warmup)
                except DataQualityError as exc:
                    logger.error("Data unusable -- NOT signalling: %s", exc)
                    decisions.record(action="none", entry_blocked="data quality",
                                     detail=str(exc))
                    breaker.record_failure(exc)
                    time.sleep(30)
                    continue

                # Phase 12.1: publish closed bars for the dashboard, so it
                # never opens its own MT5 connection to draw a chart.
                publish_candles(df)

                if quality["intraday_gaps"]:
                    logger.warning("%d intraday gap(s) in the series.",
                                   quality["intraday_gaps"])

                # --- Step 6: Apply indicators ---
                df = strategy.prepare_data(df)

                # The indicator columns must exist under their CONFIGURED names
                # (audit M-10): reading 'RSI_14' literally raised KeyError on
                # every iteration once RSI_PERIOD changed.
                try:
                    validate_for_trading(
                        df, bar_gate.bar_seconds,
                        required_columns=['RSI_%d' % config.RSI_PERIOD,
                                          'EMA_%d' % config.EMA_FAST,
                                          'EMA_%d' % config.EMA_SLOW],
                        check_staleness=False)
                except DataQualityError as exc:
                    logger.error("Indicators unusable -- NOT signalling: %s", exc)
                    breaker.record_failure(exc)
                    time.sleep(30)
                    continue

                # --- Step 7: Compute ATR for SL ---
                atr_series = atr(df, period=config.ATR_PERIOD)
                last_atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 and not pd.isna(atr_series.iloc[-1]) else None
                # generate_signal scores volatility from the 'ATR' column. It
                # was never added here, so the live bot scored against a
                # one-bar high-low proxy while the backtest used real ATR:
                # identical bars, different strengths.
                df['ATR'] = atr_series

                # Phase 12 follow-up: this assertion existed but was never
                # called from anywhere -- exactly the class of bug (M-03,
                # absolute thresholds unreachable against the real ATR
                # distribution) it was written to catch, uncaught because
                # nothing ran it. Checked once, as soon as there is enough
                # history to judge, and logged rather than fatal: a flat/stale
                # ATR distribution is a data problem the loop's other checks
                # already treat as recoverable, not a reason to stop the bot.
                if not volatility_regime_checked:
                    atr_history = [v for v in atr_series.tail(300).tolist()
                                   if v is not None and v == v]
                    if len(atr_history) >= 30:
                        from risk.volatility import VolatilityRegime
                        try:
                            VolatilityRegime(20.0, 80.0).assert_thresholds_are_reachable(atr_history)
                        except ValueError as exc:
                            logger.error("Volatility regime check: %s", exc)
                        volatility_regime_checked = True

                # --- Step 8: Generate signal ---
                signal_info = strategy.generate_signal(df)
                signal = signal_info['signal']
                strength = signal_info['strength']

                # Phase 9.1 (audit M-10): this read df['RSI_14'] literally.
                # Changing RSI_PERIOD raised KeyError on every iteration, which
                # the loop swallowed and retried forever -- a config knob that
                # bricked the bot. The column name follows the config now.
                rsi_column = 'RSI_%d' % config.RSI_PERIOD
                rsi_now = df[rsi_column].iloc[-1] if rsi_column in df.columns else float('nan')
                logger.info("Signal: %s | %s: %.2f | Strength: %.1f%%",
                            signal, rsi_column, rsi_now, strength)

                # --- Step 9: News sentiment bias ---
                # Cached; the refresher thread does the fetching.
                news_sentiment = NewsRefresher.current()
                logger.info("📰 News sentiment: %s", news_sentiment)

                # Headline sentiment vetoes an opposing entry only when
                # NEWS_SENTIMENT_TRADING_ENABLED (default off): it cannot be
                # reproduced historically, so it cannot be backtested.
                if news_blocks_entry(signal, news_sentiment, config):
                    logger.info("📊 News bias: %s vetoed by %s sentiment",
                                signal, sentiment_of(news_sentiment))
                    signal = "HOLD"

                # --- Step 9b: Move stops on open positions (Phase 5.2) ---
                #
                # This is the step the audited bot never had. Trailing used to
                # live inside should_close_trade(), where a trail trigger meant
                # "close at market". Here it MODIFIES the stop and never closes.
                if config.TRAILING_STOP_ENABLED or config.BREAK_EVEN_ENABLED:
                    try:
                        moved = executor.manage_open_positions(
                            config.SYMBOL_PHASE5,
                            atr=last_atr,
                            trend_strength=signal_info['components']['ema_signal'],
                            news_sentiment=news_sentiment,
                        )
                        if moved:
                            logger.info("Moved %d stop(s).", moved)
                    except Exception as ex:
                        logger.exception("Error managing stops: %s", ex)
                    # A stop that could not be moved after retries is a
                    # failure the operator must see, not a log line.
                    while executor.stop_failures:
                        breaker.record_failure("stop not moved: %s"
                                               % executor.stop_failures.pop(0))

    # --- Step 10: Position monitoring and auto-close ---
                if config.AUTO_CLOSE_ENABLED:
                    # BUG FIX: this called a bare `get_open_positions`, which is
                    # not imported anywhere in this module -- NameError on the
                    # first iteration with AUTO_CLOSE_ENABLED. Every other call
                    # site in this file uses executor.get_open_positions().
                    open_positions = executor.get_open_positions(config.SYMBOL_PHASE5)
                    if open_positions:
                        logger.info(f"📊 Monitoring {len(open_positions)} open positions for auto-close conditions")

                        for pos in open_positions:
                            position_type = 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL'


                            # Get news sentiment
                            # Cached; the refresher thread does the fetching.
                            news_sentiment = NewsRefresher.current()

                            # Check if position should be closed using comprehensive auto-close logic
                            close_decision = executor.should_close_trade(
                                position=pos,
                                current_data=df,
                                strategy=strategy,
                                news_sentiment=news_sentiment,
                                atr_value=last_atr,
                                # entry_atr comes from the executor's own
                                # per-ticket record (Phase 5.7).
                                entry_atr=None
                            )

                            if close_decision['should_close']:
                                logger.info(f"🚨 Auto-close triggered for position {pos.ticket} ({position_type}): {close_decision['reason']}")

                                # Close the position
                                try:
                                    success = executor.close_position_by_ticket(pos.ticket)
                                    if success:
                                        logger.info(f"✅ Auto-closed position {pos.ticket} - Reason: {close_decision['reason']}")
                                        # Log the auto-close event
                                        trade_logger.log_auto_close(
                                            ticket=pos.ticket,
                                            symbol=config.SYMBOL_PHASE5,
                                            position_type=position_type,
                                            close_reason=close_decision['reason'],
                                            pnl=pos.profit
                                        )
                                    else:
                                        logger.error(f"❌ Failed to auto-close position {pos.ticket}")
                                except Exception as ex:
                                    logger.exception(f"❌ Error auto-closing position {pos.ticket}: {ex}")

                    # Emergency close if account health is critical.
                    #
                    # BUG FIX: this read config.INITIAL_ACCOUNT_BALANCE, which
                    # Phase 3.4 DELETED -- so it raised AttributeError on every
                    # iteration, and the bare `except` swallowed it. The
                    # emergency close could therefore never fire. That is the
                    # same fail-open shape as audit L-04: a risk control that
                    # reports "nothing wrong" for every error.
                    #
                    # It also repeated L-04's original defect -- measuring
                    # drawdown against a hardcoded starting balance. It now uses
                    # the persisted equity high-water mark, like every other
                    # drawdown check.
                    try:
                        account = risk_mgr.refresh_account()
                        equity = risk_mgr.account_equity(account)
                        drawdown = risk_mgr.state.drawdown_fraction(equity)

                        if drawdown >= config.EMERGENCY_CLOSE_DRAWDOWN_FRACTION:
                            logger.warning(
                                "EMERGENCY: equity %.2f is %.1f%% below its peak "
                                "of %.2f -- closing all positions.",
                                equity, drawdown * 100,
                                risk_mgr.state.equity_high_water_mark or 0.0)
                            executor.close_all_positions(config.SYMBOL_PHASE5)
                            risk_mgr.state.halt(
                                "emergency drawdown close at %.1f%%" % (drawdown * 100))
                    except Exception as ex:
                        # Fail CLOSED: if we cannot assess account health we do
                        # not keep trading as though it were fine.
                        logger.exception("Emergency-close check FAILED: %s", ex)
                        raise

                # --- Step 11: Trade execution ---
                #
                # Phase 4.1 (audit C-02). The live loop previously had NO entry
                # gating at all: `if signal in ("BUY","SELL")` then sleep(60).
                # The only brake was MAX_CONCURRENT_POSITIONS = 100 inside
                # enter_trade. These four gates are ported from the dead
                # main_loop_legacy_gated() and run_bot.py's trading_bot()
                # (docs/phase4-entry-gating.md), with the reversal hold's unit
                # bug fixed -- it counts bars now, not hardcoded 300s ticks.

                # Gate 0: signal-reversal hold. May replace `signal` with the
                # previously held one.
                signal = bar_gate.apply_reversal_hold(
                    signal, strength, bar_time,
                    config.SIGNAL_REVERSAL_MIN_STRENGTH,
                    config.MIN_SIGNAL_HOLD_BARS,
                )

                # One position query per iteration, reused by the cap gate and
                # the decision record below.
                open_positions_now = executor.get_open_positions(config.SYMBOL_PHASE5)

                entry_blocked = None
                # Gate -1: the kill switch. Stops NEW positions; existing ones
                # are left alone, because pausing and liquidating are different
                # decisions (Phase 8.3).
                if kill_switch.is_engaged():
                    entry_blocked = "kill switch engaged"
                # Gate -0.5: scheduled macro event. Risk avoidance, not signal:
                # gold reprices violently on CPI/NFP/FOMC and stops slip.
                elif calendar is not None and calendar.is_blackout(
                        before_minutes=config.EVENT_BLACKOUT_BEFORE_MINUTES,
                        after_minutes=config.EVENT_BLACKOUT_AFTER_MINUTES)[0]:
                    entry_blocked = "event blackout: %s" % calendar.is_blackout(
                        before_minutes=config.EVENT_BLACKOUT_BEFORE_MINUTES,
                        after_minutes=config.EVENT_BLACKOUT_AFTER_MINUTES)[1]
                elif signal not in ("BUY", "SELL"):
                    entry_blocked = "signal is %s" % signal
                # Gate 1: strength floor.
                elif strength < config.MIN_ENTRY_STRENGTH:
                    entry_blocked = ("strength %.1f%% < %.1f%% minimum"
                                     % (strength, config.MIN_ENTRY_STRENGTH))
                # Gate 2: position cap, checked in the LOOP, not only in
                # enter_trade.
                elif len(open_positions_now) >= config.MAX_OPEN_TRADES:
                    entry_blocked = ("already at the %d position cap"
                                     % config.MAX_OPEN_TRADES)
                # Gate 3: one entry per closed bar.
                elif not bar_gate.may_enter(bar_time):
                    entry_blocked = "already entered on bar %s" % bar_time
                # Gate 3b: no entry that could not be flattened before the
                # weekend (the minimum hold would block the weekend close).
                elif entry_too_close_to_weekly_close(
                        datetime.now(timezone.utc), config, bar_gate.bar_seconds):
                    entry_blocked = "too close to the weekly close"
                # Gate 4: a stop needs a usable ATR (plan_entry returns None).
                elif last_atr is None or not last_atr > 0:
                    entry_blocked = "ATR unusable -- cannot size a stop"

                if entry_blocked:
                    logger.info("No entry: %s", entry_blocked)
                else:
                    entry_price = df['close'].iloc[-1]

                    # Stop and target: one implementation, shared with the
                    # backtester (strategies/trade_plan.py).
                    plan = plan_entry(signal_info, last_atr,
                                      atr_series.tail(ATR_RATIO_WINDOW_BARS).tolist(),
                                      news_sentiment, config)
                    sl_distance = plan.sl_distance
                    dynamic_rr = plan.rr
                    dynamic_lot_size = risk_mgr.calculate_dynamic_lot_size(
                        stop_loss_distance=sl_distance)
                    session = risk_mgr.get_current_market_session()
                    stop_price, tp_price = plan.levels(signal, entry_price)

                    logger.info("📊 Plan: strength=%.1f%% ATR=%.2f session=%s -> "
                                "SL x%.2f (%.2f) RR %.2f lots %s",
                                strength, last_atr, session, plan.sl_multiplier,
                                sl_distance, dynamic_rr, dynamic_lot_size)

                    try:
                        res = executor.enter_trade(
                            config.SYMBOL_PHASE5, signal, entry_price,
                            stop_price, tp_price, volume=dynamic_lot_size,
                            # Phase 5.7: record ATR at entry so the
                            # volatility-spike exit can actually fire.
                            entry_atr=last_atr)
                        # Phase 4.2: claim this bar so a re-evaluation of the
                        # same closed bar cannot open a second position.
                        bar_gate.record_entry(bar_time)
                        logger.info(f"✅ Trade placed on bar {bar_time}: {signal} | SL={stop_price:.2f} | TP={tp_price:.2f} | RR={dynamic_rr} | SL_Distance={sl_distance:.2f} | Lot_Size={dynamic_lot_size} | Result={res}")
                    except Exception as ex:
                        # A refusal from the risk layer is an expected outcome,
                        # not a crash: log it and wait for the next bar.
                        logger.warning("Entry not taken: %s", ex)

                # --- Step 11b: Record the decision (Phase 8.1) ---
                #
                # One structured record per iteration: every input and every
                # gate. This is what makes "why did it not trade?" answerable
                # without re-reading thousands of lines of prose.
                try:
                    spec = executor.get_symbol_spec(config.SYMBOL_PHASE5)
                    spread_points = spec.spread_points(mt5)
                except Exception:
                    spread_points = None

                decisions.record(
                    bar=str(bar_time),
                    symbol=config.SYMBOL_PHASE5,
                    signal=signal,
                    strength=round(float(strength), 2),
                    atr=round(float(last_atr), 4) if last_atr else None,
                    spread_points=round(spread_points, 1) if spread_points else None,
                    session=risk_mgr.get_current_market_session(),
                    news=news_sentiment.get("sentiment")
                         if isinstance(news_sentiment, dict) else news_sentiment,
                    open_positions=len(open_positions_now),
                    entry_blocked=entry_blocked,
                    action="entry" if not entry_blocked else "none",
                    min_entry_strength=config.MIN_ENTRY_STRENGTH,
                    max_open_trades=config.MAX_OPEN_TRADES,
                )

                # Phase 12.1: the loop is the only MT5 client. It publishes
                # account, positions and the last tick here; the read API and
                # dashboard read this file instead of opening their own
                # connections to the same terminal.
                health.update(
                    connected=True,
                    open_positions=len(open_positions_now),
                    daily_pnl=risk_mgr.daily_pnl,
                    circuit_breaker=breaker.status(),
                    kill_switch=kill_switch.is_engaged(),
                    halted_reason=risk_mgr.state.halted_reason,
                    **broker_snapshot(mt5, config.SYMBOL, open_positions_now),
                )
                breaker.record_success()

                # --- Step 12: Wait for the next bar to close ---
                #
                # Phase 4.2: was a fixed sleep(60), which on an M5 timeframe
                # re-evaluated the same bar about five times. There is no new
                # information until a bar closes, so wait for exactly that.
                wait = bar_gate.seconds_until_next_bar(time.time())
                logger.info("Sleeping %.0fs until the next %s bar closes.",
                            wait, config.TIMEFRAME)
                time.sleep(wait)

            except Exception as e:
                # Phase 8.2: count it. The audited loop swallowed every
                # exception and slept, so a broker rejecting every order
                # produced an indefinite silent outage that looked healthy.
                logger.exception("Error in main loop: %s", e)
                breaker.record_failure(e)
                health.update(circuit_breaker=breaker.status())
                time.sleep(5)

    finally:
        disconnect_mt5()
        logger.info("🔌 MT5 disconnected and bot stopped.")


def flatten():
    """Close every position and exit (Phase 8.3, `--flatten`).

    Deliberately separate from the kill switch. Stopping new entries and
    liquidating everything are different decisions, and a system whose only
    pause button is "close everything" will be used to close everything when a
    pause was what was wanted.
    """
    logger.warning("FLATTEN requested: closing all positions for %s.",
                   config.SYMBOL_PHASE5)

    if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD,
                       config.MT5_SERVER, config.MT5_TIMEOUT_MS):
        raise SystemExit("Could not connect to MT5 -- nothing was closed.")

    try:
        risk_mgr = RiskManager(mt5, config)
        executor = TradeExecutor(mt5, config, risk_mgr)

        before = executor.get_open_positions(config.SYMBOL_PHASE5)
        logger.warning("%d position(s) open.", len(before))
        if not before:
            return 0

        closed = executor.close_all_positions(config.SYMBOL_PHASE5)
        after = executor.get_open_positions(config.SYMBOL_PHASE5)
        logger.warning("Closed %s position(s); %d still open.", closed, len(after))

        if after:
            logger.error("NOT FLAT: %d position(s) remain. Close them in the "
                         "terminal.", len(after))
            return 1

        executor.sync_broker_deals()
        return 0
    finally:
        disconnect_mt5()


def main(argv=None):
    """Entry point. Supports --flatten and --health.

    --health reads a file and NEVER connects to a broker.
    """
    argv = sys.argv[1:] if argv is None else argv

    if "--health" in argv:
        report = HealthReport().read()
        print(json.dumps(report, indent=2) if report
              else "No health report yet -- the bot has not run.")
        return 0

    if "--flatten" in argv:
        return flatten()

    if "--record-review" in argv:
        # Phase 13: live trading requires a daily manual review.
        from execution.rollout import record_daily_review
        reviewer = os.getenv("USERNAME") or os.getenv("USER") or "operator"
        record_daily_review(reviewer)
        print("Daily review recorded by %s." % reviewer)
        return 0

    if "--clear-halt" in argv:
        # Offline: a drawdown or daily-loss halt persists in the risk state
        # file across restarts. Clearing it is a deliberate human act.
        from risk.risk_state import RiskState
        state = RiskState()
        reason = state.halted_reason
        if not reason:
            print("No halt is set.")
            return 0
        state.clear_halt()
        print("Cleared halt: %s. Entries may resume on the next start." % reason)
        return 0

    if "--ack-loss-streak" in argv:
        # Offline: reads and writes the local trade database only.
        from execution.position_state import PositionStateStore
        store = PositionStateStore()
        streak = store.consecutive_losses()
        newest = store.acknowledge_loss_streak()
        print("Acknowledged a streak of %d losing trade(s) through deal %s. "
              "Entries may resume." % (streak, newest))
        return 0

    print("XAU/USD Trading Bot")
    print("=" * 40)
    print("Starting Gold Scalper with risk management.")
    print("WARNING: this executes real trades on the configured account.")
    print("Kill switch:  create a file named STOP in the project root")
    print("Flatten:      python main.py --flatten")
    print("Health:       python main.py --health")
    print("Loss streak:  python main.py --ack-loss-streak")
    print("Risk halt:    python main.py --clear-halt")
    print("Daily review: python main.py --record-review")
    print("=" * 40)

    # Phase 12.4: validate configuration BEFORE touching the broker. Every
    # problem is reported at once, so one run shows everything to fix.
    try:
        assert_valid(config)
    except ConfigError as exc:
        raise SystemExit("\n%s" % exc)

    try:
        main_loop()
    except AccountIdentityError as exc:
        # Phase 1.6: fail closed, and say why in one line rather than a
        # traceback. This is the expected outcome of an unconfigured .env.
        raise SystemExit("\n%s" % exc)
    except KeyboardInterrupt:
        logger.warning("Interrupted. Positions are left as they are -- use "
                       "--flatten to close them.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())