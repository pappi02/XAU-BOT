# XAU-BOT

An automated XAUUSD (spot gold) trading bot for MetaTrader 5, with a read-only
dashboard and an offline backtester that runs the bot's own rules.

> **Validation status (2026-09-13): FAILED Gate C. Do not trade it with real
> money.** Measured with the rules the bot actually runs, the strategy loses
> money after costs: −$0.23 per trade over 1,813 trades. Live accounts are
> refused in code until Gates C and D pass. See [Validation status](#validation-status).

---

## Requirements

| Item | Requirement |
|---|---|
| OS | Windows (the `MetaTrader5` Python package is Windows-only) |
| Python | 3.12 (with `tzdata`, installed by `requirements.txt`) |
| Terminal | MetaTrader 5 desktop terminal, installed and logged in once |
| Account | MT5 **demo** account in **USD**. Hedging or netting both work; the bot keeps at most one position |
| Symbol | `XAUUSD` visible in Market Watch (the bot selects it if needed) |
| News (optional) | A NewsAPI key, for the dashboard's news tab only. Headline sentiment does not affect trading |

A **live (non-demo) account is refused** unless every one of these holds
(`execution/rollout.py`):

* `ALLOW_LIVE=true` is set in `.env`.
* Gate C passed.
* Gate D's automatic checks passed and a person signed it off.
* One position at a time, 0.01 lot, and a daily loss limit of 2% or less.
* A daily review was recorded within the last 36 hours.

### The XAUUSD contract

The bot never uses configured instrument facts. It reads them from the broker at
startup (`execution/symbol_spec.py`). MetaQuotes-Demo, measured 2026-09-13:

| Field | Value | Meaning |
|---|---|---|
| `digits` / `point` | 2 / 0.01 | prices quoted to the cent |
| `trade_contract_size` | 100 | **1.00 lot = 100 oz**; a $1.00 move = $100 per lot |
| `order_calc_profit` (1 lot, $1.00 move) | $100.00 | confirms the contract size |
| `volume_min` / `step` / `max` | 0.01 / 0.01 / 100 | smallest order 0.01 lot (1 oz) |
| `trade_stops_level` / `freeze_level` | 0 / 0 | no minimum stop distance |
| spread (measured session means) | 8.4–12.2 points | $0.08–0.12 |
| `swap_long` / `swap_short` | −12.6 / −4.6 points | charged at the 17:00 New York rollover, ×3 on Wednesdays |
| leverage / margin for 1.00 lot | 1:500 / $869.76 | at about $4,350 gold |

The broker's `trade_tick_value` (0.1 per 0.01 tick) disagrees with the contract
size. At startup the bot asks the broker's profit calculator which one is right,
and **refuses to start** if the calculator contradicts the contract size.

### Broker clock

MT5 stamps bars, positions and deals in **broker server time**, not UTC. On
MetaQuotes-Demo, server time is **New York time + 7 h**: UTC+3 in US summer,
UTC+2 in winter. This was measured from the daily 17:00 New York break in 1.43
years of bars. It is set by `BROKER_SERVER_TZ` / `BROKER_SERVER_SHIFT_HOURS`.
At startup it is checked against a live tick, and the bot refuses to start on a
mismatch. On a different broker, measure the offset first:
`python scripts/probe_broker_facts.py` (read-only).

---

## Setup

```powershell
git clone <repository-url> XAU-BOT
cd XAU-BOT
python -m venv env
env\Scripts\activate
pip install -r requirements.txt            # add -r requirements-dev.txt for tests
copy .env.example .env                     # then fill it in
git config core.hooksPath .githooks        # pre-commit secret and conflict checks
```

`.env` (git-ignored, never commit it):

```
MT5_ACCOUNT=      # login number
MT5_PASSWORD=
MT5_SERVER=       # e.g. MetaQuotes-Demo
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
NEWS_API_KEY=     # optional
ALLOW_LIVE=false
```

Check the environment without trading: `python scripts/check_env.py`.

---

## Running it

| Action | Command | Touches the broker? |
|---|---|---|
| Start the bot | `python main.py` | yes |
| **Stop new entries** (kill switch) | create a file named `STOP` in the project root (`New-Item STOP`) | no |
| Resume entries | delete `STOP` | no |
| **Close everything** and exit | `python main.py --flatten` | yes |
| Health report | `python main.py --health` | no (reads `logs/health.json`) |
| Clear a loss-streak halt | `python main.py --ack-loss-streak` | no (local database) |
| Clear a drawdown / daily-loss halt | `python main.py --clear-halt` | no (risk state file) |
| Record the daily review (live only) | `python main.py --record-review` | no |
| Dashboard + read API | `python run_bot.py` (API on :5001, Streamlit dashboard) | no |
| Backtest + gauntlet | `python scripts/run_gate_c.py` | no (after one data fetch) |
| Forward-test report | `python scripts/forward_test_report.py [--reconcile]` | only with `--reconcile` (read-only) |

The kill switch and flatten are separate on purpose. `STOP` blocks **new**
positions and leaves open ones, with their server-side SL/TP, alone. Use
`--flatten` only when you want out.

### Safe stop and restart

* **Stop:** create `STOP`, wait for the log line saying entries are blocked, then
  press Ctrl+C. Open positions stay open with their broker-held SL and TP; the
  bot never holds a stop only on the client side.
* **Restart:** run `python main.py`. Per-position state (peak profit, ATR at
  entry) is saved in `trades.db`, and deals are re-synced from the broker's
  history. A restart does not reset exit logic and does not open a duplicate
  position. Remember to delete `STOP`.
* **Halts need a person.** After `MAX_CONSECUTIVE_LOSSES` (5) losing trades in a
  row, or a 20% drawdown from the equity peak, entries stop until you clear
  them (`--ack-loss-streak` / `--clear-halt`). Look at the trades first.
* **Weekends:** positions are closed 30 minutes before the Friday 17:00 New York
  close. No entry is taken that could not be closed before then.
* Configuration is validated before connecting. Every problem is listed at
  once, and the bot will not start until all are fixed.

### Dashboard

The dashboard and API **never connect to MT5**. There is one broker client:
`main.py`. It publishes `logs/health.json`, `logs/candles.csv`,
`logs/decisions.jsonl` and `trades.db`, and the dashboard reads those files. If
the bot is not running, the dashboard shows the data as **stale** rather than
showing old numbers as live. Its kill-switch buttons create and delete the real
`STOP` file. Trade history shows one row per closed position, with commission
from both the opening and the closing deal.

---

## What the strategy does

On each **closed** M5 bar. The backtester runs this same code: `strategies/`
modules are shared by `main.py` and `backtest/live_engine.py`.

1. **Signal.** EMA 12/26 trend, RSI 14 and Bollinger(20, 2) position are combined
   into a strength score from 0 to 100 (`strategies/signal_strength.py`).
2. **Reversal hold.** A reversal weaker than 80, or within 5 bars of the last
   signal, is ignored. The bot does not enter on that bar.
3. **Entry gates** (all must pass): kill switch off; no economic-event blackout
   (30 min before to 15 min after US CPI, NFP and FOMC, in New York time);
   strength ≥ 65; no position open; not too close to the weekly close; usable
   ATR; no loss-streak, drawdown or daily-loss halt; spread ≤ 50 points; margin
   available.
4. **Stop and target** (`strategies/trade_plan.py`). The stop is ATR × a
   multiplier between 0.5 and 3.0. The target is the stop distance × a
   reward:risk between 1.2 and 4.0. Both adjust for signal strength, trend, RSI
   extremes and volatility relative to its recent median.
5. **Exits** (`strategies/exit_rules.py`). The broker holds SL and TP. The bot
   also closes early on:
   * two consecutive strong opposite bars;
   * a trend-reversal crossover confirmed by them;
   * a break of prior structure;
   * ATR above 2× its value at entry;
   * age over 24 h;
   * the weekend close;
   * account drawdown ≥ 35%.

   The weekend and drawdown exits apply even to positions younger than the
   15-minute minimum hold.
6. **Off:** trailing stops, break-even, signal-weakening exits, news-sentiment
   entry vetoes and exits. Scaling was deleted.

The hypothesis and its evidence are in
[docs/STRATEGY-HYPOTHESIS.md](docs/STRATEGY-HYPOTHESIS.md).

### Units

Every config key's unit is in its name or in the schema
(`utils/config_validation.py`):

| Suffix | Unit | Example |
|---|---|---|
| `_FRACTION` | fraction of balance or equity (0.01 = 1%) | `RISK_PER_TRADE_FRACTION = 0.01` |
| `_PRICE` | price units, USD per oz ($1.00 = 100 points) | `TRAIL_DISTANCE_PRICE = 10.0` |
| `_POINTS` | broker points (0.01) | `MAX_ENTRY_SPREAD_POINTS = 50` |
| `_SECONDS` / `_MS` / `_MINUTES` | time | `MAX_POSITION_AGE_SECONDS = 86400` |
| `_STRENGTH` | signal score, 0–100 | `EXIT_REVERSAL_MIN_STRENGTH = 70` |
| `LOTS` | broker lots (1.00 = 100 oz) | `MAX_LOTS_PER_ORDER = 5.0` |

The word "pip" is not used anywhere. Gold brokers disagree on what it means.

### Sizing and margin

```
lots = floor_to_step( equity × RISK_PER_TRADE_FRACTION
                      ÷ (stop_distance_price × contract_size) )
```

Example on a $1,000 account: 1% risk is $10. With a $5.00 stop, 1 lot risks
$500, so the bot sizes 0.02 lots. If the calculation comes out below
`volume_min` (0.01), **the bot skips the trade**. It does not round up to the
minimum, because that would risk more than configured. In the backtest this
skipped 1,289 of 3,102 entry attempts on a $1,000 account.

Margin is checked with the broker's own `order_calc_margin` before every order.
At 1:500 leverage and about $4,350 gold, 0.02 lots needs about $17.

---

## Validation status

| Gate | Date | Result |
|---|---|---|
| Tests (no broker connection) | 2026-09-14 | 599 passing; no known gaps marked `xfail` |
| Gauntlet step 1: zero-cost sanity | 2026-09-13 | PASS: 2,052 trades, +$0.37/trade before costs |
| **Step 2 (Gate C): realistic costs** | 2026-09-13 | **FAIL**: −$0.23/trade over 1,813 trades |
| Steps 3–7 | — | not run (the gauntlet stops at the first failure) |
| Gate D: demo forward test | — | **blocked** by Gate C |
| Phase 13: live micro-rollout | — | **refused in code** (`execution/rollout.py`) |
| Exploratory: Hypothesis 1 on H1 (17 years) | 2026-09-14 | **FAILED**, more decisively: −67.6%, t = −2.65 |
| Exploratory: Hypothesis 2, breakout + volatility expansion (M5) | 2026-09-14 | **FAILED**: −$0.62/trade over 78 trades, t = −0.42 |
| Exploratory: Hypothesis 3, trend following + ATR trailing exit (H1, $10k) | 2026-09-14 | **FAILED**, strongest signal yet: −57.3%, t = −3.89 |

None of the exploratory runs above are recorded as the project's Gate C —
only a run of the live bot's actual configuration (Hypothesis 1, M5) is. See
`docs/STRATEGY-HYPOTHESIS.md` for all three hypotheses in full, and
`docs/reports/` for every backtest report.

**Full backtest, live rules, realistic costs, halts disabled** (the diagnostic
view of the strategy's edge: `docs/reports/backtest-xauusd-m5-live-rules-no-halts.txt`):

| Measure | Value |
|---|---|
| Period | 2025-04-08 → 2026-09-11 (1.43 years, 99,699 M5 bars) |
| Balance | $1,000.00 → $586.99 (−41.3%) |
| Total trades | 1,813 |
| Wins / losses | 562 / 1,251 |
| Win rate | 31.0% |
| Profit factor | 0.95 |
| Expectancy | −$0.23 per trade (−0.02 R), t = −0.89 |
| Average win / average loss | $14.77 / −$6.97 (payoff 2.12) |
| Maximum win | $33.30 (BUY 0.02 lots, take profit) |
| Maximum loss | −$72.60 (BUY 0.02 lots, stop gapped through at the Monday open) |
| Longest win / loss streak | 7 / 23 |
| Max drawdown | $605.44 (50.8%) |
| Average holding time | 43.8 minutes |
| Costs | $902.88: spread $407.73, commission $284.41, slippage $193.22, swap $17.52 |

**With the account protections on**, exactly as the bot would run
(`docs/reports/backtest-xauusd-m5-live-rules.txt`), the 20% drawdown halt
tripped on 2025-08-08. The bot would have stopped trading after 460 trades
(+$5.30, 32.0% win rate) and waited for a person.

The data is all the history the server keeps: 99,999 M5 bars from a period
dominated by a strong gold bull market. Spreads and swap are measured.
Commission ($7/lot) and slippage are assumptions, not measurements.

Reproduce it offline after one read-only fetch:

```powershell
python scripts/fetch_historical_data.py   # read-only; needs .env
python scripts/run_gate_c.py              # offline, about 15 minutes
```

Reports are written to `docs/reports/`, and gate results to
`docs/reports/gates.json`.

---

## Development

```powershell
python -m pytest                          # no test connects to a broker
python -m compileall -q . -x "env|__pycache__"
python tools/check_config.py              # duplicate and unreferenced config keys
python tools/check_no_secrets.py
```

CI (`.github/workflows/ci.yml`) runs these on every push.

| Path | Contents |
|---|---|
| `main.py` | the bot: the single MT5 client and the trading loop |
| `config.py` | configuration; `utils/config_validation.py` is its schema |
| `strategies/` | signal, shared trade plan and exit rules |
| `execution/` | executor, order validation, symbol spec, bar gate, kill switch, durable state, live-rollout guard |
| `risk/` | sizing, daily/drawdown/portfolio limits |
| `utils/market_time.py` | broker clock, DST-aware sessions, weekly close |
| `backtest/` | live-rules backtester, the 7-step gauntlet, the performance report |
| `run_bot.py`, `dashboard.py`, `dashboard_data.py`, `tabs/` | read-only API and dashboard |
| `docs/SECURITY-DECISIONS.md` | every remediation decision, with its reason |
| `docs/reports/` | backtest, gauntlet and forward-test reports; `gates.json` |
| `scripts/manual/` | scripts that need a terminal; not part of the test suite |

---

## Risk

Leveraged gold trading can lose more than a small account can absorb, quickly.
This strategy has been measured to lose money after costs. It is provided for
research on demo accounts, with no warranty.
