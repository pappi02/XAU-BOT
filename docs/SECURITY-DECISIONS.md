# Security decisions

## H-10 — Leaked NewsAPI key `2287da19…2278b`

**Date:** 2026-09-09
**Status:** source cleaned; **revocation is OUTSTANDING and is the only fix that matters**

### Facts established

- The key was hardcoded as the `os.getenv` fallback in `config.py:12`.
- It appears in **5 commits** on `main`: `9583572`, `38b7152`, `a2c32b2`, `7f5754d`, `8f75372`.
- **4 of those commits are on the public remote** `https://github.com/pappi02/XAU-BOT.git`
  (verified with `git log --oneline origin/main -S <key>`).

### Decision: treat the key as permanently public. Revoke it.

The repository is already published. Once a secret reaches a public GitHub
repository it must be assumed compromised: GitHub retains unreferenced objects,
the commits may be forked, cloned, or served from the API/search index, and
secret-harvesting crawlers scan public pushes within minutes. A history rewrite
would remove it from *this* clone's history; it would **not** unpublish it.

Therefore:

1. **Revoke and reissue at newsapi.org.** This is the whole remedy. Until it is
   done, the exposure is live regardless of what the code says. ← *user action,
   acknowledged 2026-09-09, to be done via the newsapi.org account dashboard.*
   The reissued key goes in `.env` (git-ignored) and nowhere else.
2. The `config.py` fallback is now `os.getenv('NEWS_API_KEY')` with **no default**,
   so a missing key fails visibly instead of silently using a burned one.
3. `scripts/check_env.py` refuses to pass preflight if the revoked key is ever
   pasted back into `.env`, so a stale copy cannot quietly come back into use.
4. A `pre-commit` secret scan (`.githooks/pre-commit`) blocks this specific key and
   common secret shapes from ever being staged again. Enable per clone with
   `git config core.hooksPath .githooks`.

### On rewriting history

`git filter-repo --replace-text` is **deferred, not rejected**. It costs a
force-push that rewrites every published SHA and breaks any existing clone, and
it buys nothing security-wise given the key is revoked. Revisit only if the
repository is ever made private or a fresh history is wanted for other reasons.

### Residual

`API_KEY` / `SECRET_KEY` in `config.py:11-12` still default to the placeholder
strings `'your_api_key_here'` / `'your_secret_key_here'`. They are read nowhere
else in the codebase. Delete them in Phase 12 unless a consumer appears.

---

# Phase 1 decisions

## Conflict resolution (C-01)

All 60 conflict hunks across seven files resolved to the **HEAD** side, after
diffing both sides hunk by hunk. The `9583572` side was in every case the older,
pre-refactor code. Two findings from that review:

- **Nothing of value was lost.** The larger `9583572` hunks (e.g. dashboard's
  443-line inline tab bodies) are superseded by HEAD's refactor into `tabs/*.py`.
- **One suspected loss was not real.** HEAD's `_check_market_session_end` drops
  the `SESSION_END_CLOSE` guard, but the caller at `trade_executor.py:699`
  already gates on it. The guard moved; it did not disappear.
- Four one-line docstrings on `close_{profitable,loss,buy,sell}_positions`
  existed only on the discarded side and were restored by hand.

## CONTRACT_SIZE deduplication (C-04, partial)

`config.py` defined `CONTRACT_SIZE` twice: `100.0` (correct -- 100 oz per
standard lot of XAUUSD) and later `100000` (the FX convention). Python kept the
**later** one, so every money conversion in the codebase was wrong by 1000x.

Gate B forbids duplicate top-level names, so this had to be resolved in Phase 1
rather than deferred to Phase 2 as the plan suggests. **The correct value
(100.0) was kept.** This changes the bot's effective behaviour -- deliberately,
because the alternative was preserving a known 1000x error. Phase 2 deletes the
key outright in favour of `SymbolSpec.contract_size` read from the broker.

`TRAIL_START_PIPS` (20 vs 25) was deduplicated to **25**, the value that was
already winning -- no behaviour change. `TP_RISK_REWARD` was defined twice with
the identical value 2.5 -- no behaviour change.

## Dead config keys deleted (M-14)

`tools/check_config.py` found **15** keys referenced nowhere outside their own
assignment (the audit said 14). Recorded here so the intent is not lost:

```
API_KEY = os.getenv('API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')
DATA_SOURCE = 'mt5'
POSITION_SIZE_PCT = 1.0
LEVERAGE = 400
LEVERAGE_PHASE5 = 400
CORRELATION_THRESHOLD = 0.7
CURRENT_VOLATILITY = 1.8
HIGH_IMPACT_NEWS_CLOSE = True          # revisit in Phase 10 (news calendar)
ECONOMIC_EVENT_CLOSE_MINUTES = 30      # revisit in Phase 10
MAX_POSITION_AGE_MINUTES = 1440        # superseded by MAX_POSITION_AGE
SIGNAL_STRENGTH_DROP = 30              # comment admitted it was unused
RISK_MODE_BALANCED_MULTIPLIER = 1.2
SCALING_ATR_MULTIPLIER = 1.5
WINNING_STREAK_LENGTH = 3
```

A config key that nothing reads is a lie about what the bot does -- it invites
tuning a number that has no effect. Phases 2, 3 and 10 will define what they
actually need, with the unit in the name.

`SCALING_CHECK_INTERVAL = 60` was additionally deleted in Phase 1.7: its only
reader was `run_bot.py::trading_bot()`, which was removed in 1.4. Phase 4 should
reintroduce it (with a unit in the name) if the ported loop needs it.

## One entry point (M-08, 1.4)

`main.py` is the only process permitted to trade.

- **`run_bot.py`** is now a launcher and read-only Flask API. Two hazards removed:
  a module-level `mt5.initialize()` + `connect_mt5()` pair that connected to a
  broker *on import* (and called `quit()` on failure, killing the interpreter),
  and `trading_bot()` -- a second trading loop whose entry gating diverged from
  `main.py`'s. A test asserts importing it performs no broker calls.
- **`dashboard.py`** calls `disable_trading_writes()` at import. Every broker
  write in the codebase now routes through the single choke point
  `TradeExecutor._send_order`, which raises `TradingDisabled` when the interlock
  is set. A test asserts no `order_send` call exists outside that method, so a
  future fifth call site cannot quietly bypass it.

## Logging (1.7)

`data/connect_mt5.py` called `logging.basicConfig()` at import. Being a library
module, that installed a root handler alongside `setup_logger`'s, and every log
line was emitted twice. Removed; `setup_logger` now sets `propagate = False` and
`connect_mt5` uses the shared bot logger so the account-identity warning lands
in the same stream as everything else.

## Test suite (1.7)

`pytest` previously collected **zero** tests: it imported `data/test_data.py`, a
manual MT5 script that calls `quit()` at module level, which aborted the run with
INTERNALERROR. That file is renamed `data/check_data_manual.py`, and `pytest.ini`
restricts collection to `tests/`.

Once running, 15 of 32 tests failed -- all stale fixtures, not production bugs:

- `TradeExecutor.__init__` iterates open positions to seed scaling data, but the
  fixtures left `positions_get` unconfigured, returning a truthy non-iterable
  `Mock`. This also meant `TradeExecutor()` could not be constructed at all.
- `check_daily_loss_limit` was rewritten at some point to read floating P&L
  (`account.profit`) instead of summing `history_deals_get()`; the tests still
  mocked the old path.
- `get_current_market_session` moved from `datetime.utcnow()` to
  `datetime.now(timezone.utc)`; the test still patched `utcnow`.

`tests/test_phase1_guarantees.py` adds 20 tests covering every Phase 1 fix.
Total: **52 passing**, and CI is green and blocking.

---

# Phase 2 decisions

## The "pip conversions" were no-ops (2.2)

The audit describes `x / 100000 * CONTRACT_SIZE` as a hand-rolled unit
conversion implementing "1 pip = $1.00". Reading it with the *shipped* value of
`CONTRACT_SIZE = 100000`, it is something worse: **the identity function**.
`delta / 100000 * 100000 == delta`. Eleven sites performed this no-op while
looking like unit conversion, and every `*_PIPS` config value was therefore a
plain price delta all along -- `TRAIL_START_PIPS = 25` meant *$25 of gold price
movement*, not 25 pips of anything.

This matters for Phase 1: deduplicating `CONTRACT_SIZE` to the correct `100.0`
turned those identities into a genuine 1000x error. Phase 2 removes the
conversions entirely and renames the keys so the unit is in the name:

```
TRAIL_START_PIPS               -> TRAIL_START_PRICE
TRAIL_DISTANCE_PIPS            -> TRAIL_DISTANCE_PRICE
TRAILING_STOP_ACTIVATION_PIPS  -> TRAILING_STOP_ACTIVATION_PRICE
TRAILING_STOP_DISTANCE_PIPS    -> TRAILING_STOP_DISTANCE_PRICE
BREAK_EVEN_PROFIT_PIPS         -> BREAK_EVEN_PROFIT_PRICE
BREAK_EVEN_BUFFER_PIPS         -> BREAK_EVEN_BUFFER_PRICE
SCALING_PROFIT_THRESHOLD_PIPS  -> SCALING_PROFIT_THRESHOLD_PRICE
SCALING_LOSS_THRESHOLD_PIPS    -> SCALING_LOSS_THRESHOLD_PRICE
```

**The numeric values are unchanged**, so behaviour matches what the bot did
before Phase 1 rather than what the code appeared to say. The plan suggests
re-denominating these into ATR multiples; that is a strategy change, deferred to
Phase 5 where the exit logic is rewritten anyway. **These thresholds have never
been validated against anything** -- $25 to start trailing gold is a guess
inherited from the audited code, not a calibrated number.

## CONTRACT_SIZE is gone (2.1)

Deleted from `config.py`. `execution/symbol_spec.py` reads the contract
specification from the broker, validates it, and refuses to continue if it is
unusable or disagrees with an expected value. `RiskManager` was migrated too --
it was the last consumer.

One behaviour change worth stating: `compute_lot_size` used to return a lot size
even when `symbol_info` was unavailable, computed from the configured (wrong)
contract size. **It now raises.** If the broker will not say what a lot is,
guessing is the one thing we must not do.

The correction is visible in `test_compute_lot_size_normal`, whose expected
value moved from `0.01` to `0.1`. The old expectation encoded the bug -- its own
comment read `usd_risk_per_lot = 100000 * 20`. With the wrong contract size the
computed size was 1000x too small and got clamped up to the broker minimum, so
**the bot was opening floor-value positions on every trade regardless of the
risk settings**.

## Orders are now validated against the broker (2.3)

`execution/order_validator.py` normalises volume **down** to `volume_step`
(rounding up would exceed authorised risk), rejects below `volume_min`, caps at
`volume_max`, rounds prices to the symbol's own `digits` rather than a hardcoded
2 decimals, widens SL/TP to clear `trade_stops_level` (**widen the stop, never
shrink the position, never drop the stop**), and checks `order_calc_margin`
against 25% of free margin.

Filling mode is probed from the symbol's bitmask with an IOC -> FOK -> RETURN
fallback, replacing the hardcoded `ORDER_FILLING_IOC`. On an FOK-only broker
every order previously failed with retcode 10030, was retried three times,
raised and swallowed -- a silent total outage indistinguishable from "no signals
today".

## Spread gate (2.4) and ticket identity (2.5)

`MAX_ENTRY_SPREAD_POINTS = 50` blocks entries on a wide spread, and the spread
is logged on every entry decision so the threshold can be calibrated from real
data. **50 is a placeholder**, not a measurement. An unreadable spread is
reported as unknown and logged as a warning -- never treated as zero, which
would wave every order through.

`_resolve_position_ticket` resolves the real position ticket from
`positions_get()` filtered by magic number, instead of assuming `result.order`
is a position ticket. It falls back to the old behaviour on lookup failure and
warns on mismatch.

## Still outstanding for Phase 2

The `SymbolSpec` field values in tests are **plausible, not observed**. Before
Gate C, connect a demo terminal once, dump the real `symbol_info` for the traded
symbol, and commit it as a fixture. This is a read-only call -- no orders.

---

# Phase 3 decisions

## Sizing is one calculation, and it can say no (3.1, C-05)

```
risk_money = equity * RISK_PER_TRADE_FRACTION
raw_lots   = risk_money / (spec.contract_size * sl_distance)
lots       = floor_to_step(raw_lots, spec.volume_step)
```

`floor`, never round -- rounding up takes more risk than authorised. If
`lots < volume_min` the trade is **DECLINED** and the reason logged. The audited
code clamped up to the minimum instead, which is how an intended 1% became 2.5%
on a small account.

There were **two** sizing implementations (`compute_lot_size` and
`calculate_dynamic_lot_size`) with the same defect. There is now one;
`compute_lot_size` is a thin wrapper.

`RISK_PER_TRADE_PCT = 0.02` (a fraction) and `BASE_RISK_PERCENT = 1.0` (a
percent) were two contradictory risk settings. Collapsed into
`RISK_PER_TRADE_FRACTION = 0.01`, with the unit in the name.

**Twenty-three keys were deleted**, including all twelve sizing multipliers.
None had evidence behind them; the ATR pair was provably inert. Full list in the
Phase 3 section of the config history below. Sizing multipliers are the easiest
place in a trading system to overfit -- re-introduce one only if Phase 9
demonstrates it improves *out-of-sample* results.

## The volatility multiplier was inverted, not just wrong (3.2, M-03)

`ATR_LOW_THRESHOLD = 10` against an M5 gold ATR(14) of roughly 1.5-5 means
`atr < 10` is *always* true. The "low volatility, increase lot" multiplier was
applied permanently -- **including during volatility spikes** -- and the
high-volatility branch was unreachable. The bot sized up hardest exactly when it
should have sized down.

`risk/volatility.py` classifies volatility by **percentile of its own trailing
distribution**, which means the same thing on any instrument, timeframe or price
level. `check_absolute_thresholds()` is kept as a diagnostic and its test asserts
that it correctly diagnoses the shipped 10/30 pair as broken.

## The daily loss limit measured the wrong number (3.3, H-03)

`check_daily_loss_limit` read `account.profit` -- the **floating** P&L of open
positions. `update_daily_pnl`, which queried `history_deals_get` correctly, was
never called. **A day of ten realised losses passed the check, because nothing
was open.** There is a test for exactly that scenario.

Now: realised (profit + commission + swap over today's deals) **plus** floating,
against the **day's opening balance**, persisted to `risk_state.json` so killing
and restarting the bot cannot reset a limit that has already tripped. Also
tested.

`MAX_DAILY_LOSS_PCT = 0.60` carried the comment "stop trading if daily loss >
30%" -- the value and the stated intent disagreed, and 60% is not a risk limit.
Now `MAX_DAILY_LOSS_FRACTION = 0.05`. **This is a judgement call, not a
measurement** -- 5% is a conventional daily stop. Change it deliberately.

`MIN_ACCOUNT_BALANCE` was `0`, making `enough_balance()` unconditionally true.
Now 50.0 -- also a placeholder to be set to a real floor.

## Drawdown, and a control that failed open (3.4, L-04)

Drawdown was measured against a hardcoded `INITIAL_ACCOUNT_BALANCE = 150.0`:
permanently 33% on a $100 account, unreachable on a $500 one. It now comes from
a **persisted equity high-water mark**, so it means the same thing at any
account size.

`_check_portfolio_drawdown` used a bare `except: return False`. A risk control
that answers "no problem" to *every* error is not a risk control. It now **fails
closed**: an error is treated as a breach, logged loudly, and positions are
protected.

## Portfolio-level pre-trade check (3.5)

No check existed between the entry decision and the order. `check_portfolio_risk`
now asserts open risk plus the candidate stays within
`MAX_PORTFOLIO_RISK_FRACTION = 0.04`. A position **with no stop counts its whole
notional**, because that is what it risks.

The scaling fallback stop (L-07) was `10 / 100000 * CONTRACT_SIZE` -- an
arbitrary $10 disguised as a conversion. It is now `ATR x
SCALING_FALLBACK_SL_ATR`, and refuses to scale at all when ATR is unavailable.

## Gates are wired to the entry path

The audit's recurring pattern was controls that existed but were never called.
Five tests assert each gate actually blocks `enter_trade`.

## Test hygiene

`tests/conftest.py` now pins the environment before `config` is imported. The
suite was depending on the developer's local `.env`, and a malformed one broke
every test with an error unrelated to the code under test.

---

# Phase 4 decisions

## The live loop had no entry gating at all (4.1, C-02)

The audited `main_loop` entered on `if signal in ("BUY","SELL")` and then slept
60 seconds. No strength filter, no position cap, no dedupe. The only brake was
`MAX_CONCURRENT_POSITIONS = 100` inside `enter_trade` -- which on a small account
is not a brake but a margin stop-out waiting to happen.

Four gates now stand between the signal and the order, in this order:

0. **Signal-reversal hold** -- a BUY->SELL flip needs `strength >= 80` *and* the
   previous signal held for `MIN_SIGNAL_HOLD_BARS`.
1. **Strength floor** -- `strength >= MIN_ENTRY_STRENGTH` (65).
2. **Position cap** -- checked in the loop, not only inside `enter_trade`.
3. **Per-bar dedupe** -- one entry per closed bar timestamp.

`MAX_CONCURRENT_POSITIONS` went from **100 to 1**, and `MAX_OPEN_TRADES` from a
module-level 12 in `main.py` to `config.MAX_OPEN_TRADES = 1`. The two disagreed
and both were live. Raise them only on Phase 9 evidence.

`main_loop_legacy_gated()` (125 lines) is deleted now that its gates are ported.

## The forming bar was the real duplicate-entry bug (4.2, C-02 / M-12 / H-09)

`copy_rates_range` returns the **still-forming** bar as the last row, and
`generate_signal` reads `iloc[-1]`. On a 60-second loop with M5 bars, the same
forming bar was evaluated about five times with indicator values mutating
underneath it -- so one bar could produce several different signals, and several
entries, from data that had not finished existing.

`get_candles` now uses `copy_rates_from_pos` (count-based and timezone-free,
which also closes H-09) and **drops the forming bar by default**. The old call
computed its date window as `now - num_candles * 5 minutes`, silently assuming
an M5 timeframe and mixing local time with broker time.

Display callers may opt out: `tabs/charts_tab.py` passes
`drop_forming_bar=False` so the chart shows live price. `tabs/signals_tab.py`
deliberately does not -- that panel must show the signal the bot actually acts
on.

The loop no longer sleeps a fixed 60 seconds; it waits for the next bar close
plus a 2-second settle margin. There is no new information until a bar closes.

## A unit bug in the gate being ported

`run_bot.py`'s reversal hold compared elapsed seconds against
`min_hold_candles * 300` -- hardcoding a 5-minute bar. On H1 that is a 25-minute
hold instead of 5 hours. `BarGate` counts **bars**, and `timeframe_seconds()`
raises on an unknown timeframe rather than defaulting to M5, which is how this
class of bug went unnoticed twice.

---

# Phase 5 decisions

## 5.7 factor re-audit -- can it fire? should it? what closes it?

| # | Factor | Status after Phase 5 |
|---|---|---|
| 1 | Take profit | **Deleted.** Server-side; racing it adds only slippage (M-13) |
| 2 | Stop loss | **Deleted.** Same |
| 3 | Trailing stop | **Moved** to `manage_open_positions()`; modifies, never closes |
| 4 | Opposite signal | Kept; positive + negative tests |
| 5 | Signal weakening | Kept; depends on the Phase 9 strength rebuild |
| 6 | News event | Kept as-is; real calendar is Phase 10 |
| 7 | Volatility spike | **Now able to fire** -- `entry_atr` recorded per ticket |
| 8 | Time-based exit | Kept |
| 9 | Session end | **Buffer fixed** (M-06) |
| 10 | Break of structure | **Fixed** -- 0% to ~10.5% firing (M-01) |
| 11 | RR reversal | **Rewritten on PFE, default OFF** (C-03) |
| 12 | Portfolio drawdown | Fixed in Phase 3.4 |
| 13 | Correlation | **Renamed** `_check_max_total_positions` (M-02) |
| 14 | Trend reversal | Kept |

## C-03 was already half-fixed, and still wrong (5.1)

Phase 2.2's money-conversion work incidentally corrected the `* 100000` that
made this factor always-true -- I verified the original demanded **$12,500 of
profit on a 0.01-lot position** to avoid closing, so every position was
market-closed on schedule regardless of outcome.

But correct arithmetic was not enough. "Profit fell below half of what it
reached" needs to know what it reached, and the code remembered nothing: a fresh
position at $0 profit still satisfied `0 < max_profit * 0.5`. The factor now
tracks **peak favourable excursion per ticket** and measures real retracement.

`RR_REVERSAL_ENABLED` is **False** until Phase 7 persists the PFE. In-memory
peaks reset on restart, and a peak of 0 after a restart would instantly close a
winning position. A disabled factor is safe; an always-true one is not.

## The trailing stop closed positions instead of trailing them (5.2, C-06)

`_check_trailing_stop` was consumed inside `should_close_trade`, so a trail
trigger meant *close at market* -- the exact opposite of a trailing stop, and it
converted every winner into an exit at whatever price was available. Meanwhile
`modify_trade_sl`, `apply_break_even_sl` and `calculate_trailing_stop` were
carefully written and **called from no live path at all**.

`manage_open_positions()` is the missing step: it runs each bar, computes a new
stop, refuses to move one backwards, and issues `TRADE_ACTION_SLTP`. It never
closes anything. A test drives a favourable price ramp and asserts monotonically
improving stops and **zero** `TRADE_ACTION_DEAL` requests.

## M-01 measured, before and after (5.3)

The window used `.tail(n)`, which includes the current bar. `close < low.tail(n).min()`
is unsatisfiable -- a bar's close is never below its own low. I reproduced the
audit's finding (0 firings) and measured the fix on 20,000 random walks per
direction: **BUY breakdowns 0 -> 10.48%, SELL breakouts 0 -> 10.95%**, which is
about what a 10-bar breakout should do on a random walk.

## The session overlap was invisible (5.6, M-06)

The elif chain tested New York (13-20) before London (8-16), so **13:00-16:00 --
the London/NY overlap, gold's highest-volume window** -- was reported as plain
"New York". Any analysis bucketed by session attributed the overlap's behaviour
to NY alone. The overlap is now its own session.

Session boundaries remain fixed UTC hours. Broker server time is usually
UTC+2/+3 with DST, so edges drift by an hour twice a year. DST-aware conversion
needs the broker's timezone -- **deferred to Phase 11**, recorded here so it is
not forgotten.

## Determinism (5.5, M-04)

Two `* random.uniform(0.95, 1.05)` jitters, commented "prevent
over-optimization", are deleted along with the `random` import. Jitter does not
address overfitting; it makes risk irreproducible, incidents un-debuggable and
tests impossible. Determinism is a precondition for Phase 9.

## A note on how two of these tests are written

`test_trailing_no_longer_closes_positions` and `test_no_randomness_in_the_executor`
**parse the AST** rather than grepping the source. Written as string searches
they failed against the comments explaining the removal -- a comment naming a
deleted call is not a call. Grep-based structural assertions are fragile in
exactly this way.

---

# Phase 5 follow-up: trailing switch, and a break-even bug found while testing it

## Trailing is one switch, and it is OFF

There were **three** overlapping trailing switches: `TRAILING_STOP_ENABLED`,
`ADAPTIVE_TRAILING_STOP` and `TRAILING_STOP_MODIFICATION`. The third was read
only by the dashboard, so the UI could show "trailing on" while the bot had it
off. Deleted. `ADAPTIVE_TRAILING_STOP` survives as a documented sub-mode that
only matters when trailing is enabled.

**`TRAILING_STOP_ENABLED = False`** (user request). The behaviour has never
actually run as intended -- until Phase 5.2 it closed positions instead of
moving stops (C-06) -- and its thresholds have never been validated. When
trailing is off, positions are managed solely by the broker's server-side SL/TP.

`main.py::manage_positions()` was deleted: 52 lines containing a **second**
trailing implementation that built its own SLTP request, bypassed the Phase 2.3
order validation, and had been dead since 5.2 wired in the executor's version.
Exactly the duplicate-definition shape of audit M-08.

## Break-even could set a stop below entry -- or negative

Found while verifying the trailing switch, not by the audit. Two compounding
bugs:

1. `BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER` added 0.01 price units per minute
   held, **unbounded**. A week-old position accrues ~100 units from this term
   alone; with a stale `position.time` it reaches six figures.
2. The "safety" clamp then set `sl = price_current - buffer * 0.5`. With a large
   buffer that lands far **below entry**. Observed: entry 2000, current 2100,
   computed stop **-147,012** -- a negative price.

A break-even stop below the entry it protects is not break-even; it is a loss
with extra steps. The clamp intended to prevent an invalid stop produced a
worse one.

Fixed: the buffer is capped at `BREAK_EVEN_MAX_BUFFER_FRACTION` (0.9) of the
profit actually achieved, and the resulting stop is clamped **into**
`[entry, current)` for a BUY and `(current, entry]` for a SELL rather than
outside it. If no protective level exists the stop is left alone, and a stop is
never moved backwards. Seven regression tests cover fresh, day-old, week-old,
month-old and epoch-zero positions on both sides.

The time multiplier itself remains an unvalidated heuristic inherited from the
audited code. Phase 9 should decide whether it earns its place at all.

## Also fixed

Deprecated `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` in
`tabs/live_trading_tab.py` and `tabs/sl_management_tab.py` -- the last two
occurrences outside docstrings.

---

# Phase 6 decisions

## No stop modification at all (user request)

`TRAILING_STOP_ENABLED = False` **and** `BREAK_EVEN_ENABLED = False`. The bot
never issues `TRADE_ACTION_SLTP`: once a position is open, its stop and target
are exactly what was sent at entry, held server-side by the broker.

Tested end-to-end by walking a position from flat to deeply profitable and
asserting zero broker writes. A separate test asserts the loop still *calls*
`manage_open_positions`, so re-enabling is a config change rather than a code
change.

## Retries are idempotent (6.1, H-02)

The old loop re-sent an identical request up to three times whenever the retcode
was not DONE -- **including when `result` was None**, which is precisely when the
order's true status is unknown. A timeout after the broker filled would open a
second position. The price was computed once and never refreshed, so each retry
competed with a stale quote.

Now:

* Every attempt carries a unique token (`XAU-<10 hex>`) in the order comment,
  which fits MT5's 31-character limit.
* Before any retry, `positions_get` and `history_orders_get` are searched for
  that token. If it is there, the order already executed and we return it
  instead of resending.
* Only **10004 (requote)**, **10020 (price changed)** and **10021 (price off)**
  are retried. Everything else is either a hard rejection that resending cannot
  fix, or an unknown outcome.
* A `None` result is **never** retried -- it reconciles by token, and if it
  cannot find the order it raises rather than guessing.
* The tick is re-read before each retry.
* After the loop, a final reconciliation catches an order that landed late.

Note the two existing tests for this path asserted retries on retcode **10006
(REJECT)** -- they encoded the bug. Rewritten around 10004, with new tests
asserting 10006/10016/10018/10019/10027/10030 are *not* retried.

## Partial fills (6.2)

`result.volume` was never compared to the request, so a partial fill left the
bot believing it held a size it did not have. Both are now recorded, along with
slippage against the intended price.

**Policy: accept the partial fill**, logged as a warning. Topping up would place
a second order at a worse price to chase size the market did not offer, and
would double the failure modes on the path 6.1 just made safe.

## The mock broker is gone (6.3, M-05)

`TradeExecutor.__init__` substituted `unittest.mock.Mock` objects when its
arguments were None -- including an `order_send` returning `retcode=10009`
(DONE). A fake broker that confirms every order, reachable from production by
forgetting an argument: a misconfigured bot looked exactly like a working one,
logging successful trades that never reached a market.

All three dependencies are now required and `__init__` raises naming the missing
ones. The doubles moved to `tests/fakes.py`, where reaching them is deliberate.

## Disconnect no longer reads as "flat" (6.4, H-04)

`positions_get()` returns `None` for **both** "no positions" and "not
connected", and the old code mapped every failure -- exceptions included -- to
`[]`. A dropped connection therefore presented as a flat account, and a bot that
believes it is flat will stack a new position on top of ones it cannot see.

`get_open_positions()` now raises `BrokerQueryFailed` when the answer is
unknown, disambiguating via `terminal_info()`. `enter_trade` refuses to trade
when it cannot establish position state. `get_open_positions_or_none()` serves
read-only callers.

`reconnect_with_backoff()` re-establishes the connection with doubling delays
(capped), and the loop checks `is_connected()` before every decision. Credential
errors are **not** retried -- retrying those cannot help and risks connecting to
the wrong account.

---

# Issues found and fixed before Phase 7

## `main.py` read a config key Phase 3.4 had deleted

`config.INITIAL_ACCOUNT_BALANCE` was still read in the emergency-close block.
It would raise `AttributeError` on **every iteration** -- and the surrounding
bare `except` swallowed it, so **the emergency close could never fire**. Same
fail-open shape as L-04: a risk control reporting "nothing wrong" for every
error.

It also repeated L-04's original defect, measuring drawdown against a hardcoded
starting balance. It now uses the persisted equity high-water mark, halts on
breach, and **re-raises** rather than swallowing.

Found by an AST scan for `config.*` attributes that no longer exist; that scan
now reports clean.

## Stale root-level scripts

Five `test_*.py` files sat in the repository root, collected by nothing and
maintained by no one. `test_execute_trade.py` was **broken**: its entire purpose
was `TradeExecutor(None, None, None)`, the mock-broker fallback Phase 6.3
removed. Deleted -- its coverage is in `tests/test_execution_phase6.py`.

The other four moved to `scripts/manual/` and were renamed `check_*`. Files
named `test_*` outside `tests/` are how the suite came to collect zero tests in
the first place.

---

# Phase 7 decisions

## Scaling state is durable (7.1, H-04)

`position_scaling_data` was an in-memory dict, and `__init__` re-seeded every
open position with `additional_positions: 0`. **The 3x exposure cap refilled on
every restart**, so a crash-restart loop made scaling unbounded -- the limit
reset itself exactly when things were going wrong.

State now lives in SQLite (`position_state`): entry token, entry ATR, original
and total volume, scaling count and peak favourable excursion. The scaling
decision consults the durable row, not the in-memory copy.

Startup **reconciles** rather than re-initialising. Three populations:

* **adopted** -- open at the broker, unknown to us. Put in **manage-only** mode:
  managed but never scaled, because the scaling history is unknown and assuming
  zero *is* the bug.
* **closed** -- known to us, no longer open. Dropped. This also fixes the leak
  where server-side SL/TP closures left rows forever, since cleanup only
  happened inside `close_position_by_ticket`.
* **matched** -- history preserved.

When the position query fails, nothing is reconciled and nothing is assumed.

## Trade records come from the broker (7.2, H-07)

`log_trade_entry`, `log_trade_exit` and `update_position` were fully implemented
and called from **nowhere**. The only writer was `log_auto_close`, recording
`pos.profit` -- the *floating* P&L read before the close order was sent,
excluding closing spread, slippage and swap. Trades closed by a server-side stop
were never recorded at all.

That last point is the one that matters. **Stop-outs are the loss-heavy tail**,
so omitting them biases the win rate upward *by construction*. The dashboard
would show a flattering number regardless of how the strategy actually
performed. This is survivorship bias applied to live results, and it is exactly
what makes a losing system look worth scaling up. A test demonstrates it: five
trades, 40% real win rate, negative total P&L -- and 100% by the old accounting.

`sync_deals()` polls `history_deals_get` and records every closing deal keyed by
the broker's own deal ticket, so re-polling cannot double-count. `net_pnl` is
`profit + commission + swap` -- the number that actually moved the balance.
Recording `profit` alone overstates every trade by its costs, which on a
scalping strategy is most of the edge.

`compute_statistics()` is recomputed from this table and reports
`source: "broker_deals"`, so nobody mistakes it for the old reconstruction.

**Phase 9 depends on this.** Measuring an edge against records that omit the
losses is not measurement.

---

# Phase 8 decisions

## The dashboard was still showing the biased numbers

Found before starting Phase 8. Phase 7.2 fixed the *recording* of realised P&L,
but `tabs/performance_tab.py` still called `trade_logger.compute_statistics()`,
which summed the **local** table -- the one that never saw a server-side
stop-out. Fixing the recording without fixing the reporting leaves the dangerous
number exactly where a human can read it and believe it.

`TradeLogger.compute_statistics()` and `get_total_pnl()` now delegate to the
broker-sourced store. If the broker table is empty but legacy rows exist, they
are shown rather than hidden -- labelled
`source: "legacy_local_events (BIASED: omits stop-outs)"`.

## File logging (8.1, H-11)

There was no `FileHandler` anywhere, despite the README claiming logs are
written to files. After a crash or an overnight run there was nothing to read.
Added a `RotatingFileHandler` (5 MB x 10).

`DecisionLog` writes one JSON record per iteration: bar, signal, strength, ATR,
spread, session, news, open positions, which gate blocked the entry, and the
resulting action. Prose logs say what happened; this says *why*, in a form that
loads into pandas. "Why did it not trade yesterday?" is a Phase 9 question that
gets asked constantly.

## Circuit breaker (8.2)

Both loops wrapped everything in `except Exception` and slept, with no failure
counter. A broker rejecting every order produced an **indefinite silent outage
that looked exactly like a running bot** -- process up, log ticking, nothing
trading. Five consecutive failures now halt trading and log at CRITICAL. A
success clears the consecutive count but does **not** un-trip a tripped breaker;
that needs a deliberate reset.

## Kill switch and flatten (8.3)

A sentinel file `STOP` in the project root stops new entries, checked every
iteration. A file deliberately: it works from any shell without the bot
listening on a socket.

`--flatten` is a **separate** command that closes everything and exits. Stopping
entries and liquidating are different decisions, and a system whose only pause
button is "close everything" gets used to close everything when a pause was
wanted.

`SIGINT`/`SIGTERM` now set a flag the loop checks, so the current iteration
finishes and the connection closes; a second signal still force-exits.

## Health (8.4)

`logs/health.json` carries last loop time, connection state, open positions,
daily P&L, breaker state, kill-switch state and any halt reason. `--health`
**reads the file and never connects to a broker** -- answering "are you
healthy?" by contacting the broker turns a diagnostic into a side effect. A test
asserts it with the MT5 entry points poisoned.

## Gate C-1 status

| Criterion | Status |
|---|---|
| All Critical and High findings closed, with tests | **Met in code** -- 288 tests |
| Adversarial scenarios 1-11, 23 vs mocked MT5 | **Not done** -- needs the audit's §13 list |
| 24h demo soak | **Not done** -- needs a demo run |
| Kill switch verified under load | **Unit-tested only** |

**Gate C-1 is not passed.** Three of its four criteria require running against a
demo account, which is outside the current no-broker-contact constraint.

---

# Phase 9 decisions

## H-08 verified, with one correction to the audit

Exhaustive enumeration over every reachable state:

* `strength` takes **four** distinct values, `{0, 20.0, 40.0, 100.0}` -- not the
  three the audit reports. `40.0` is reachable. **The conclusion is unchanged.**
* Six of the seven separately-tuned thresholds (55, 65, 70, 75, 80, 85)
  partition that set **identically**. Every one is `strength == 100`. Only the
  30 threshold differs.
* Enumerating RSI 0-100 against every reachable Bollinger state:
  **RSI and Bollinger cannot change the signal at all.** The decision is exactly
  the sign of `EMA_fast - EMA_slow`.

Seven knobs that were one knob; three indicators that were one indicator.

`strategies/signal_strength.py` replaces it with a continuous score from four
separable inputs. **This is a repair, not a hypothesis** -- it removes a
measurement artefact; it does not supply an edge. The hypothesis is now written
down, with its falsifiers, in `docs/STRATEGY-HYPOTHESIS.md`.

## C-07: the backtester executed zero trades

`if signal == 'buy'` against `generate_signal` returning `'BUY'`. Never matched,
on any input, and reported 0.00% return -- which looks like an honest answer.

Rewritten as an event-driven engine. Two decisions matter most:

* **Intrabar ordering is pessimistic and explicit.** When a bar spans both stop
  and target, the **stop** is assumed first. OHLC cannot say which came first,
  and the optimistic choice converts losers into winners at exactly the rate
  that makes a coin-flip look like an edge.
* **Sizing uses the live `RiskManager`** through a broker adapter, not a
  reimplementation. A backtest that sizes differently from the live bot measures
  a system nobody will run. It also inherits the live *declines*: trades the
  bot would refuse are counted, not silently taken.

Costs are itemised -- spread by session, commission, swap, slippage as a
distribution, and latency of one bar. The audited model charged none of these.

## H-09 / M-10: an outage looked like a quiet market

`main.py` read `df['RSI_14']` literally, so changing `RSI_PERIOD` raised
KeyError every iteration -- swallowed and retried forever. Fixed in `main.py`
and `run_bot.py`.

`data/quality.py` makes "I cannot decide" a distinct answer from "I decide to do
nothing": warm-up bar counts, named missing columns, duplicate and non-monotonic
timestamps, impossible OHLC, stale feeds, and gap detection that treats weekends
as expected rather than as faults.

## A logging bug found while building this

`setup_logger()` reset the logger's level on **every** call. Six modules call it
at import, several lazily inside functions -- so the backtester turned logging
down for a run and the first lazy `import RiskManager` inside that run turned it
back up. It now leaves an already-configured logger's level alone, and the
backtester configures logging before lowering it.

Worth noting how this was found: I asserted a cause twice and was wrong both
times. Tracing `setLevel` showed it in one step.

## Gate C: NOT ANSWERED

The gauntlet is built and tested; the verdict is not available.

| Step | Status |
|---|---|
| 1 zero-cost sanity | machinery verified on synthetic data |
| 2 **realistic cost -- GATE C** | **requires 2+ years of real M5 gold data** |
| 3-7 OOS, walk-forward, Monte Carlo, sensitivity, regime | built, unrun |

Against synthetic random walks the gauntlet correctly **fails** at step 2 and
prints the "STOP" verdict -- the right answer for a random walk with costs, and
evidence the instruments work. It says nothing about the strategy.

**Gate C needs real data, which needs the broker.** Everything else in Phase 9
is complete and offline-testable.

---

# Symbol fix and Phase 9 wiring

## config.SYMBOL was wrong, and the bot could not trade at all

`'XAUUSDm'` (an Exness-style micro suffix) against a MetaQuotes demo that lists
`'XAUUSD'`. The bot connected, failed the symbol lookup, logged
`Symbol 'XAUUSDm' not found` and exited -- on every start. Now `'XAUUSD'`.

`data/symbol_resolver.py` validates it at startup and, on failure, **lists the
gold-like symbols the broker actually offers**, so the fix is a one-line config
change rather than a hunt through Market Watch.

It deliberately does **not** auto-select a lookalike. Silently picking
something matching "XAU" is how a bot ends up trading a mining CFD, or a 1oz
contract on an account sized for 100oz.

## Phase 9 was built but not wired in -- the audit's own signature

Found by scanning for it. `strategies/signal_strength.py` and
`data/quality.py` were complete, tested, and **called from nowhere** -- exactly
the shape of H-07 (three unused logging methods), C-06 (three unused stop
helpers) and M-03 (an unreachable branch).

Now wired. `BasicTradingStrategy.generate_signal` uses the continuous scorer,
and the live distribution went from **4 distinct strength values to 294**
(variance 441) over 300 evaluations. The loop validates data before signalling
and indicator columns by their *configured* names.

---

# Phase 10 decisions

The plan says Phase 10 is "only worth building if Gate C passed", and Gate C is
not answered. The three **defects** are unconditional bugs and were fixed
regardless; the calendar was built because its rationale does not depend on any
edge.

## Every news check in the system silently evaluated false (H-05)

`get_latest_forex_news()` returns a `dict`; all six consumer sites compared it
against a string. A dict never equals a string, so the entire news subsystem
was dead **while appearing to work** -- the worst failure mode, because nobody
investigates a check that never fires.

Fixed at every site via `sentiment_of()`, which accepts either shape. An AST
test now fails CI if any module compares a raw news value against `"bullish"`
or `"bearish"` again.

## No timeout, inside the trading loop

`requests.get` with no `timeout` waits forever by default. A hung socket
blocked the loop with **no position managed and no stop checked**. Now
`timeout=(3, 5)`, and the fetch moved to a background `NewsRefresher` thread --
the loop reads a cache and never blocks on the network at all.

## UnboundLocalError in every fallback path

`cache_age` was referenced in three error handlers but assigned only inside an
`if`. The rate-limit fallback -- the code written specifically to keep working
when NewsAPI says no -- **crashed instead**. Now computed by a helper that
returns None when there is no cache.

## There was no economic calendar at all

`HIGH_IMPACT_NEWS_CLOSE` and `ECONOMIC_EVENT_CLOSE_MINUTES` were referenced
nowhere. The bot traded straight into CPI, NFP and FOMC.

`utils/economic_calendar.py` reads a local JSON file (populate it from any
provider) and enforces a blackout window before *and after* high-impact events
-- after matters because the spread is widest just after a release.

Three outcomes, deliberately distinct: an event is scheduled; nothing is
scheduled; or **the schedule is unknown**. An unreadable calendar does not read
as "nothing is happening".

Without a calendar file it falls back to a coarse recurring-release estimate,
so the unconfigured case is not wide open. That is a safety net, not a
substitute for real data.

## VADER sentiment: OFF

`NEWS_SENTIMENT_CLOSE = False`. Averaging headline tone over
`"gold OR USD OR forex OR XAU"` is ambiguous by construction: **USD-bullish and
gold-bullish are opposite signals for the same trade**. The plumbing is fixed
and the factor is reachable again, but it stays off until it demonstrates
out-of-sample value. The calendar stays on, because avoiding a known volatility
event is risk management rather than signal.

---

# Bug found via IDE diagnostics (Pylance)

## `main.py` called an undefined `get_open_positions`

Pylance flagged `main.py:313` (`reportUndefinedVariable`). Confirmed real: the
name is not imported anywhere in `main.py`. Every other call site in the file
correctly uses `executor.get_open_positions(...)`; this one was a bare call
left over from an earlier edit. It would have raised `NameError` on the first
loop iteration where `AUTO_CLOSE_ENABLED` was true and a position was open --
`python -m compileall` cannot catch this class of bug, since it is a runtime
name lookup, not a syntax error.

Fixed to `executor.get_open_positions(config.SYMBOL_PHASE5)`.

Two regression tests added to `tests/test_observability_phase8.py`:
`test_every_bare_call_in_main_is_a_real_name` (a general AST check: a name
called bare, never bound/imported, but used elsewhere only as an attribute
access, is exactly this shape of missing-prefix mistake) and the specific
`test_get_open_positions_is_always_qualified`. Both were verified to fail
against the reintroduced bug and pass against the fix.

---

# Gate C: run against real data (user-authorized broker read)

## What happened

Per explicit user instruction ("do backtest with the demo acc credentials"),
made a single read-only connection to the demo account (5055880630,
MetaQuotes-Demo) to fetch real historical XAUUSD M5 data. `scripts/
fetch_historical_data.py` calls only `symbol_info`, `symbol_select` and
`copy_rates_from_pos` -- no `order_send`, no `TradeExecutor`, no
`RiskManager`. It also captured the real broker `SymbolSpec` (contract size,
tick value, swap rates) to a JSON file, so the backtest uses measured values
rather than guessed defaults. Disconnected immediately after. No further
broker connection was made for the actual gauntlet run
(`scripts/run_gate_c.py`), which is 100% offline against the saved CSV.

MT5 caps `copy_rates_from_pos` at 99,999 bars per call (measured: 100,000
returns "Invalid params"); chunking past that returns "Terminal: Call failed"
-- this server's retained history for the symbol is exactly 99,999 M5 bars,
2025-04-07 to 2026-09-11, **1.43 years**, short of the plan's 2+ year target.
That is the server's retention limit, not a fetch bug.

## Result: gauntlet FAILS at step 4 (walk-forward)

Full detail in `docs/STRATEGY-HYPOTHESIS.md`. Summary: **step 2 (Gate C's own
criterion) passed** -- positive expectancy ($0.20/trade) after real measured
spread, real swap, and documented-unverified commission/slippage, on 1,687
trades. Step 3 (out-of-sample) also passed. **Step 4 (walk-forward) failed**:
expectancy across four rolling windows was +0.72, **-0.28**, +1.11, +0.23 --
three of four positive, but the plan's criterion is consistent sign across
every window. Per the plan's stop-at-first-failure rule, steps 5-7 were not
run.

This is the gauntlet doing its job, not a wasted result. The sample is
dominated by an extraordinary secular gold rally (close $2,959 -> $5,589 across
1.43 years); a result built mostly on one long trend is exactly the setup a
walk-forward check exists to catch, and it caught it here on real money-shaped
data rather than a synthetic random walk.

## Decision: do NOT proceed to Phase 11

The plan's overview states Phases 10-13 only proceed if Phase 9 passes; Phase
11 (demo forward test) also carries its own Gate-C dependency in the phase
table. Phase 9's gauntlet did not pass -- it failed at step 4. Starting a
multi-week demo forward test on an unvalidated, regime-inconsistent
configuration is a decision for the user, not an automatic continuation.

Phase 12 (architecture & cleanup) does not depend on Gate C -- it is general
maintainability work -- and proceeds next.

## Reproducing this

1. `env/Scripts/python.exe scripts/fetch_historical_data.py` -- one read-only
   broker connection, saves `data/historical/XAUUSD_M5.csv` and
   `XAUUSD_spec.json` (both git-ignored: account-specific, regenerable, and
   `.gitignore` already excludes generated data).
2. `env/Scripts/python.exe scripts/run_gate_c.py` -- fully offline, ~5-6
   minutes, prints every gauntlet step and the final verdict.

# Phase 12 decisions (architecture & cleanup)

## One MT5 client (12.1)

`dashboard.py` imported MT5 helpers and called `get_candles`, which opened a
second terminal connection from the Streamlit process. `run_bot.py` connected
too. The MetaTrader5 package allows one connection per process and is not
thread-safe, and two processes on one terminal fight over it. `main.py` is now
the only broker client. It publishes `logs/health.json` (including a broker
snapshot: account, positions, tick), `logs/candles.csv` (atomic write) and
`logs/decisions.jsonl`, and closed deals go to `trades.db`. The dashboard
(`dashboard_data.py`) and the Flask API (`run_bot.py`) only read those. Both
report **stale** after 600 s with no loop heartbeat instead of showing old
numbers as live. `/signals` was deleted: it was hardcoded to `XAUUSDm` and
nothing used it. A subprocess import-graph test fails if the dashboard or API
imports MetaTrader5 again.

## The dashboard's controls lied

* **The kill switch was fake.** It set a Streamlit session variable that the
  bot never read. It now creates and deletes the real `STOP` file.
* **"Apply Strategy Settings" changed nothing** the bot used. Removed; the tab
  now shows the live config read-only.

A control that looks like it works is worse than no control.

## SQLite connections were never closed

`with sqlite3.connect(...)` commits or rolls back but does **not** close the
connection. Handles leaked on every call. On Windows that also locked the file:
this showed up when a test's temp directory could not be deleted.
`utils/db.connect` closes the connection and sets WAL mode and a 10 s busy
timeout, so the bot writing and the dashboard reading do not block each other.
Every caller uses it.

## The trailing-stop throttle crashed on real positions

`should_update_trailing_stop` stored its timestamp as an attribute on the MT5
position. Real positions are immutable namedtuples, so this raised on the first
call against a real broker, and mocks hid it. It is now a per-ticket dict,
cleared by `forget_position`. Trailing is off, so this never ran live.

## No market state in config (12.3)

`config.CURRENT_ATR`, `CURRENT_TREND_STRENGTH` and `CURRENT_NEWS_SENTIMENT` were
module globals used as a message bus. Nothing wrote them in the live loop, so
readers got startup placeholders. They are deleted, and live values are passed
as arguments. The test fake deletes these attributes, so any regression that
reads them fails.

## The executor ignored its injected config

16 executor methods (the whole exit chain and the scaling code) did
`import config` instead of using `self.config`. Tests that injected a config
were testing the global module, and older tests worked around it by assigning
`ex.config = config`. All now use `self.config`. Found while writing the
close-chain tests.

## Exit-chain defects found by testing it (12.2)

`should_close_trade` runs every bar (`AUTO_CLOSE_ENABLED=True`) and had no
direct tests. Writing them (`tests/test_close_chain_phase12.py`) found:

* **Signal weakening could never fire.** It needed strength
  `< EXIT_WEAKENING_MAX_STRENGTH` (30) and also the opposite-candle confirmation
  (`>= EXIT_REVERSAL_MIN_STRENGTH`, 70) on the same reading. It now fires on two
  consecutive bars below 30. Making it work would add a live exit that no
  backtest has measured (the backtester models only SL/TP), so it sits behind
  the new `SIGNAL_WEAKENING_CLOSE = False`.
* **"Two consecutive candles" was two consecutive calls.** Confirmation history
  was one list shared by every position and appended on every call. Two positions
  on one bar, or one bar evaluated twice, counted as two candles. It is now keyed
  by ticket and bar timestamp.
* **HOLD counted as an opposite signal** in that confirmation (`!= position
  type`). It now requires the actual opposite signal.
* `detect_trend_reversal` hardcoded `RSI_14` (KeyError for any other
  `rsi_period`) and raised on frames missing indicator columns. Both fixed.
* `main.py` computed `generate_signal` and `detect_trend_reversal` for every
  open position and then threw the results away. Removed.

**Note for Gate C:** the discretionary exits that are on (opposite signal, trend
reversal, break of structure, volatility spike, 24 h age, drawdown) are not
modelled by the backtester. The live bot is not exactly the system that was
tested.

## Broker tick value disagrees with contract size

The demo XAUUSD spec reports `trade_tick_value = 0.1` per 0.01 tick (about $10
per lot per $1.00 move) and `trade_contract_size = 100` ($100). All sizing and
P&L use the contract size. If the tick value is the true figure, the bot
overestimates risk 10× and trades 10× smaller than intended. That is
conservative, not dangerous, but it is wrong. `SymbolSpec.load` now logs a
warning when the two disagree by more than 5%. **Resolve with
`mt5.order_calc_profit` on the demo before Phase 11.** Sizing was not changed on
a guess.

## Units in names, and a schema (12.4)

Keys renamed so the unit is in the name, across 12 files including tests:
`MIN_HOLDING_TIME` → `MIN_HOLDING_SECONDS`, `MT5_TIMEOUT` → `MT5_TIMEOUT_MS`,
`ORDER_DEVIATION` → `ORDER_DEVIATION_POINTS`, `ORDER_RETRY` →
`ORDER_MAX_ATTEMPTS`, `EMERGENCY_CLOSE_THRESHOLD` →
`EMERGENCY_CLOSE_DRAWDOWN_FRACTION`, `MAX_LOT_SIZE` → `MAX_LOTS_PER_ORDER`,
`MAX_CORRELATED_POSITIONS` → `MAX_TOTAL_POSITIONS` (it never measured
correlation), and others. `utils/config_validation.py` gives every key a type,
range, unit and secret flag, plus cross-key rules (EMA fast < slow, risk per
trade ≤ portfolio risk, emergency drawdown ≥ halt drawdown, and so on).
`main.py` validates before connecting and lists every problem at once. Secrets
are masked in messages. `tools/check_config.py` now finds references by AST
instead of regex, and excludes tests, so a key used only by a test counts as
dead.

## Dead code deleted

`BasicTradingStrategy.backtest()` (executed zero trades, C-07),
`should_close_position()`, `TradeExecutor._check_take_profit_reached()` and
`_check_stop_loss_hit()` (removed from the close path in 5.6), module-level
legacy `execute_trade` / `close_position` / `get_open_positions`,
`RiskManager.get_recent_performance()` and `get_news_impact_level()` (returned
invented numbers), and config keys `MIN_LOT_SIZE`, `SCALING_ENABLED`,
`TRAILING_STOP_ACTIVATION_PRICE`, `TRAILING_STOP_DISTANCE_PRICE`.

## Scaling subsystem: NOT wired, NOT deleted

`evaluate_position_scaling` / `scale_up_position` / `scale_down_position` /
`close_position_partial` (165 statements) are called from nowhere in the live
loop. `ADAPTIVE_SCALING_ENABLED = False`, commented "NOT WIRED". Left in place
pending the user's decision; recommendation is to delete it.

## Loss-streak halt

After `MAX_CONSECUTIVE_LOSSES` (5) losing broker deals in a row, new entries are
blocked. Only a person clears it (`python main.py --ack-loss-streak`), which
records an acknowledgement cursor in `trades.db`. A restart does not clear it.

## Order-send exceptions are "unknown", not "failed"

An exception from `order_send`, or a result with no readable retcode, may still
have filled. Treating it as a failure and retrying can open a second position.
Both now go to reconciliation by dedup token, the same path as a timeout.
`TradingDisabled` is still re-raised.

## Section 13 adversarial scenarios

25 scenarios, plus variants, in `tests/test_adversarial_section13.py`. Three are
known gaps, marked `expectedFailure`. Each was confirmed to fail on a real
assertion, not an error:

* s15: session boundaries are fixed UTC and ignore DST;
* s16: `SESSION_END_CLOSE` defaults to False, so positions are held into the
  weekend;
* s24b: a failed SL modification is not retried or escalated (moot while stop
  modification is off).

## Coverage (2026-09-13, source files only, tests excluded)

64.5% overall; 67.1% excluding the unwired scaling subsystem. The executor is
about 77% excluding scaling. `main.py` (11%) and `dashboard.py` (0%) are covered
only by import, startup and bare-mode smoke tests. Their logic has been moved
into tested modules where practical (`execution/control.py`,
`dashboard_data.py`).

## Outstanding for the user

* NEWS_API_KEY: the value in `.env` was printed in plain text in a session
  config listing during this phase. Rotate it.
* Decide: delete the scaling subsystem? Enable `SESSION_END_CLOSE`?
* Verify tick value against contract size on the demo (above).
* Phase 11 remains blocked by the Gate C step 4 failure.
* Nothing from Phases 0–12 has been committed.

(All but the key rotation were resolved in the follow-up below.)

# Phase 12 follow-up and Phase 13 readiness (2026-09-13)

The user asked for every open issue and decision to be resolved by judgement,
and for the next phase. Phase 13 is the **live-money** rollout and the plan
allows it "only after Gates A–D". Gate C had failed and Gate D had not run, so
no live trading was started. Phase 13 was built as a guardrail instead, and the
open issues were fixed. The most important discovery was that the backtest did
not measure the bot, and measuring the real bot changed the verdict.

## Broker facts measured, not guessed (read-only probe)

`scripts/probe_broker_facts.py` makes one read-only connection and places no orders.

* **Tick value.** `order_calc_profit` for 1.00 lot over a $1.00 move = **$100.00**.
  The contract size (100) is right, and `trade_tick_value` (0.1) is a broker
  quirk. `SymbolSpec.load` now asks the calculator. It refuses to start if the
  calculator contradicts the contract size, and warns once when there is no
  calculator to ask (the backtest).
* **Clock.** The market was closed (Sunday), so a live tick could not measure
  the offset. The history could: the daily break sits at 00:00–01:00 server
  time in both US summer and winter, and gold breaks at 17:00 New York, so
  **server = New York + 7 h**. The live tick (Friday 22:59:59 server = 15:59
  New York) agrees.

## Broker server time was treated as UTC everywhere

MT5 stamps bars, positions, deals and orders in server time. `utils/market_time.py`
(`BrokerClock`) now converts. Every consumer was wrong:

| Where | Effect before the fix |
|---|---|
| position age (`time.time() - position.time`) | a new position looked 3 h in the future: the minimum hold ran 3 h long, the 24 h exit fired 3 h late |
| candle staleness | server-time bars looked 3 h fresh: a feed up to 3 h stale passed |
| deal sync window | deals from the last 2–3 h were invisible: the **loss-streak halt lagged 3 h** |
| `realised_pnl_today` window | the **daily loss limit could not see the last 2–3 h of losses** |
| `_find_order_by_token` window | an order that had just executed could not be found, so **a retry after a timeout could send a duplicate order** |
| sessions and weekend close | fixed UTC hours, an hour wrong for half of each year (adversarial s15) |
| backtest data | server times used as UTC: session spreads and swap were mis-assigned |

At startup the configured offset is checked against a live tick, and a mismatch
refuses to start. A tick that is an exact number of half-hours old is not
mistaken for an offset: offsets beyond ±14 h are rejected (caught by a test).

## The backtest measured a different system

| | Backtester (Phase 9) | Live bot |
|---|---|---|
| stop / target | 2 × ATR, TP_RISK_REWARD | `dynamic_stop_loss` / `dynamic_rr_ratio` |
| exits | SL/TP only | seven discretionary exits |
| entry gates | strength | reversal hold, calendar, spread, halts, Friday cutoff |
| signal volatility | ATR column | **bar-range proxy**: `main.py` never added the ATR column |

Fixes:
* `strategies/trade_plan.py` (stop/target) and `strategies/exit_rules.py` (exits)
  are single implementations called by both `main.py` and
  `backtest/live_engine.py`.
* `main.py` now adds the ATR column.
* `TP_RISK_REWARD` became unreferenced and was deleted.
* The engine also fills a gap through the stop at the open, not at the stop
  level (a Monday gap is not a 1R loss), and charges swap at the 17:00 New York
  rollover with Wednesday ×3.

## Defects found while building the shared rules

* **The reversal hold could enter the wrong way.** A suppressed SELL returned
  the held "BUY" with the SELL bar's strength, which could clear the entry
  threshold. It now returns HOLD.
* **Risk exits were blocked by the minimum hold.** A position opened at 16:40
  New York on a Friday could not be closed by the weekend exit and would ride
  the gap. `RISK_FACTORS` (weekend close, drawdown) now ignore the minimum hold,
  and entries too close to the weekly close are blocked.
* **`dynamic_stop_loss` compared the news dict with a string** (H-05 again).
  Both dynamic functions also used absolute ATR thresholds ("typical 1–5"),
  which pinned them at their caps with gold at $3,000–5,500. They now use ATR
  relative to its 288-bar median.
* **Headline sentiment was still live.** Phase 10 recorded it as off, but
  `main.py` still vetoed entries and adjusted targets with it, and no historical
  headlines exist to test it. It is now behind `NEWS_SENTIMENT_TRADING_ENABLED = False`.
* **The calendar fallback used UTC hours**, so summer releases were blacked out
  an hour late, and "FOMC" was any mid-month Wednesday. It now uses New York
  time and the Fed's published 2025–2026 meeting dates. There is still no dated
  calendar file: CPI dates are approximated (days 10–15).
* **Opening deals were not recorded.** Commission charged on the open was lost,
  and holding time could not be measured. `record_deal` also turned the
  legitimate 0 values (`DEAL_TYPE_BUY`, `DEAL_ENTRY_IN`) into −1 via `int(x or -1)`.
  Trades are now aggregated per position (`closed_trades()`). The loss streak,
  statistics and dashboard history all use them.
* **`close_position_by_ticket` crashed** on a `None` broker result.

## Decisions taken

* **Weekend close ON** (`SESSION_END_CLOSE = True`, 30 min buffer). A weekend gap
  fills stops beyond the risk model; the backtest's largest loss (−$72.60) was
  exactly such a gap. Closes s16.
* **Scaling deleted**, with its config and `may_scale`/`increment_scaling`/
  `place_order`. It had no caller, and a scale-in is a second position, which
  the cap forbids. Old database columns are kept for compatibility.
* **Also deleted as dead:** `execute_trade` (hardcoded `XAUUSDm`, a $10 stop and
  0.1 lots), the four `close_*_positions` helpers, `utils/plot_utils.py`,
  `data/fetch_live_data.py` (local-time windows), and `matplotlib`.
* **Stop modification retries, then escalates** (s24b): CRITICAL log,
  `stop_failures`, and a circuit-breaker failure in `main.py`. The previous
  server-side stop stays in place.
* **`--clear-halt`** added: a drawdown halt could previously only be cleared by
  editing a file.
* `tzdata` pinned (Windows has no IANA database).

## Gate C, re-run with the live rules: FAILED at step 2

The gauntlet judges the strategy, so its runs disable the account halts. The
first live-rules gauntlet did not, and its step 2 "passed" on the four months
before the drawdown halt stopped all trading. That mistake was caught and
corrected before recording a verdict.

* Step 1 PASS: 2,052 trades, +$0.37/trade at zero cost.
* **Step 2 FAIL: −$0.2278/trade over 1,813 trades**; profit factor 0.95; win
  rate 31.0%; max drawdown 50.8%; costs $902.88.
* With halts on, as live: halted 2025-08-08 after 460 trades.

Full reports are in `docs/reports/`; analysis is in `docs/STRATEGY-HYPOTHESIS.md`.
**Decision: STOP.** No Gate D, no Phase 13. No variant was tried after seeing
the result, and any future one must be pre-registered.

## Phase 11 tooling and Phase 13 guardrail

* `scripts/forward_test_report.py`: offline report of a demo period from broker
  deals, in the same format as the backtest report; comparison with the backtest
  on Gate D measures with stated tolerances; optional read-only broker
  reconciliation. It writes Gate D's automatic result to `gates.json`.
* `execution/rollout.py`: a live login is refused unless Gate C passed, Gate D
  passed with a named sign-off, the settings are one position, 0.01 lot and a
  daily loss limit ≤ 2%, and a daily review (`--record-review`) is under 36 h
  old. `ALLOW_LIVE=true` is necessary but no longer sufficient. Demo accounts
  are unaffected.

## Still outstanding

* Commission and slippage remain assumptions until a real statement exists.
* No dated economic calendar file; CPI days are approximated.
* Nothing has been committed.

NEWS_API_KEY has been rotated by the user (2026-09-14).

# H1 timeframe test (2026-09-14)

Per the user's instruction ("start with option 1, if it doesn't work move to
option 2"), the plan's own fallback was tried before a new hypothesis: the
same unmodified signal re-run on H1 bars, where a fixed round-trip cost is a
smaller fraction of the expected move.

## `scripts/fetch_historical_data.py` and `run_gate_c.py` gained a `--timeframe` override

Fetching and backtesting a different timeframe than `config.TIMEFRAME` needed
to not perturb the M5-configured bot or its recorded Gate C result. Both
scripts now accept `--timeframe H1` and derive everything (bar length, data
paths, report filenames) from the override, falling back to config when absent.
A run at a timeframe other than `config.TIMEFRAME` is explicitly **not**
recorded to `gates.json` -- an exploratory run must not silently satisfy Gate C.

## Bug caught while wiring it: BarGate used the wrong timeframe

`LiveRulesBacktester` built its `BarGate` from `config.TIMEFRAME` regardless of
what timeframe the DATA was actually at. `BarGate` converts bars-based rules
(the reversal hold, the weekly-close entry cutoff) using its own bar length in
seconds. Running H1 data with `config.TIMEFRAME` still `"M5"` would have made a
5-bar hold last 25 hours instead of 5, and mismeasured the weekly-close cutoff
the same way -- silently, since nothing would raise. `LiveRulesBacktester` now
takes an explicit `timeframe` parameter (defaulting to `config.TIMEFRAME`) and
derives `bar_seconds` from it. Caught before any backtest ran on it; covered by
`tests/test_live_fidelity.py::test_bar_gate_uses_the_actual_data_timeframe`.

## Result: FAILED, more decisively than M5

17 years of real H1 data were fetched (2009-09 to 2026-09; the server retains
far more H1 history than M5). Diagnostic (halts disabled): -67.6% over 1,373
trades, expectancy -$0.49/trade, **t = -2.65** (versus -0.89 on M5 -- a
materially stronger signal that the loss is real, not noise). No session was
profitable. Gate C step 2: FAILED, -$0.4925/trade over 1,373 trades. Full
detail in `docs/STRATEGY-HYPOTHESIS.md`.

**Decision: the higher-timeframe fallback is exhausted.** Per the user's own
sequencing, the next step is a new signal hypothesis, pre-registered in
`docs/STRATEGY-HYPOTHESIS.md` before it is run.

# Audit follow-up: fixes, dead-code removal, and Hypothesis 3 (2026-09-14)

The user asked for a fresh audit of the strategy, indicators, execution and
risk layers, then for the findings fixed and a genuinely different, realistic
strategy implemented. Findings and fixes:

## Indicators disagreed with the broker's own chart

`calculate_rsi` and `utils/indicators.atr` used a plain rolling mean for the
smoothed average, not Wilder's exponential smoothing that MT5's own `iRSI`/
`iATR` (and most reference implementations) use by default. Not a correctness
bug -- SMA-based RSI/ATR is a real, documented variant -- but it meant the
bot's numbers would not match what a person sees on the MT5 chart while
sanity-checking it, and the 30/70 RSI thresholds (tuned by convention against
Wilder's smoothing) were being applied to a differently-shaped series. Both
now use `ewm(alpha=1/period, adjust=False)`, Wilder's definition exactly. RSI
was also being smoothed a SECOND time with an unexplained 3-bar moving
average on top -- removed.

## Dead code across every indicator module

`get_rsi_condition`, `get_ema_trend`, `get_bollinger_position` were imported
into `strategy_basic.py` and never called. `rsi_divergence` and
`bollinger_reversal_signal` were never imported by anything. `RSI_signal`,
`RSI_crossover`, `EMA_crossover`, `BB_signal`, `BB_bandwidth`, `BB_squeeze`,
`BB_percent` were computed into the DataFrame on every single bar of every
backtest and never read -- `strategies/signal_strength.py` computes %B itself,
independently, from the band columns that are actually used. All removed.
`strategy_basic.py`'s `generate_signal` also returned a `scaling_factors` dict
that nothing consumed -- a leftover from the scaling subsystem deleted in
Phase 12 -- removed along with the now-single-purpose `buy_score`/`sell_score`
debug variables.

## RiskManager repeated the H-04 mistake in a second place

`open_risk_fraction` and `current_open_positions_count` called
`mt5.positions_get()` **directly**, so a disconnected terminal read as "zero
open risk" / "zero open positions" -- the exact fail-open bug Phase 6.4 fixed
once already in `TradeExecutor.get_open_positions`. Reachable only after
`enter_trade`'s own earlier, safe check succeeds in the same call, so this was
not exposed in practice, but a connection dropping *between* the two calls in
one `enter_trade` invocation would have been. Extracted the safe query into
`execution/broker_query.py`; both `TradeExecutor` and `RiskManager` now call
the one implementation. `enter_trade` converts a resulting `BrokerQueryFailed`
into the same clear refusal its earlier check already used. Tests:
`tests/test_broker_query.py`.

## Sizing was not re-checked after the broker widened a stop

`enforce_stops_level()` (Phase 2.3) correctly widens a stop that is inside the
broker's minimum distance -- but position size was computed against the
*original*, narrower distance, and nothing re-derived it afterward. On this
broker `trade_stops_level` is 0, so this never fired, but a broker with a real
minimum distance would have silently carried more dollar risk than
`RISK_PER_TRADE_FRACTION` authorised, with no log line saying so.
`_place_market_order` now shrinks the position proportionally when the actual
stop distance exceeds the intended one (same dollar risk, smaller size), and
declines the trade outright if the shrink would need less than the broker's
minimum lot -- consistent with the existing "decline rather than silently
round up" sizing policy. Tests:
`tests/test_executor_paths.py::TestSizingHoldsRiskWhenTheStopIsWidened`.

## A written safety check that nothing ran

`VolatilityRegime.assert_thresholds_are_reachable` was documented as "the
startup assertion the plan asks for" (it would have caught M-03, absolute
thresholds unreachable against the real ATR distribution) but was never
called from anywhere. Wired into `main.py`'s loop, checked once as soon as
enough ATR history exists, logged rather than fatal. Also: `classify()` was
sorting the same ATR history twice per call (once per percentile) -- every
bar, of every backtest; now sorts once.

## Hypothesis 3: trend following with a real trailing exit

Hypotheses 1 and 2 both cap every winner at a fixed multiple of the initial
risk (`TradePlan.rr`). That is the wrong shape for trend following, whose
entire case rests on a small number of large winners funding many small
losers. Built as a genuinely different mechanism: a 200-bar EMA regime filter
gating a 20-bar Donchian breakout, with NO fixed take-profit -- a chandelier
ATR trailing stop (`backtest/live_engine.py`) replaces it, ratcheting only in
the trade's favour. `strategies/trade_plan.TradePlan` gained an optional
`trailing_atr_mult` field and `plan_trend_entry()`; `LiveRulesBacktester`
gained a `plan_fn` parameter so a plan builder is now pluggable per strategy.
Pre-registered in `docs/STRATEGY-HYPOTHESIS.md` before it was run, per the
process the last two hypotheses followed. Backtest-only: `TRAILING_STOP_ENABLED`
stays off for live trading regardless of this result, by the user's standing
instruction -- this is `backtest/live_engine.py` machinery, not a change to
`execution/trade_executor.py`'s live stop-modification path.

Tested at **$10,000**, not the project's $1,000 baseline: at $1,000 the wider
ATR-based initial stop this hypothesis needs declined essentially every
qualifying signal below the broker's minimum lot (0 of 52 candidates sized on
a 20,000-bar sample) -- the undercapitalisation this same audit flagged for
Hypotheses 1/2, more severe here by design. Reported explicitly as a deviation
rather than silently changed.

**Result: FAILED**, and more decisively than either prior hypothesis. 17 years
of H1 data, halts disabled: -57.3% (**t = -3.89**, the strongest signal yet
that a result here is real, not noise), win rate 31.3%, payoff ratio 1.53 --
below the ~2.2 a 31% win rate needs to break even. The hypothesis's own
falsification test (stated before running it) was whether trailing produced a
payoff ratio well above 1; it produced 1.53, better than Hypotheses 1/2's
near-1.0 but not enough. Gate C: FAILED at step 2, -$7.47/trade over 767
trades. Full detail in `docs/STRATEGY-HYPOTHESIS.md`.

## Where this leaves the project

Three mechanistically different hypotheses -- momentum state-following,
volatility-confirmed breakout, and trend following with a real trailing exit
-- have now failed Gate C on gold at M5 and/or H1, two of them with a
t-statistic beyond -3. No further parameter or timeframe variant of price-only
technical signals should be tried without the user's explicit direction: the
evidence at this point favours concluding this indicator family does not have
a demonstrated edge on this instrument, over continuing to search it.

# Testing the mechanism on a different symbol (2026-09-14)

The user asked whether a different instrument, rather than another technical
variant, should be tried next. Clarified: two distinct ideas -- a genuinely
different DATA SOURCE for gold (real yields, DXY, positioning -- not
available through this MT5 feed, a much bigger lift), versus running the
same, already-tested MECHANISM on a different symbol (cheap: same
infrastructure, same broker connection). The user chose the latter.

## What this broker actually offers

A read-only symbol probe (`scripts/probe_symbols.py`, no orders) found this
demo account has no BTCUSD, SPX500, NAS100, DJ30 or GER40. It does have
EURUSD (only 2.5 years of M5, no H1), and three index CFDs with deep H1
history: US500 and US30 (both back to 2012, 63k H1 bars), USTEC (2022). US500
was chosen: deepest history tied with US30, and equity indices are known to
trend more persistently than FX, which matters specifically for re-testing
Hypothesis 3.

## `fetch_historical_data.py` and `run_gate_c.py` gained a `--symbol` override

Same pattern as the existing `--timeframe`/`--strategy` overrides: exploratory
runs never touch `config.SYMBOL`, and a run at a different symbol is not
recorded as the project's Gate C.

## `resolve_symbol` refused to even READ US500's history

`main.py`'s live path correctly refuses a symbol with `trade_mode=0`
(disabled for trading) before it could ever place an order. The fetch
script -- which the fetch script's own docstring guarantees never calls
`order_send`, `TradeExecutor` or `RiskManager` -- inherited the same refusal
from the shared `resolve_symbol()`, and US500 is `trade_mode=0` on this demo
account (readable, not tradeable here). Added `require_tradeable=False` for
read-only callers; `main.py`'s call is unchanged and still requires it.

## A real bug found by testing a second symbol: Gate C step 1 used gold's contract size for every instrument

Step 1 (zero-cost sanity) built its cost model from a module-level `ZERO_COST`
constant that hardcodes `contract_size=100.0, point=0.01` -- gold's values,
baked in at import time. On US500 (real `contract_size=1.0`) this sized every
trade as if 100 units traded per lot instead of 1: a 100x sizing error that
rounded almost every candidate below the broker's minimum lot. Step 1 saw 3
trades over 14 years where the realistic-cost run in the same session saw
hundreds. This was invisible on gold for the entire project so far because
the hardcoded defaults happened to already equal gold's real spec.

Fixed at the source: `CostModel.zero_cost_variant()` derives a zero-cost copy
from the REAL cost model (this run's actual point and contract_size), and
Gate C's step 1 now calls it instead of the shared constant. `ZERO_COST`
itself is kept, marked deprecated, only because existing tests use it
correctly with gold-shaped synthetic data. Tests:
`tests/test_zero_cost_variant.py`.

**This is exactly the value of testing a second instrument**: a defect a
single-symbol project could carry indefinitely, because its one symbol's
numbers happened to match the hardcoded assumption.

## US500 trend-following result

See `docs/STRATEGY-HYPOTHESIS.md` for the full US500 write-up, including a
separate caveat about the $7/lot commission assumption's fit on an index CFD
whose lot sizes are far larger than gold's, and the pre-commission figure
alongside the full-cost one.
