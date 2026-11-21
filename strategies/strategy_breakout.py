"""Breakout / volatility-expansion strategy (Hypothesis 2).

Pre-registered in docs/STRATEGY-HYPOTHESIS.md BEFORE this was backtested.
Mechanism is deliberately different from strategy_basic.py's EMA-state
follower (Hypothesis 1), which failed Gate C on both M5 and 17 years of H1
data.

Enters when price closes outside its recent N-bar trading range AT THE SAME
TIME volatility is expanding (current ATR above its own recent median).
Neither condition alone is a signal. Exits, sizing and entry gating are the
unmodified shared modules (strategies/trade_plan.py, strategies/exit_rules.py)
-- only the signal and the reversal detector are strategy-specific, so a
comparison against Hypothesis 1 isolates the mechanism, not the risk
management around it.

NOT the live default. main.py still instantiates BasicTradingStrategy;
switching the live bot to this strategy is a decision for after it has
passed Gate C, not before.
"""

from indicators.rsi import add_rsi_signals


class BreakoutStrategy:
    """Donchian-channel breakout confirmed by ATR expansion."""

    def __init__(self, channel_period=20, atr_expansion_min=1.1, rsi_period=14):
        self.channel_period = int(channel_period)
        self.atr_expansion_min = float(atr_expansion_min)
        self.rsi_period = int(rsi_period)

    def prepare_data(self, data):
        """Add the channel and its state. Requires an 'ATR' column already
        present for generate_signal/detect_trend_reversal to see volatility --
        added by the caller the same way strategy_basic.py's callers do
        (main.py, backtest/live_engine.py's prepare_frame)."""
        df = data.copy()
        df = add_rsi_signals(df, self.rsi_period)

        # The channel EXCLUDES the current bar: shift(1) before rolling. A bar
        # can never break a range that includes itself -- the same mistake
        # Phase 5.3 fixed for break_of_structure (audit M-01).
        df['channel_high'] = df['high'].shift(1).rolling(self.channel_period).max()
        df['channel_low'] = df['low'].shift(1).rolling(self.channel_period).min()

        # Channel STATE, mirroring strategy_basic's EMA_signal: +1 above the
        # channel, -1 below, 0 inside. detect_trend_reversal reads this the
        # same way strategy_basic reads EMA_signal.
        df['channel_state'] = 0
        df.loc[df['close'] > df['channel_high'], 'channel_state'] = 1
        df.loc[df['close'] < df['channel_low'], 'channel_state'] = -1
        return df

    def generate_signal(self, data):
        """BUY/SELL only on a channel breakout confirmed by ATR expansion."""
        min_bars = max(self.channel_period, self.rsi_period) + 2
        empty = {
            'signal': 'HOLD', 'strength': 0, 'reasons': [],
            'components': {'channel_state': 0, 'atr_ratio': None, 'rsi_condition': 'neutral'},
        }
        if len(data) < min_bars:
            empty['reasons'] = ['Not enough data']
            return empty

        latest = data.iloc[-1]
        close = float(latest['close'])
        upper = latest.get('channel_high')
        lower = latest.get('channel_low')
        if upper is None or lower is None or upper != upper or lower != lower:
            empty['reasons'] = ['Channel not yet formed']
            return empty

        from strategies.trade_plan import atr_ratio as _atr_ratio
        atr_val = float(latest.get('ATR')) if 'ATR' in data.columns and latest.get('ATR') == latest.get('ATR') else None
        ratio = _atr_ratio(data['ATR'].tolist()) if 'ATR' in data.columns else None

        breakout_up = close > upper
        breakout_down = close < lower
        expanding = ratio is not None and ratio >= self.atr_expansion_min

        rsi_val = latest.get('RSI_%d' % self.rsi_period, 50)
        rsi_condition = "bullish" if rsi_val < 30 else ("bearish" if rsi_val > 70 else "neutral")
        channel_state = int(latest.get('channel_state', 0) or 0)

        signal, reasons = 'HOLD', []
        if breakout_up and expanding:
            signal = 'BUY'
            reasons.append("Close above %d-bar high with expanding volatility "
                           "(ATR ratio %.2f)" % (self.channel_period, ratio))
        elif breakout_down and expanding:
            signal = 'SELL'
            reasons.append("Close below %d-bar low with expanding volatility "
                           "(ATR ratio %.2f)" % (self.channel_period, ratio))
        elif breakout_up or breakout_down:
            reasons.append("Range breakout without volatility expansion -- no signal")
        else:
            reasons.append("Inside the %d-bar range" % self.channel_period)

        strength = 0.0
        if signal in ('BUY', 'SELL') and atr_val and atr_val > 0:
            distance = (close - upper) if signal == 'BUY' else (lower - close)
            distance_score = min(max(distance / atr_val, 0.0), 2.0) / 2.0
            expansion_score = min(max((ratio or 1.0) - 1.0, 0.0), 1.0)
            strength = round(100.0 * (0.6 * distance_score + 0.4 * expansion_score), 1)

        return {
            'signal': signal,
            'strength': strength,
            'reasons': reasons,
            'components': {
                'channel_state': channel_state,
                # 'ema_signal' is strategy_basic's key for direction/trend
                # state; strategies/trade_plan.py reads it generically as
                # trend_strength for the stop/target multipliers. Aliased here
                # so a breakout has the same trend-alignment effect an EMA
                # state would.
                'ema_signal': channel_state,
                'atr_ratio': ratio,
                'rsi_condition': rsi_condition,
            },
        }

    def detect_trend_reversal(self, data):
        """Channel-state flip between the last two bars.

        Same two-bar state-change mechanism strategy_basic.py uses for its
        EMA_signal reversal -- required so strategies/exit_rules.py's
        TREND_REVERSAL_CLOSE factor works unchanged for this strategy too.
        """
        no_reversal = {'reversal_detected': False, 'direction': None, 'strength': 0}
        if 'channel_state' not in data.columns or len(data) < 2:
            return no_reversal

        states = data['channel_state'].tail(2).values
        prev_state, current_state = states[0], states[-1]
        if current_state != prev_state and current_state != 0:
            return {
                'reversal_detected': True,
                'direction': 'bullish_to_bearish' if current_state == -1 else 'bearish_to_bullish',
                'strength': 70,
            }
        return no_reversal
