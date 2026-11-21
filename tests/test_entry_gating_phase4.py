"""Phase 4 tests: one position per decision, one decision per closed bar.

The two facts the plan asks to prove:

  * order_send(TRADE_ACTION_DEAL) never exceeds the position cap, and never
    exceeds one per bar timestamp;
  * five evaluations of one M5 bar produce exactly one entry.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.bar_gate import BarGate, timeframe_seconds


def bars(n, start="2026-01-05 08:00:00", minutes=5):
    """A UTC DatetimeIndex of n closed M5 bars."""
    t0 = pd.Timestamp(start, tz="UTC")
    return pd.DatetimeIndex([t0 + timedelta(minutes=minutes * i) for i in range(n)])


class TestTimeframeSeconds(unittest.TestCase):
    def test_known_timeframes(self):
        self.assertEqual(timeframe_seconds("M5"), 300)
        self.assertEqual(timeframe_seconds("H1"), 3600)
        self.assertEqual(timeframe_seconds("m15"), 900)

    def test_unknown_timeframe_raises_rather_than_guessing(self):
        # The old code assumed a 5-minute bar in two places. Guessing the bar
        # length is how MIN_SIGNAL_HOLD became wrong on every other timeframe.
        with self.assertRaises(ValueError):
            timeframe_seconds("M7")


class TestOneEntryPerBar(unittest.TestCase):
    """4.3: five evaluations of one M5 bar produce exactly one entry."""

    def test_five_evaluations_of_one_bar_yield_one_entry(self):
        gate = BarGate("M5")
        bar = pd.Timestamp("2026-01-05 08:00:00", tz="UTC")

        entries = 0
        for _ in range(5):              # 60s loop over a 300s bar
            if gate.may_enter(bar):
                entries += 1
                gate.record_entry(bar)
        self.assertEqual(entries, 1)

    def test_a_new_bar_permits_a_new_entry(self):
        gate = BarGate("M5")
        taken = 0
        for bar in bars(3):
            if gate.may_enter(bar):
                taken += 1
                gate.record_entry(bar)
        self.assertEqual(taken, 3)

    def test_missing_bar_timestamp_refuses_entry(self):
        self.assertFalse(BarGate("M5").may_enter(None))


class TestReversalHold(unittest.TestCase):
    """The gate ported from run_bot.py, with its unit bug fixed."""

    def setUp(self):
        self.gate = BarGate("M5")
        self.bars = bars(20)

    def _seed(self, signal, bar):
        return self.gate.apply_reversal_hold(signal, 99.0, bar, 80.0, 5)

    def test_weak_reversal_is_ignored(self):
        self._seed("BUY", self.bars[0])
        held = self.gate.apply_reversal_hold("SELL", 70.0, self.bars[10], 80.0, 5)
        # Not "BUY": re-issuing the old signal on a bar that says SELL would
        # enter against the current bar at the SELL reading's strength.
        self.assertEqual(held, "HOLD")
        self.assertEqual(self.gate.last_signal, "BUY")

    def test_strong_reversal_after_the_hold_is_accepted(self):
        self._seed("BUY", self.bars[0])
        out = self.gate.apply_reversal_hold("SELL", 95.0, self.bars[10], 80.0, 5)
        self.assertEqual(out, "SELL")

    def test_strong_but_hasty_reversal_is_ignored(self):
        self._seed("BUY", self.bars[0])
        out = self.gate.apply_reversal_hold("SELL", 95.0, self.bars[2], 80.0, 5)
        self.assertEqual(out, "HOLD")

    def test_hold_is_counted_in_bars_not_seconds(self):
        # The original compared elapsed seconds against min_hold * 300, which
        # hardcodes an M5 bar. On H1 that is 25 minutes instead of 5 hours.
        gate = BarGate("H1")
        hourly = bars(10, minutes=60)
        gate.apply_reversal_hold("BUY", 99.0, hourly[0], 80.0, 5)
        # 3 hours later: still inside a 5-BAR hold, though far past 1500s.
        out = gate.apply_reversal_hold("SELL", 95.0, hourly[3], 80.0, 5)
        self.assertEqual(out, "HOLD")
        self.assertGreater((hourly[3] - hourly[0]).total_seconds(), 5 * 300)

    def test_continuing_the_same_signal_is_untouched(self):
        self._seed("BUY", self.bars[0])
        self.assertEqual(
            self.gate.apply_reversal_hold("BUY", 50.0, self.bars[1], 80.0, 5),
            "BUY")

    def test_hold_signal_passes_through(self):
        self.assertEqual(
            self.gate.apply_reversal_hold("HOLD", 10.0, self.bars[0], 80.0, 5),
            "HOLD")


class TestBarCloseAlignment(unittest.TestCase):
    def test_waits_until_the_next_bar_boundary(self):
        gate = BarGate("M5")
        # 08:02:00 UTC -> 180s to 08:05:00, plus the 2s settle margin.
        epoch = pd.Timestamp("2026-01-05 08:02:00", tz="UTC").timestamp()
        self.assertAlmostEqual(gate.seconds_until_next_bar(epoch), 182.0)

    def test_never_returns_a_zero_or_negative_wait(self):
        gate = BarGate("M5")
        for offset in range(0, 300, 7):
            epoch = pd.Timestamp("2026-01-05 08:00:00", tz="UTC").timestamp() + offset
            self.assertGreater(gate.seconds_until_next_bar(epoch), 0)

    def test_exactly_on_a_boundary_waits_a_whole_bar(self):
        gate = BarGate("M5")
        epoch = pd.Timestamp("2026-01-05 08:05:00", tz="UTC").timestamp()
        self.assertAlmostEqual(gate.seconds_until_next_bar(epoch), 302.0)


class TestFormingBarIsDropped(unittest.TestCase):
    """4.2: the still-forming bar must never reach a trading decision."""

    def _mt5_with(self, rows):
        mt5 = MagicMock()
        mt5.initialize.return_value = True
        mt5.account_info.return_value = MagicMock()
        mt5.symbol_info.return_value = MagicMock(visible=True)
        mt5.copy_rates_from_pos.return_value = rows
        return mt5

    def _rates(self, n):
        import numpy as np
        base = int(pd.Timestamp("2026-01-05 08:00:00", tz="UTC").timestamp())
        return np.array(
            [(base + 300 * i, 1., 2., 0.5, 1.5, 10, 1, 0) for i in range(n)],
            dtype=[("time", "<i8"), ("open", "<f8"), ("high", "<f8"),
                   ("low", "<f8"), ("close", "<f8"), ("tick_volume", "<i8"),
                   ("spread", "<i4"), ("real_volume", "<i8")])

    def test_last_row_is_dropped_by_default(self):
        import data.fetch_candles as fc
        real = fc.mt5
        fc.mt5 = self._mt5_with(self._rates(11))
        try:
            df = fc.get_candles("XAUUSDm", 5, num_candles=10)
        finally:
            fc.mt5 = real
        self.assertEqual(len(df), 10)
        # The 11th (forming) bar's timestamp must not be present. MT5 stamps
        # bars in server time (New York + 7 h); in January that is UTC+2.
        self.assertEqual(df.index[-1],
                         pd.Timestamp("2026-01-05 06:45:00", tz="UTC"))

    def test_display_callers_can_keep_the_forming_bar(self):
        import data.fetch_candles as fc
        real = fc.mt5
        fc.mt5 = self._mt5_with(self._rates(10))
        try:
            df = fc.get_candles("XAUUSDm", 5, num_candles=10,
                                drop_forming_bar=False)
        finally:
            fc.mt5 = real
        self.assertEqual(len(df), 10)

    def test_count_based_fetch_is_used_not_a_date_window(self):
        # copy_rates_range with a locally computed window assumed an M5 bar
        # and mixed local time with broker time (audit H-09).
        import data.fetch_candles as fc
        real = fc.mt5
        mock = self._mt5_with(self._rates(11))
        fc.mt5 = mock
        try:
            fc.get_candles("XAUUSDm", 5, num_candles=10)
        finally:
            fc.mt5 = real
        mock.copy_rates_from_pos.assert_called_once()
        mock.copy_rates_range.assert_not_called()


class TestLoopRespectsTheCap(unittest.TestCase):
    """4.3: entries never exceed the cap, nor one per bar timestamp."""

    def test_synthetic_trend_never_exceeds_cap_or_one_per_bar(self):
        cap = 1
        gate = BarGate("M5")
        open_positions = []
        deals = []

        # A strong uptrend: every bar says BUY at full strength, and the loop
        # evaluates each bar five times (a 60s loop over 300s bars).
        for bar in bars(40):
            for _ in range(5):
                signal = gate.apply_reversal_hold("BUY", 95.0, bar, 80.0, 5)
                if signal not in ("BUY", "SELL"):
                    continue
                if 95.0 < 65.0:
                    continue
                if len(open_positions) >= cap:
                    continue
                if not gate.may_enter(bar):
                    continue
                deals.append(bar)
                gate.record_entry(bar)
                open_positions.append(bar)

        self.assertLessEqual(len(open_positions), cap,
                             "position cap exceeded")
        self.assertEqual(len(deals), len(set(deals)),
                         "more than one entry for a single bar timestamp")
        self.assertEqual(len(deals), 1)

    def test_cap_frees_up_as_positions_close(self):
        cap = 1
        gate = BarGate("M5")
        open_positions = []
        deals = []

        for i, bar in enumerate(bars(10)):
            if i % 3 == 0:
                open_positions.clear()          # previous position closed
            if len(open_positions) < cap and gate.may_enter(bar):
                deals.append(bar)
                gate.record_entry(bar)
                open_positions.append(bar)

        self.assertEqual(len(deals), len(set(deals)))
        self.assertEqual(len(deals), 4)         # bars 0, 3, 6, 9


class TestConfigCaps(unittest.TestCase):
    def test_position_cap_was_reduced_from_100(self):
        import config
        self.assertLessEqual(config.MAX_CONCURRENT_POSITIONS, 1)
        self.assertEqual(config.MAX_OPEN_TRADES, config.MAX_CONCURRENT_POSITIONS)

    def test_entry_strength_floor_exists(self):
        import config
        self.assertGreater(config.MIN_ENTRY_STRENGTH, 0)

    def test_main_no_longer_shadows_the_cap(self):
        import main
        self.assertFalse(hasattr(main, "MAX_OPEN_TRADES"),
                         "main.py shadows config.MAX_OPEN_TRADES again")

    def test_dead_gated_loop_is_gone(self):
        import main
        self.assertFalse(hasattr(main, "main_loop_legacy_gated"))


if __name__ == "__main__":
    unittest.main()
