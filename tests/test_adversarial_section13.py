"""Audit section 13: the 25-scenario adversarial test plan (Phase 12.2).

One test per row of the audit's table, named test_sNN_*, each asserting the
audit's "expected safe behaviour" against a mocked MT5 boundary. No broker.

Three scenarios are marked ``unittest.expectedFailure``. That is deliberate and
honest: the safe behaviour the audit asks for is NOT yet implemented, and an
expected failure keeps the gap visible in every test run -- a skip would hide
it. When one is fixed, pytest reports an "unexpected success", which is the cue
to remove the marker.

  15  DST transition     session boundaries are fixed UTC hours
  16  Weekend gap        SESSION_END_CLOSE defaults to False
  24  SL modify fails    no retry/escalation path (stop modification is off)
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import (fake_config, fake_mt5, fake_risk_manager, fake_symbol_info,
                   make_executor)

from execution.bar_gate import BarGate
from execution.control import CircuitBreaker
from execution.order_validator import (OrderValidator, Rejection,
                                       enforce_stops_level)
from execution.position_state import PositionStateStore
from execution.symbol_spec import SymbolSpec
from risk.risk_manager import RiskManager
from risk.risk_state import RiskState

MAGIC = 987654321


def gold_spec(**overrides):
    fields = dict(name="XAUUSD", digits=2, point=0.01, contract_size=100.0,
                  tick_value=1.0, tick_size=0.01, volume_min=0.01,
                  volume_step=0.01, volume_max=50.0, stops_level_points=0,
                  freeze_level_points=0, filling_modes=2)
    fields.update(overrides)
    return SymbolSpec(**fields)


def result(retcode, volume=0.1, price=2000.50):
    return MagicMock(retcode=retcode, volume=volume, price=price, order=1,
                     comment="")


def position(**overrides):
    fields = dict(ticket=1, symbol="XAUUSD", type=0, volume=0.1,
                  price_open=2000.0, price_current=2000.0, sl=1990.0,
                  tp=2025.0, time=0, magic=MAGIC, profit=0.0, comment="")
    fields.update(overrides)
    return MagicMock(**fields)


class Harness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "trades.db")
        self.config = fake_config(TRADE_DB_PATH=self.db,
                                  RISK_STATE_PATH=os.path.join(self.dir, "rs.json"))
        self.mt5 = fake_mt5()
        self.ex = make_executor(self.mt5, self.config, fake_risk_manager())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def risk_manager(self, equity=10000.0):
        mt5 = fake_mt5()
        mt5.account_info.return_value = MagicMock(
            balance=equity, equity=equity, profit=0.0, margin_free=equity)
        return RiskManager(mt5, self.config), mt5


class TestAdversarialSection13(Harness):

    # 1 -------------------------------------------------------------------
    def test_s01_rapid_spike_does_not_market_close_the_position(self):
        """Gold +$25 in 3 bars. Expected: never closed at market by trailing.

        Audit C-06: a trail trigger closed the position at market. Trailing now
        only MODIFIES stops, and under the current configuration (stop
        modification off, user decision) nothing is sent at all.
        """
        sent = []
        self.mt5.order_send.side_effect = lambda r: sent.append(r) or result(10009)
        for price in (2010.0, 2018.0, 2025.0):
            self.mt5.symbol_info_tick.return_value = MagicMock(bid=price, ask=price + 0.1)
            self.mt5.positions_get.return_value = [
                position(price_current=price, profit=(price - 2000) * 10)]
            self.ex.manage_open_positions("XAUUSD", atr=3.0)
        deals = [r for r in sent if r.get("action") == self.mt5.TRADE_ACTION_DEAL]
        self.assertEqual(deals, [], "a spike closed the position at market")

    # 2 -------------------------------------------------------------------
    def test_s02_rapid_crash_stop_out_is_booked(self):
        """Server-side SL fills. Expected: one loss booked and logged.

        Audit: the closure was never written to the trade DB (H-07).
        """
        store = PositionStateStore(self.db)
        now = datetime.now(timezone.utc)
        self.mt5.history_deals_get.return_value = [MagicMock(
            ticket=900, position_id=1, order=900, symbol="XAUUSD", type=1,
            entry=1, volume=0.1, price=1990.0, profit=-100.0, commission=-0.7,
            swap=0.0, time=now.timestamp(), comment="[sl 1990.00]")]
        self.assertEqual(store.sync_deals(self.mt5), 1)
        stats = store.compute_statistics()
        self.assertEqual(stats["total_trades"], 1)
        self.assertAlmostEqual(stats["total_pnl"], -100.7)

    # 3 -------------------------------------------------------------------
    def test_s03_spread_expansion_blocks_entries(self):
        """Spread 20 -> 300 points. Expected: new entries blocked."""
        self.mt5.symbol_info_tick.return_value = MagicMock(bid=2000.00, ask=2003.00)
        with self.assertRaises(RuntimeError) as ctx:
            self.ex._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)
        self.assertIn("Spread", str(ctx.exception))
        self.mt5.order_send.assert_not_called()

    # 4 -------------------------------------------------------------------
    def test_s04_news_slippage_is_recorded(self):
        """Fill 80 points worse. Expected: actual fill recorded, not intent."""
        quality = self.ex._log_fill_quality(result(10009, volume=0.1, price=2001.30),
                                            {"volume": 0.1}, 2000.50)
        self.assertAlmostEqual(quality["slippage"], 0.80)
        self.assertAlmostEqual(quality["fill_price"], 2001.30)

    # 5 -------------------------------------------------------------------
    def test_s05_sixty_minutes_of_signals_open_one_position(self):
        """Strong trend for 60 min. Expected: one position, or a hard cap.

        Audit: 60 entries, one per loop iteration.
        """
        gate = BarGate("M5")
        start = pd.Timestamp("2026-01-05 08:00", tz="UTC")
        open_positions, entries = [], 0
        for minute in range(60):                   # a 60s loop for an hour
            bar = start + timedelta(minutes=(minute // 5) * 5)
            if len(open_positions) >= self.config.MAX_OPEN_TRADES:
                continue
            if not gate.may_enter(bar):
                continue
            gate.record_entry(bar)
            open_positions.append(bar)
            entries += 1
        self.assertEqual(entries, 1)

    # 6 -------------------------------------------------------------------
    def test_s06_five_evaluations_of_one_bar_enter_once(self):
        gate = BarGate("M5")
        bar = pd.Timestamp("2026-01-05 08:00", tz="UTC")
        entries = 0
        for _ in range(5):
            if gate.may_enter(bar):
                gate.record_entry(bar)
                entries += 1
        self.assertEqual(entries, 1)

    # 7 -------------------------------------------------------------------
    def test_s07_send_raises_after_fill_reconciles_to_one_position(self):
        """order_send fills, then reading the response raises.

        Expected: reconcile; exactly one position. Audit: retried 3x -> up to
        3 positions.
        """
        sent = {}

        def send(request):
            sent["comment"] = request["comment"]
            sent["count"] = sent.get("count", 0) + 1
            raise RuntimeError("IPC pipe broken while reading the reply")

        self.mt5.order_send.side_effect = send
        self.mt5.positions_get.side_effect = lambda symbol=None: (
            [position(ticket=77, comment=sent["comment"])] if "comment" in sent else [])

        found = self.ex._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)
        self.assertEqual(found.ticket, 77)
        self.assertEqual(sent["count"], 1, "resent an order that had filled")

    def test_s07b_unreadable_retcode_is_treated_as_unknown(self):
        class Exploding:
            @property
            def retcode(self):
                raise RuntimeError("corrupt reply")

        self.mt5.order_send.return_value = Exploding()
        self.mt5.positions_get.return_value = []
        with self.assertRaises(RuntimeError) as ctx:
            self.ex._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)
        self.assertIn("unknown", str(ctx.exception).lower())
        self.assertEqual(self.mt5.order_send.call_count, 1)

    # 8 -------------------------------------------------------------------
    def test_s08_news_api_hang_is_bounded(self):
        import utils.news_reader as nr
        with patch.object(nr, "NEWS_API_KEY", "k"), \
                patch.object(nr.requests, "get",
                             side_effect=nr.requests.exceptions.Timeout()) as get:
            outcome = nr.get_latest_forex_news(force=True)
        self.assertEqual(get.call_args.kwargs["timeout"], nr.REQUEST_TIMEOUT)
        self.assertFalse(outcome["available"])

    # 9 -------------------------------------------------------------------
    def test_s09_fok_only_broker_adapts_and_repeated_rejection_halts(self):
        """Every order returns 10030. Expected: adapt the filling mode; if
        rejections continue, halt and alert rather than loop silently."""
        from execution.order_validator import choose_filling_mode
        mt5 = fake_mt5()
        self.assertEqual(choose_filling_mode(mt5, gold_spec(filling_modes=1)),
                         mt5.ORDER_FILLING_FOK)

        self.mt5.order_send.return_value = result(10030)
        breaker = CircuitBreaker(threshold=5)
        for _ in range(5):
            try:
                self.ex._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)
            except RuntimeError as exc:
                breaker.record_failure(exc)
        self.assertEqual(self.mt5.order_send.call_count, 5,
                         "10030 is not retryable: one send per attempt")
        self.assertTrue(breaker.is_tripped)

    # 10 ------------------------------------------------------------------
    def test_s10_partial_fill_is_detected(self):
        self.mt5.order_send.return_value = result(10009, volume=0.04)
        with self.assertLogs("xau_bot", level="WARNING") as logs:
            self.ex._place_market_order("XAUUSD", True, 0.1, 1990.0, 2020.0)
        self.assertTrue(any("PARTIAL FILL" in line for line in logs.output))

    # 11 ------------------------------------------------------------------
    def test_s11_restart_cannot_add_exposure(self):
        """Restart after two scale-ups. Expected: no further scaling.

        Scaling was deleted (no live caller), so there is no allowance to
        refill; a restart with a held position still respects the entry cap.
        """
        held = position(ticket=11)
        self.mt5.positions_get.return_value = [held]
        reborn = make_executor(self.mt5, self.config, fake_risk_manager(
            current_open_positions_count=MagicMock(return_value=1)))
        self.assertFalse(hasattr(reborn, "may_scale"))
        with self.assertRaises(RuntimeError):
            reborn.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0, 2020.0, volume=0.1)

    # 12 ------------------------------------------------------------------
    def test_s12_thirty_bars_of_history_refuses_to_signal(self):
        from data.quality import DataQualityError, check_bar_count, required_warmup_bars
        bars = pd.DataFrame({"close": np.linspace(2000, 2001, 30)})
        with self.assertRaises(DataQualityError):
            check_bar_count(bars, required_warmup_bars(26, 14, 20, 14))

    # 13 ------------------------------------------------------------------
    def test_s13_indicator_columns_follow_a_changed_rsi_period(self):
        from data.quality import check_indicator_columns
        from strategies.strategy_basic import BasicTradingStrategy
        rng = np.random.default_rng(1)
        close = 2000 + np.cumsum(rng.normal(0, 1, 300))
        df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                           "close": close})
        prepared = BasicTradingStrategy(ema_fast=12, ema_slow=26, rsi_period=21,
                                        bb_period=20, bb_std=2.0).prepare_data(df)
        self.assertTrue(check_indicator_columns(prepared, ["RSI_21"]))
        self.assertNotIn("RSI_14", prepared.columns)

    # 14 ------------------------------------------------------------------
    def test_s14_duplicate_or_out_of_order_bars_are_rejected(self):
        from data.quality import DataQualityError, validate_for_trading
        index = pd.date_range("2026-01-05", periods=50, freq="5min", tz="UTC")
        good = pd.DataFrame({"open": 2000.0, "high": 2001.0, "low": 1999.0,
                             "close": 2000.5}, index=index)
        with self.assertRaises(DataQualityError):
            validate_for_trading(pd.concat([good, good.iloc[[10]]]), 300,
                                 check_staleness=False)
        with self.assertRaises(DataQualityError):
            validate_for_trading(good.iloc[::-1], 300, check_staleness=False)

    # 15 ------------------------------------------------------------------
    def test_s15_dst_shifts_the_new_york_session(self):
        """US clocks change. Expected: sessions shift with them.

        Was a known gap (fixed UTC hours). In July 12:45 UTC is 08:45 in New
        York, so it is the overlap; in January it is 07:45, so plain London.
        """
        rm, _ = self.risk_manager()
        july = datetime(2026, 7, 15, 12, 45, tzinfo=timezone.utc)
        with patch("risk.risk_manager.datetime") as fake_dt:
            fake_dt.now.return_value = july
            self.assertEqual(rm.get_current_market_session(), "London/NY overlap")
        january = datetime(2026, 1, 15, 12, 45, tzinfo=timezone.utc)
        with patch("risk.risk_manager.datetime") as fake_dt:
            fake_dt.now.return_value = january
            self.assertEqual(rm.get_current_market_session(), "London")

    # 16 ------------------------------------------------------------------
    def test_s16_default_config_is_flat_before_the_weekend(self):
        """$8 Sunday gap through a stop. Expected: flat before the weekend.

        Was a known gap: SESSION_END_CLOSE defaulted to False. Now on.
        """
        import importlib, config
        importlib.reload(config)
        self.assertTrue(config.SESSION_END_CLOSE)

    def test_s16b_session_end_close_works_when_enabled(self):
        import config
        self.ex.config = config
        # Friday 16:50 New York in winter (EST) and in summer (EDT).
        winter = datetime(2026, 1, 9, 21, 50, tzinfo=timezone.utc)
        summer = datetime(2026, 7, 10, 20, 50, tzinfo=timezone.utc)
        summer_early = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
        with patch.object(config, "SESSION_END_BUFFER_MINUTES", 15):
            self.assertTrue(self.ex._check_market_session_end(winter))
            self.assertTrue(self.ex._check_market_session_end(summer))
            self.assertFalse(self.ex._check_market_session_end(summer_early))

    # 17 ------------------------------------------------------------------
    def test_s17_extreme_atr_cuts_size_sharply(self):
        """ATR 25 on M5. Expected: size reduced sharply.

        Audit: 25 fell between the absolute thresholds, multiplier 1.0, size
        unchanged. Sizing is now risk / (contract x stop), and the stop is ATR-
        based, so size scales inversely with volatility.
        """
        rm, _ = self.risk_manager(equity=10000.0)
        calm = rm.calculate_dynamic_lot_size(rm.calculate_dynamic_sl_distance(2000, 2.5, 2.0))
        wild = rm.calculate_dynamic_lot_size(rm.calculate_dynamic_sl_distance(2000, 25.0, 2.0))
        self.assertIsNotNone(calm)
        self.assertTrue(wild is None or wild <= calm / 9.0,
                        "calm=%s wild=%s" % (calm, wild))

    # 18 ------------------------------------------------------------------
    def test_s18_near_zero_volatility_stop_respects_broker_minimum(self):
        """ATR 0.3. Expected: widen the stop to the broker's minimum distance.

        Audit: a $0.15-0.90 stop inside trade_stops_level -> retcode 10016 ->
        silent outage.
        """
        spec = gold_spec(stops_level_points=100)          # $1.00 minimum
        sl, _ = enforce_stops_level(spec, price=2000.0, sl=2000.0 - 0.6,
                                    tp=None, is_buy=True)
        self.assertLessEqual(sl, 1999.0)
        self.assertIsNotNone(sl, "the stop must never be dropped")

    # 19 ------------------------------------------------------------------
    def test_s19_ten_losers_in_a_row_halt_entries(self):
        store = PositionStateStore(self.db)
        base = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)
        self.mt5.history_deals_get.return_value = [MagicMock(
            ticket=i + 1, position_id=i, order=i, symbol="XAUUSD", type=1,
            entry=1, volume=0.1, price=2000.0, profit=-10.0, commission=0.0,
            swap=0.0, time=(base + timedelta(minutes=5 * i)).timestamp(),
            comment="") for i in range(10)]
        store.sync_deals(self.mt5, since=base - timedelta(days=1),
                         until=base + timedelta(days=1))
        self.assertEqual(store.consecutive_losses(), 10)
        with self.assertRaises(RuntimeError) as ctx:
            self.ex.enter_trade("XAUUSD", "BUY", 2000.0, 1990.0, 2020.0)
        self.assertIn("Loss-streak", str(ctx.exception))

    # 20 ------------------------------------------------------------------
    def test_s20_forty_percent_drawdown_halts_and_triggers_emergency_close(self):
        """Equity -40%. Expected: flatten and stop.

        Audit: compared balance to a hardcoded $150.
        """
        rm, mt5 = self.risk_manager(equity=10000.0)
        rm.state = RiskState(os.path.join(self.dir, "dd.json"))
        rm.check_drawdown()                                    # peak = 10,000
        mt5.account_info.return_value = MagicMock(balance=6000.0, equity=6000.0,
                                                  profit=0.0, margin_free=6000.0)
        self.assertFalse(rm.check_drawdown())
        self.assertIsNotNone(rm.state.halted_reason)
        self.assertGreaterEqual(rm.state.drawdown_fraction(6000.0),
                                self.config.EMERGENCY_CLOSE_DRAWDOWN_FRACTION)

    # 21 ------------------------------------------------------------------
    def test_s21_deposit_recomputes_limits_from_new_equity(self):
        rm, mt5 = self.risk_manager(equity=10000.0)
        rm.state = RiskState(os.path.join(self.dir, "dep.json"))
        before = rm.calculate_dynamic_lot_size(10.0)
        mt5.account_info.return_value = MagicMock(balance=20000.0, equity=20000.0,
                                                  profit=0.0, margin_free=20000.0)
        after = rm.calculate_dynamic_lot_size(10.0)
        self.assertAlmostEqual(after, before * 2, places=2)
        rm.state.observe_equity(20000.0)
        self.assertEqual(rm.state.equity_high_water_mark, 20000.0)

    # 22 ------------------------------------------------------------------
    def test_s22_limit_stays_tripped_when_floating_pnl_recovers(self):
        """Floating -50% then +20%. Expected: consistent evaluation.

        Audit: the check flipped between blocking and permitting on floating
        P&L alone. A breach now latches.
        """
        rm, mt5 = self.risk_manager(equity=10000.0)
        rm.state = RiskState(os.path.join(self.dir, "dl.json"))
        mt5.account_info.return_value = MagicMock(balance=10000.0, equity=5000.0,
                                                  profit=-5000.0, margin_free=5000.0)
        self.assertFalse(rm.check_daily_loss_limit())
        mt5.account_info.return_value = MagicMock(balance=10000.0, equity=12000.0,
                                                  profit=2000.0, margin_free=12000.0)
        self.assertFalse(rm.check_daily_loss_limit(),
                         "a breached daily limit un-tripped on floating recovery")

    # 23 ------------------------------------------------------------------
    def test_s23_margin_exhaustion_is_refused_before_the_broker(self):
        """Expected: refuse new orders before the broker does."""
        self.mt5.order_calc_margin.return_value = 5000.0
        self.mt5.account_info.return_value = MagicMock(margin_free=1000.0)
        with self.assertRaises(RuntimeError) as ctx:
            self.ex._place_market_order("XAUUSD", True, 1.0, 1990.0, 2020.0)
        self.assertIn("margin", str(ctx.exception).lower())
        self.mt5.order_send.assert_not_called()

    # 24 ------------------------------------------------------------------
    def test_s24a_no_stop_modification_is_attempted_under_current_config(self):
        """SL modification fails. Under the current configuration (trailing and
        break-even off, user decision) no modification is ever sent, so the
        failure path cannot be reached."""
        self.assertFalse(self.config.TRAILING_STOP_ENABLED)
        self.assertFalse(self.config.BREAK_EVEN_ENABLED)
        self.mt5.positions_get.return_value = [position(profit=500.0)]
        self.assertEqual(self.ex.manage_open_positions("XAUUSD", atr=3.0), 0)
        self.mt5.order_send.assert_not_called()

    def test_s24b_failed_stop_modification_is_retried_then_escalated(self):
        """Was a known gap: modify_trade_sl logged 10016 and gave up silently.
        It now retries, then escalates (CRITICAL log + stop_failures)."""
        self.ex._stop_retry_delay = 0
        self.mt5.order_send.return_value = MagicMock(retcode=10016, comment="Invalid stops")
        self.mt5.symbol_info.return_value = fake_symbol_info(trade_stops_level=0)
        breaker_calls = []
        with patch.object(self.ex, "_escalate_stop_failure",
                          side_effect=lambda *args: breaker_calls.append(args)):
            self.ex.modify_trade_sl(position(price_current=2050.0), 2030.0)
        self.assertGreaterEqual(self.mt5.order_send.call_count, 2)
        self.assertTrue(breaker_calls)

    def test_s24c_escalation_is_recorded(self):
        self.ex._stop_retry_delay = 0
        self.mt5.order_send.return_value = MagicMock(retcode=10016, comment="Invalid stops")
        self.mt5.symbol_info.return_value = fake_symbol_info(trade_stops_level=0)
        with self.assertLogs("xau_bot", level="CRITICAL"):
            self.assertFalse(self.ex.modify_trade_sl(position(price_current=2050.0), 2030.0))
        self.assertEqual(len(self.ex.stop_failures), 1)

    def test_s24d_transient_failure_then_success(self):
        self.ex._stop_retry_delay = 0
        self.mt5.order_send.side_effect = [MagicMock(retcode=10004, comment="Requote"),
                                           MagicMock(retcode=10009, comment="done")]
        self.mt5.symbol_info.return_value = fake_symbol_info(trade_stops_level=0)
        self.assertTrue(self.ex.modify_trade_sl(position(price_current=2050.0), 2030.0))
        self.assertEqual(self.ex.stop_failures, [])

    # 25 ------------------------------------------------------------------
    def test_s25_take_profit_is_never_modified_client_side(self):
        """TP modification fails. By design there is no TP modification path:
        the target sent at entry is held server-side, and client-side TP/SL
        checks were deleted in Phase 5.6."""
        import ast, inspect, textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(
            type(self.ex).should_close_trade)))
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertNotIn("_check_take_profit_reached", called)
        self.assertNotIn("_check_stop_loss_hit", called)


if __name__ == "__main__":
    unittest.main()
