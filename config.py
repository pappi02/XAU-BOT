# Configuration file for XAU Bot
# Add your API keys, settings, etc. here

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
# No fallback -- the previous hardcoded default was a real key that leaked
# (audit H-10). An unset OR empty value normalises to None so that
# `NEWS_API_KEY=` in .env means "absent", not the empty string.
# Get one at https://newsapi.org/
NEWS_API_KEY = os.getenv('NEWS_API_KEY') or None

# MT5 Settings
MT5_ACCOUNT = os.getenv('MT5_ACCOUNT')
if MT5_ACCOUNT in [None, '', 'None']:
    MT5_ACCOUNT = None
else:
    # An MT5 login is always a number. A non-numeric value here is almost
    # always a password pasted into the wrong field -- say so plainly instead
    # of raising a bare ValueError from int(), and never echo the value.
    _raw = MT5_ACCOUNT.strip()
    if not _raw.isdigit():
        raise ValueError(
            "MT5_ACCOUNT in .env is not numeric (got %d characters of "
            "non-numeric text). An MT5 login is a number like 12345678. "
            "If you pasted your password there by mistake, fix .env -- and "
            "treat that password as exposed." % len(_raw)
        )
    MT5_ACCOUNT = int(_raw)
    del _raw

MT5_PASSWORD = os.getenv('MT5_PASSWORD')
if MT5_PASSWORD in [None, '', 'None']:
    MT5_PASSWORD = None

MT5_SERVER = os.getenv('MT5_SERVER')
if MT5_SERVER in [None, '', 'None']:
    MT5_SERVER = None

MT5_TIMEOUT_MS = 60000  # Connection timeout in milliseconds
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"  # Path to MT5 terminal

# Trading Settings
# TRADE_ACCOUNT_MODE = "live" was deleted in Phase 1.6. It read like a safety
# switch but was not one: its only use was the ternary below, whose two branches
# were the identical string. Demo/live is now decided by the broker account we
# actually connect to and enforced by data.connect_mt5.assert_account_identity()
# against the ALLOW_LIVE environment variable -- not by a config string.
SYMBOL = 'XAUUSD'  # Trading symbol

# Broker server clock. MT5 stamps bars, positions and deals in SERVER time, not
# UTC. Measured for MetaQuotes-Demo from the daily break in 1.43 years of bars:
# server time = New York local time + 7 h (UTC+3 in US summer, UTC+2 in winter).
# Checked against a live tick at startup. See utils/market_time.py.
BROKER_SERVER_TZ = 'America/New_York'
BROKER_SERVER_SHIFT_HOURS = 7.0
SYMBOL_PHASE5 = SYMBOL
# CONTRACT_SIZE was DELETED in Phase 2.1 (audit C-04). It was defined twice --
# 100.0 (correct for gold) and 100000 (the FX convention, which silently won),
# making every money conversion wrong by 1000x. Contract size is a fact about
# the broker's contract, not a setting: it is now read from the terminal via
# execution.symbol_spec.SymbolSpec and validated at load.
# Phase 3.1: RISK_PER_TRADE_PCT (0.02, a fraction) and BASE_RISK_PERCENT (1.0,
# a percent) were two contradictory risk settings. Collapsed into ONE, with the
# unit in the name. 0.01 = risk 1% of equity per trade.
RISK_PER_TRADE_FRACTION = 0.01
# Phase 3.3: was MAX_DAILY_LOSS_PCT = 0.60 with the comment "stop trading if
# daily loss > 30%" -- the value and the stated intent disagreed, and 60% is not
# a risk limit. Measured on realised + floating P&L against the DAY'S OPENING
# BALANCE, persisted so a restart cannot reset it.
MAX_DAILY_LOSS_FRACTION = 0.05
# Phase 4.1 (audit C-02): was 100. At that cap the bot could hold ~1.00 lot,
# roughly $400,000 notional, on a $150 account -- the terminal event is a margin
# stop-out, not a stop loss. Start at 1 and justify any increase with Phase 9
# evidence, not intuition.
MAX_CONCURRENT_POSITIONS = 1
MAX_OPEN_TRADES = 1           # loop-level cap; kept equal to the above

# Phase 4.1: entry gates the live loop was missing entirely.
MIN_ENTRY_STRENGTH = 65.0     # minimum signal strength (%) to open a position

# Phase 4.2: a signal reversal must be strong AND the previous signal must have
# been held for a minimum number of BARS (not seconds -- see docs/phase4).
SIGNAL_REVERSAL_MIN_STRENGTH = 80.0
MIN_SIGNAL_HOLD_BARS = 5
# Phase 3.3: was 0, which made enough_balance() unconditionally true.
# Set this to the balance below which you want the bot to stop, in USD.
MIN_ACCOUNT_BALANCE = 50.0
# Phase 3.4: INITIAL_ACCOUNT_BALANCE = 150.0 was deleted. Drawdown is now
# measured from a PERSISTED EQUITY HIGH-WATER MARK (risk/risk_state.py), not a
# constant that read 33% permanently on a $100 account and could never fire on
# a $500 one.
MAX_DRAWDOWN_FRACTION = 0.20      # halt if equity falls this far below its peak
MAX_PORTFOLIO_RISK_FRACTION = 0.04  # total risk across all open positions
# Phase 12.5: halt new entries after this many consecutive LOSING closes,
# counted from broker deals. Sticky until `python main.py --ack-loss-streak`.
MAX_CONSECUTIVE_LOSSES = 5
ORDER_MAX_ATTEMPTS = 3  # Times to retry order_send on failures
ORDER_DEVIATION_POINTS = 20  # Allowed slippage in points
# Phase 2.4: block entries when the spread is wider than this, in BROKER
# POINTS (point = symbol.point, e.g. 0.01). Gold runs 15-35 points in the
# London/NY overlap and 50-100+ in the Asian session and around macro prints.
# Calibrate from the spread logged on each entry decision before tightening.
MAX_ENTRY_SPREAD_POINTS = 50

# Data Settings
TIMEFRAME = 'M5'  # Timeframe: M1, M5, M15, H1, H4, D1, W1, MN
NUM_CANDLES = 1000  # Number of historical candles to fetch

# Strategy Settings
EMA_FAST = 12
EMA_SLOW = 26
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2.0
ATR_PERIOD = 14

# Backtest Settings

# Logging & control (Phase 8)
LOG_LEVEL = 'INFO'
# Consecutive loop failures before trading halts. The audited loop had no
# counter at all, so a broker rejecting every order produced an indefinite
# silent outage that looked exactly like a healthy running bot.
CIRCUIT_BREAKER_THRESHOLD = 5

# Auto-close Settings (Enhanced for Phase 5)
AUTO_CLOSE_ENABLED = True  # Enable automatic position closing


# 2. Trailing Stop
# ==== TRAILING STOP =========================================================
# TRAILING_STOP_ENABLED is the ONE switch that controls trailing. When False,
# no trailing stop is computed and no stop is moved for trailing reasons; the
# position is managed solely by the broker's server-side SL/TP.
#
# OFF by default. Phase 5.2 found that "trailing" previously CLOSED positions at
# market instead of moving their stops (audit C-06), so the behaviour has never
# actually run as intended and its thresholds below have never been validated
# against real data. Turn it on deliberately, ideally after Phase 9 shows it
# helps rather than hurts.
TRAILING_STOP_ENABLED = False
# UNITS: these are PRICE units (USD of gold price movement), not "pips".
# Phase 2.2: the old *_PIPS names were a fiction -- the conversion
# `x / 100000 * CONTRACT_SIZE` was the identity while CONTRACT_SIZE was 100000,
# so the values were always plain price deltas. Renamed so the unit is in the
# name. Phase 5 may re-denominate these into ATR multiples.
TRAIL_START_PRICE = 25.0     # start trailing after $25 of favourable movement
TRAIL_DISTANCE_PRICE = 10.0  # trail $10 behind price

# 3. Opposite Signal
EXIT_REVERSAL_MIN_STRENGTH = 70  # Minimum signal strength for reversal close (percentage)

# 4. Signal Weakening
#
# Phase 12: this factor could never fire -- it required strength < 30 AND the
# "two opposite readings at strength >= 70" confirmation on the same reading.
# It is now satisfiable (two consecutive bars below the threshold), which makes
# it a NEW live exit that no backtest has measured. Off until one does.
SIGNAL_WEAKENING_CLOSE = False
EXIT_WEAKENING_MAX_STRENGTH = 30  # close when strength stays BELOW this for two bars

# 5. News & Economic Events (Phase 10, audit H-05)
#
# NEWS_SENTIMENT_CLOSE is OFF. Averaging headline tone over a
# "gold OR USD OR forex OR XAU" query is ambiguous by construction:
# USD-bullish and gold-bullish are OPPOSITE signals for the same trade. Until
# it demonstrates out-of-sample value (Phase 9), it is noise with a number
# attached. See docs/STRATEGY-HYPOTHESIS.md.
NEWS_SENTIMENT_CLOSE = False
# Headline sentiment is also OFF for entries: it no longer vetoes an opposing
# signal or changes the stop/target. Phase 10 recorded it as off, but main.py
# still applied it -- and no historical headlines exist to backtest it.
NEWS_SENTIMENT_TRADING_ENABLED = False

# The economic calendar DOES have a defensible rationale, independent of any
# edge: gold reprices violently on CPI/NFP/FOMC, and in those seconds the
# spread widens and stops slip. This is risk avoidance, not signal.
ECONOMIC_CALENDAR_ENABLED = True
ECONOMIC_CALENDAR_PATH = None          # None -> data/economic_calendar.json
EVENT_BLACKOUT_BEFORE_MINUTES = 30     # no new entries this long before
EVENT_BLACKOUT_AFTER_MINUTES = 15      # nor this long after

# 6. Volatility Spike
VOLATILITY_SPIKE_ENABLED = True  # Enable volatility-based closing
ATR_SPIKE_MULTIPLIER = 2.0  # Close if ATR spikes above this multiplier of entry ATR

# 7. Time-Based Exit
MIN_HOLDING_SECONDS = 900  # Minimum holding time in seconds (15 minutes for M5)
MAX_POSITION_AGE_SECONDS = 86400  # Maximum position age in seconds (24 hours)

# 8. Market Session
# ON (Phase 12 follow-up): a weekend gap fills a stop beyond the risk model, so
# positions are flattened before the Friday 17:00 New York close (DST-aware).
SESSION_END_CLOSE = True
SESSION_END_BUFFER_MINUTES = 30  # close this many minutes before the weekly close

# 9. Break of Structure
BREAK_OF_STRUCTURE_ENABLED = True  # Enable structure break detection
FRACTAL_PERIOD = 5  # Period for fractal detection

# 10. Risk/Reward Ratio Reversal
# Phase 5.1 (audit C-03): this factor was ALWAYS TRUE -- it inflated max profit
# ~1000x, so "profit < half of max" could never be false and every position was
# market-closed on schedule regardless of outcome. The arithmetic is fixed and
# the factor now measures real retracement from peak favourable excursion, but
# PFE is in-memory until Phase 7 persists it, and a peak reset by a restart
# would close a winner instantly. OFF until then: a disabled factor is safe.
RR_REVERSAL_ENABLED = False
RR_REVERSAL_THRESHOLD = 0.5  # close if profit falls below this fraction of PEAK

# 11. Portfolio/Account Drawdown
PORTFOLIO_DRAWDOWN_CLOSE = True  # Enable portfolio-level drawdown closing
EMERGENCY_CLOSE_DRAWDOWN_FRACTION = 0.35  # Close all if account drops by 35%

# 12. Total position count
# Phase 5.4 (audit M-02): this was labelled "correlation", but the check added
# two complementary subsets of the same list together -- it only ever measured
# the total position count. Renamed rather than left mislabeled. Real
# correlation (vs DXY / XAGUSD) is a feature for after Phase 9, not a rename.
MAX_TOTAL_POSITIONS_CLOSE_ENABLED = False  # close when total open positions exceed the cap
MAX_TOTAL_POSITIONS = 2       # maximum TOTAL open positions

# 13. Trend Reversal
TREND_REVERSAL_CLOSE = True  # Close on detected trend reversals

# Phase 3.1: TWELVE sizing multipliers were deleted here. They are recorded in
# docs/SECURITY-DECISIONS.md. Sizing multipliers are the easiest place in a
# trading system to overfit, and not one of these had evidence behind it -- the
# ATR pair was provably inert (see M-03). Re-introduce one only if Phase 9
# demonstrates it improves OUT-OF-SAMPLE results.
#
# Position size is now a single calculation: risk_money / (contract_size * sl).

# Dynamic Lot Sizing Configuration
MAX_LOTS_PER_ORDER = 5.0  # Maximum allowed lot size

# Phase 13 micro-rollout limits, enforced for LIVE accounts only
# (execution/rollout.py): minimum lot, and a hard daily loss limit.
LIVE_MAX_LOTS_PER_ORDER = 0.01
LIVE_MAX_DAILY_LOSS_FRACTION = 0.02

#Trailing stop config
# Sub-mode, only consulted when TRAILING_STOP_ENABLED is True: adapt the trail
# distance to ATR/trend/news, versus a fixed TRAIL_DISTANCE_PRICE.
ADAPTIVE_TRAILING_STOP = True
# Phase 12.3: CURRENT_ATR = 12.5, CURRENT_TREND_STRENGTH = 65 and a hardcoded
# CURRENT_NEWS_SENTIMENT = {'sentiment': 'bullish', ...} were DELETED. The stop
# management code read them as though they were live market state; nothing
# ever wrote them. Real values are now passed as arguments.
# Phase 5 follow-up: TRAILING_STOP_MODIFICATION was a THIRD trailing switch,
# read only by the dashboard, which could disagree with TRAILING_STOP_ENABLED
# and show a state the bot was not in. Deleted -- there is one switch.

# SL Management Settings
# OFF (user request): no stop modification of any kind for now. Together with
# TRAILING_STOP_ENABLED = False this means the bot NEVER issues
# TRADE_ACTION_SLTP -- once a position is open, its stop and target are exactly
# what was sent at entry, held server-side by the broker.
#
# Break-even also had a real bug (see docs/SECURITY-DECISIONS.md): an unbounded
# time-based buffer combined with a clamp that could place the stop below entry,
# once producing a negative price. That is fixed and tested, but the feature has
# never been validated against real data, so it stays off until Phase 9.
BREAK_EVEN_ENABLED = False
BREAK_EVEN_PROFIT_PRICE = 20.0  # profit threshold to trigger break-even (price units)
BREAK_EVEN_BUFFER_PRICE = 2.0  # buffer above entry for break-even SL (price units)
BREAK_EVEN_ATR_MULTIPLIER = 0.5  # ATR multiplier for dynamic buffer (e.g., 0.5 * ATR)
BREAK_EVEN_TREND_STRENGTH_MULTIPLIER = 0.1  # Trend strength multiplier for buffer adjustment
BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER = 0.2  # News sentiment multiplier for buffer adjustment
# BUG FIX (Phase 5 follow-up): this multiplier is applied per minute held, with
# no natural bound -- after a week it alone contributes ~100 price units. The
# buffer is now capped at BREAK_EVEN_MAX_BUFFER_FRACTION of the profit actually
# achieved. NOTE: the multiplier itself is an unvalidated heuristic inherited
# from the audited code; Phase 9 should decide whether it earns its place.
BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER = 0.01  # price units per minute held
BREAK_EVEN_MAX_BUFFER_FRACTION = 0.9  # buffer <= this fraction of achieved profit
BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER = 0.05  # Profit level multiplier for buffer adjustment

# Adaptive scaling was DELETED (Phase 12 follow-up): no live caller, and a
# scale-in is a second position, which MAX_CONCURRENT_POSITIONS = 1 forbids.

# Trend-following backtest, Hypothesis 3 (docs/STRATEGY-HYPOTHESIS.md).
# Backtest-only: strategies/trade_plan.py's plan_trend_entry() and the
# chandelier trailing stop in backtest/live_engine.py are the only readers.
# Nothing in the live loop (main.py) uses these -- TRAILING_STOP_ENABLED
# stays off for live trading regardless of what this backtest finds.
TREND_INITIAL_SL_ATR_MULT = 2.5   # initial stop = ATR(entry) x this
TREND_TRAIL_ATR_MULT = 3.0        # trail = peak favourable excursion - ATR(entry) x this
