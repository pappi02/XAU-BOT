"""Trend following with a regime filter (Hypothesis 3).

Pre-registered in docs/STRATEGY-HYPOTHESIS.md BEFORE this was backtested.

Mechanism, deliberately different from strategy_basic.py (Hypothesis 1, an
EMA-state follower) and strategy_breakout.py (Hypothesis 2, a breakout AND
volatility-expansion conjunction): trade a 20-bar Donchian breakout ONLY in
the direction of a 200-bar trend filter. This is one condition doing what
Hypothesis 2 needed two independent conditions for, and it is closer to what
published trend-following systems (Donchian, the Turtles' 55/20-day variants,
most CTA trend models since) actually do: "trade breakouts, but only with the
tide."

The mechanism this module is actually testing is not the entry -- it is the
EXIT, implemented in backtest/live_engine.py as an ATR chandelier trailing
stop with no fixed take-profit. That is genuinely new infrastructure, not
just a new signal; see docs/STRATEGY-HYPOTHESIS.md for why Hypotheses 1 and 2
could never have shown a trend-following edge regardless of their entries,
because both capped every winner at a fixed multiple of the initial risk.

NOT the live default, and this backtest-only trailing exit cannot become one:
TRAILING_STOP_ENABLED stays off for live trading regardless of this result.
"""

from indicators.ema import calculate_ema
from indicators.rsi import add_rsi_signals


class TrendFollowingStrategy:
    """20-bar Donchian breakout, taken only with a 200-bar trend filter."""

    def __init__(self, trend_period=200, channel_period=20, rsi_period=14):
        self.trend_period = int(trend_period)
        self.channel_period = int(channel_period)
        self.rsi_period = int(rsi_period)

    def prepare_data(self, data):
        """Add the trend filter, the channel and their states.

        Requires an 'ATR' column already present, added by the caller the
        same way every strategy's callers do (main.py,
        backtest/live_engine.py's prepare_frame).
        """
        df = data.copy()
        df = add_rsi_signals(df, self.rsi_period)

        df['EMA_trend'] = calculate_ema(df, self.trend_period)
        df['trend_regime'] = 0
        df.loc[df['close'] > df['EMA_trend'], 'trend_regime'] = 1
        df.loc[df['close'] < df['EMA_trend'], 'trend_regime'] = -1

        # The channel EXCLUDES the current bar: shift(1) before rolling, same
        # fix as strategy_breakout.py and Phase 5.3's break_of_structure --
        # a bar can never break a range that includes itself.
        df['channel_high'] = df['high'].shift(1).rolling(self.channel_period).max()
        df['channel_low'] = df['low'].shift(1).rolling(self.channel_period).min()
        return df

    def generate_signal(self, data):
        """BUY/SELL only on a channel breakout WITH the trend-filter regime."""
        min_bars = max(self.trend_period, self.channel_period, self.rsi_period) + 2
        empty = {
            'signal': 'HOLD', 'strength': 0, 'reasons': [],
            'components': {'trend_regime': 0, 'ema_signal': 0, 'rsi_condition': 'neutral'},
        }
        if len(data) < min_bars:
            empty['reasons'] = ['Not enough data']
            return empty

        latest = data.iloc[-1]
        close = float(latest['close'])
        upper, lower = latest.get('channel_high'), latest.get('channel_low')
        regime = int(latest.get('trend_regime', 0) or 0)
        if upper is None or lower is None or upper != upper or lower != lower:
            empty['reasons'] = ['Channel not yet formed']
            return empty

        atr_val = float(latest.get('ATR')) if 'ATR' in data.columns and latest.get('ATR') == latest.get('ATR') else None
        rsi_val = latest.get('RSI_%d' % self.rsi_period, 50)
        rsi_condition = "bullish" if rsi_val < 30 else ("bearish" if rsi_val > 70 else "neutral")

        signal, reasons = 'HOLD', []
        if regime == 1 and close > upper:
            signal = 'BUY'
            reasons.append("Close above %d-bar high with price above the "
                           "%d-bar trend filter" % (self.channel_period, self.trend_period))
        elif regime == -1 and close < lower:
            signal = 'SELL'
            reasons.append("Close below %d-bar low with price below the "
                           "%d-bar trend filter" % (self.channel_period, self.trend_period))
        elif close > upper or close < lower:
            reasons.append("Breakout against the trend filter -- no signal")
        else:
            reasons.append("Inside the %d-bar range" % self.channel_period)

        strength = 0.0
        if signal in ('BUY', 'SELL') and atr_val and atr_val > 0:
            distance = (close - upper) if signal == 'BUY' else (lower - close)
            trend_distance = abs(close - float(latest['EMA_trend'])) / atr_val
            distance_score = min(max(distance / atr_val, 0.0), 2.0) / 2.0
            trend_score = min(max(trend_distance / 5.0, 0.0), 1.0)
            strength = round(100.0 * (0.7 * distance_score + 0.3 * trend_score), 1)

        return {
            'signal': signal,
            'strength': strength,
            'reasons': reasons,
            'components': {
                'trend_regime': regime,
                # Alias for strategies/trade_plan.py, which reads
                # components['ema_signal'] generically as trend_strength.
                'ema_signal': regime,
                'rsi_condition': rsi_condition,
            },
        }

    def detect_trend_reversal(self, data):
        """Trend-filter regime flip between the last two bars.

        Same two-bar state-change mechanism strategy_basic.py and
        strategy_breakout.py use -- this IS the intended exit trigger for
        this hypothesis (strategies/exit_rules.py's trend_reversal factor),
        not a secondary signal.
        """
        no_reversal = {'reversal_detected': False, 'direction': None, 'strength': 0}
        if 'trend_regime' not in data.columns or len(data) < 2:
            return no_reversal

        states = data['trend_regime'].tail(2).values
        prev_state, current_state = states[0], states[-1]
        if current_state != prev_state and current_state != 0:
            return {
                'reversal_detected': True,
                'direction': 'bullish_to_bearish' if current_state == -1 else 'bearish_to_bullish',
                'strength': 70,
            }
        return no_reversal
