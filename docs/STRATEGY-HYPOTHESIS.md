# Strategy hypothesis

Phase 9.3 asks for something the repository has never contained: a written
answer to *why should this have positive expectancy on M5 gold?*

---

# Hypothesis 2: breakout / volatility expansion (pre-registered 2026-09-14, FALSIFIED)

Both the M5 and H1 tests of Hypothesis 1 (an EMA(12/26) state-follower) failed
Gate C, with the H1 test's t = -2.65 a materially stronger signal of a real
loss than a curve-fit artefact. Per the user's instruction, this is a
genuinely different mechanism, not a parameter or timeframe change of
Hypothesis 1.

**Mechanism.** Hypothesis 1 followed a moving-average trend STATE (is the fast
EMA above or below the slow one, right now). This hypothesis instead looks for
a STRUCTURAL EVENT: price closing outside its recent trading range, at the
same moment volatility is expanding rather than contracting.

**The stated reasoning.** A Donchian-channel breakout (close beyond the
highest high / lowest low of the prior N bars) marks a level the market has
respected recently and just stopped respecting. Two things can produce that:
a genuine shift in supply/demand (the move should continue), or a stop-run /
liquidity grab in an otherwise range-bound market (the move should fail and
revert). Volatility expansion -- current ATR meaningfully above its own recent
median -- is the discriminator: a breakout on expanding volatility means
participants are actually pricing something new; a breakout on flat or
shrinking volatility is more consistent with noise poking through thin liquidity
at the range edge. Gold, driven by macro/rate surprises, plausibly produces
exactly this pattern: quiet consolidation, a real informational shock, a
volatility-confirmed range break, and a multi-hour to multi-day continuation.

**Implementation** (`strategies/strategy_breakout.py`, exit rules reused
unmodified from `strategies/exit_rules.py`):

* Channel: prior 20 bars' high/low (current bar excluded, so a bar can't break
  its own range -- the exact defect Phase 5.3 fixed for break-of-structure).
* Entry: close beyond the channel AND `ATR / median(ATR, 288 bars) >= 1.1`.
  Both conditions required -- a breakout alone, or expansion alone, is not
  a signal.
* Strength (0-100): a blend of how far beyond the channel edge (in ATR units,
  0-2 ATR mapped to 0-100%) and how much volatility has expanded (ratio 1.0-2.0
  mapped to 0-100%), weighted 60/40 toward distance.
* Reversal-for-exit: a channel-state flip between the previous and current bar
  (the same two-bar mechanism Hypothesis 1 used for its EMA-state reversal),
  so `TREND_REVERSAL_CLOSE` and the rest of `exit_rules.py` work unchanged.
* Sizing, stop, target, entry gates, and every discretionary exit are IDENTICAL
  to Hypothesis 1 -- only `generate_signal` and `detect_trend_reversal` differ.
  This isolates the test to the mechanism, not the risk management around it.

**Stated so it can be falsified.** Expectancy after realistic costs should be
positive, and should not depend on a single regime or session (Gate C steps
2-7, run via `python scripts/run_gate_c.py --strategy breakout`). If the
expansion filter is doing real work, expectancy WITHOUT it (breakout alone,
no ATR-ratio requirement) should be measurably worse -- that is a specific,
checkable corollary, not just "it should work."

**What would falsify it:** the same criteria as Hypothesis 1 -- expectancy
<= 0 after costs, non-monotonic or flat performance across strength deciles,
profit concentrated in one session/year, or a sign flip under a +/-20%
parameter change.

## Status (2026-09-14): FALSIFIED.

M5, realistic costs: 78 trades, win rate 24.4%, expectancy **-$0.62/trade**,
t = -0.42 (weak evidence, but small-sample -- the double condition, a channel
breakout AND simultaneous ATR expansion, fires rarely). Report:
`docs/reports/backtest-xauusd-m5-breakout-live-rules-no-halts.txt`. Not
retested on H1: a small negative result plus two decisive negative results
from Hypothesis 1 (M5 and H1) did not justify 17 more years of compute chasing
a weak signal with no reason to expect a sign flip.

---

# Hypothesis 3: trend following with an ATR trailing exit (pre-registered 2026-09-14, FALSIFIED)

Hypotheses 1 and 2 share something neither previous write-up named directly:
**both cap every winning trade at a fixed multiple of the initial risk**
(`strategies/trade_plan.py`'s `rr`, 1.2-4.0x). That is a deliberate choice for
a mean-reversion or short-horizon momentum system, but it is the wrong shape
for trend following, where the entire statistical case rests on a small
number of large winners paying for a larger number of small losers -- a fat
right tail that a fixed take-profit amputates by construction. No backtest run
so far has given a trend an opportunity to be large.

**Mechanism**, genuinely different from both prior hypotheses at every layer:

* **Regime filter**: price above a 200-period EMA = long-only regime; below =
  short-only. This is the "trade with the tide" filter that most published
  trend-following research (Donchian, the Turtles, and every CTA variant
  since) treats as close to non-negotiable -- it is what a discretionary
  trend trader means by "don't fight the trend."
* **Entry trigger**: a 20-bar Donchian breakout, taken ONLY in the regime
  filter's direction (a breakout up while below the 200 EMA, or down while
  above it, is not traded). This is one condition doing double duty rather
  than the two independent AND conditions that starved Hypothesis 2's trade
  count.
* **Initial stop**: `TREND_INITIAL_SL_ATR_MULT` (2.5) x ATR at entry -- sizing
  basis, unchanged in spirit from Hypotheses 1 and 2.
* **Exit -- the actual mechanism under test**: NO fixed take-profit
  (`strategies/trade_plan.py`'s `rr` set effectively unbounded). Instead a
  chandelier-style ATR trailing stop: for a long, the stop ratchets up to
  `highest high since entry - TREND_TRAIL_ATR_MULT (3.0) x ATR-at-entry`, and
  only ever moves in the trade's favour. The position is closed when price
  trades back through the trail, or when the 200 EMA regime flips against it
  (`strategies/exit_rules.py`'s existing `trend_reversal` factor, unmodified).
  Every other discretionary exit (volatility spike, break of structure, fixed
  time exit, weekend close) is switched OFF for this test: each assumes a
  short-horizon position and would cut a developing trend on the very noise
  the trailing stop is designed to ride through. Portfolio drawdown protection
  stays on.
* Position sizing, costs, spread/session gates, the calendar blackout, the
  loss-streak and daily-loss halts are the unmodified shared modules -- only
  the signal, the profit target, and which discretionary exits are enabled
  differ from Hypotheses 1/2.

**This tests something the live bot cannot currently run.** `TRAILING_STOP_ENABLED`
is off for live trading by user instruction, and stays off regardless of this
result -- trailing here is backtest-only machinery (`backtest/live_engine.py`),
not a change to `execution/trade_executor.py`'s live stop-modification path.
If this hypothesis passes Gate C, promoting it to a live, trailing-stop-capable
exit is a separate decision for later, not an automatic consequence of a
passing backtest.

**Stated so it can be falsified.** Expectancy after realistic costs should be
positive (Gate C step 2), and the average WINNING trade should be
substantially larger than the average losing trade (a real payoff ratio well
above 1, not the near-1 ratios Hypotheses 1/2 produced) -- if trailing isn't
actually letting winners run further than a fixed target would have, the
mechanism isn't doing what it claims.

**What would falsify it:** the same Gate C criteria as before -- expectancy
<= 0 after costs, a walk-forward sign flip, profit concentrated in one
regime/year, or a parameter-sensitivity sign flip.

## Status (2026-09-14): FALSIFIED, with the strongest statistical signal of the three hypotheses.

Tested at $10,000 initial capital, not the project's $1,000 baseline: at
$1,000 the 2.5x-ATR initial stop declined essentially every qualifying signal
below the broker's minimum lot (measured: 0 of 52 candidates sized on a
20,000-bar sample) -- the same undercapitalisation the Phase 12 audit flagged
for Hypotheses 1/2, more severe here because trend-following stops are wider
by design. $10,000 is a more realistic minimum for a strategy that holds
through multi-day swings; report notes this deviation explicitly.

**Diagnostic (halts disabled), 17 years, H1:**

| Measure | Value |
|---|---|
| Balance | $10,000 -> $4,267.93 (-57.3%) |
| Total trades | 767 |
| Wins / losses | 240 / 527 |
| Win rate | 31.3% |
| Profit factor | 0.70 |
| Expectancy | -$7.47/trade (-0.12 R), **t = -3.89** |
| Average win / average loss | $54.31 / -$35.61 (payoff ratio 1.53) |
| Max drawdown | 64.0% |
| Average holding time | 27.4 hours |
| Costs | $1,997.69: spread 47%, commission 17%, swap 25%, slippage 12% (41% of gross) |

**Gate C (realistic-cost gauntlet): FAILED at step 2**, -$7.4734/trade over
767 trades. Reports: `docs/reports/backtest-xauusd-h1-trend-live-rules-no-halts.txt`,
`docs/reports/gauntlet-xauusd-h1-trend-live-rules.txt`.

### Why the mechanism failed on its own terms

The hypothesis's falsification test was explicit: "the average WINNING trade
should be substantially larger than the average losing trade... if trailing
isn't actually letting winners run further than a fixed target would have,
the mechanism isn't doing what it claims." The measured payoff ratio is 1.53.
At a 31% win rate, break-even needs a payoff ratio of roughly (1 - 0.31) /
0.31 = 2.2. The trailing stop IS doing something -- 1.53 is higher than
Hypotheses 1/2's near-1.0 ratios -- but not enough to clear the bar its own
low win rate sets. The 200-bar trend filter plus 20-bar breakout does not
identify entries clean enough, or the 3x-ATR trail is not loose enough (or is
too loose, cutting winners no further than a moderate fixed target would
have) to produce the fat right tail trend-following depends on. This is a
falsified specific parameterisation of the mechanism, not proof the mechanism
can never work -- a wider trail, a stricter entry filter, or a genuinely
higher timeframe (D1) are the next things a real trend-following redesign
would try, not variations of what was just tested.

### Where this leaves the project

Three genuinely different mechanisms -- state-following momentum, breakout
with volatility confirmation, and trend following with a real trailing exit
-- have now failed Gate C, two of them (H1 momentum and this one) with a
t-statistic beyond -3, which is a strong signal the losses are systematic
rather than sampling noise. No variant has shown a demonstrated edge in gold
at M5 or H1 with this indicator set. Per the plan, this is a STOP: no further
variant should be tried without a materially different data source or
mechanism (e.g. an actual fundamental/positioning signal, not a derivative of
price alone), and that decision belongs to the user.


## What the strategy actually was

Before Phase 9, verified by exhaustive enumeration over every reachable state:

- `strength` took **four** distinct values: `{0, 20.0, 40.0, 100.0}`. (The audit
  said three; `40.0` is reachable. The conclusion is unchanged.)
- Six of the seven separately-tuned thresholds — 55, 65, 70, 75, 80, 85 —
  partition that set **identically**. Every one reduces to `strength == 100`.
- Enumerating all RSI values 0–100 against every reachable Bollinger state
  shows **RSI and Bollinger cannot change the signal at all**. The decision was
  exactly the sign of `EMA_fast − EMA_slow`.

So the system was a **12/26 EMA state-follower on M5 XAUUSD**, wearing seven
tuning knobs that were one knob and three indicators that were one indicator.

## Why that has negative expected value

Not "unproven" — *negatively* expected, for two structural reasons:

**1. M5 gold is dominated by mean-reverting noise.** A state-follower (not a
crossover-trigger — it is long whenever fast > slow) re-enters continuously
through chop. Each oscillation around the EMA cross is a round trip.

**2. The spread is charged on every reversal.** Gold runs 15–35 points in the
London/NY overlap and 50–100+ in the Asian session. At 0.01 point size that is
$0.15–$1.00 per round trip on a strategy whose M5 ATR is $1.50–$5.00. The cost
is a substantial fraction of the move being captured, paid every time, while
the edge is at best a small fraction of it.

A strategy that trades often and captures little is the configuration costs
punish hardest. This is why the plan names "move to a higher timeframe" as the
most likely remedy.

## What Phase 9.3 replaced it with

`strategies/signal_strength.py` produces a continuous 0–100 score from four
inputs chosen to be separable:

| Input | Why it is independent |
|---|---|
| EMA separation in **ATR units** | Scale-free: comparable at gold $1,200 and $3,000 |
| RSI distance from 50 | Computed from RSI alone, not gated on the EMA state |
| Bollinger %B | Computed from the bands, not defined as an EMA conjunction |
| Volatility regime percentile | Damps confidence when volatility is extreme |

**This is a repair, not a hypothesis.** It removes a measurement artefact that
made every threshold meaningless. It does not supply a reason these inputs
should predict M5 gold returns, and the honest prior remains that they do not.

## The hypothesis, stated so it can be falsified

> Short-term gold returns exhibit weak momentum persistence when trend,
> momentum and volatility-envelope position **agree**, and that persistence is
> large enough to exceed round-trip costs **only** when the agreement is strong
> and the spread is narrow.

Two testable corollaries follow, and both are things the old system could not
express:

1. Expectancy should rise monotonically with the strength score. Under the old
   scorer this was untestable — there were four values and one real threshold.
2. Expectancy should be materially better in the London/NY overlap (~18 points
   of spread) than in the Asian session (~45). If it is not, the result is not
   a cost-sensitive edge and is more likely noise.

## What would falsify it

- Step 2 of the gauntlet: expectancy ≤ 0 after realistic costs.
- Flat or non-monotonic expectancy across strength deciles — the score carries
  no information.
- Profit concentrated in one session or one year (step 7) — a regime artefact.
- Sign flips under ±20% parameter changes (step 6) — a curve fit.

## Status (2026-09-13): FALSIFIED. Gate C fails with the rules the bot runs.

### What changed since the first run

The first Gate C run (below, kept for the record) passed steps 1-3 and failed
walk-forward. It measured **a system the bot does not run**:

| | First run's backtester | The live bot |
|---|---|---|
| Stop / target | fixed 2 x ATR, fixed 2.5 R | `dynamic_stop_loss` / `dynamic_rr_ratio` |
| Exits | SL/TP only | + opposite signal, trend reversal, structure break, volatility spike, 24 h age, weekend close, drawdown |
| Entry gates | strength only | + reversal hold, calendar, spread, daily loss, drawdown, loss streak, Friday cutoff |
| Signal volatility term | real ATR column | bar-range proxy (the ATR column was never added live) |
| Timestamps | broker server time treated as UTC | the same, which skewed sessions, costs and age |

All of that is now one implementation shared by `main.py` and
`backtest/live_engine.py` (see `docs/SECURITY-DECISIONS.md`).

### Result

Data: 99,699 usable M5 bars, 2025-04-08 to 2026-09-11 UTC (server times converted).
Costs: measured session spreads (8.4-12.2 points), real swap at the 17:00 New
York rollover with Wednesday charged x3, and gaps through stops filled at the
open. Commission $7/lot and slippage (mean 2, sd 3 points) are assumed.

**Step 1 (zero cost): PASS.** 2,052 trades, reconciles, +$0.37/trade.

**Step 2 (Gate C): FAIL.** Over 1,813 trades:

| Measure | Value |
|---|---|
| Net | -$413.01 on $1,000 (-41.3%) |
| Win rate | 31.0% (562 wins / 1,251 losses) |
| Profit factor | 0.95 |
| Expectancy | -$0.23/trade (-0.02 R), t = -0.89 |
| Average win / loss | $14.77 / -$6.97 |
| Maximum win / loss | $33.30 / -$72.60 (a gap through the stop) |
| Longest losing streak | 23 |
| Max drawdown | 50.8% |
| Costs | $902.88 against a -$111.08 result after spread and slippage |

Report files: `docs/reports/backtest-xauusd-m5-live-rules-no-halts.txt` and
`docs/reports/gauntlet-xauusd-m5-live-rules.txt`.

The gauntlet measures the rules with the account halts off. With them on
(`docs/reports/backtest-xauusd-m5-live-rules.txt`), the sticky 20% drawdown halt
tripped on 2025-08-08 after 460 trades, and the bot would have stood idle for
the remaining 13 months.

### Against the falsification criteria

* **Step 2 expectancy <= 0 after realistic costs: met.** The hypothesis is falsified
  for this configuration.
* The corollaries point the same way. The London/NY overlap, the tightest-spread
  session, is the **worst** (-$1.31/trade). The Asian session is the only
  positive one (+$0.66/trade over 725 trades). That is the opposite of a
  cost-sensitive momentum edge.
* Before costs the system makes +$0.37/trade. Costs average about $0.50/trade.
  The edge is smaller than the cost of trading it on M5.

### What this means

Per the plan: stop. No demo forward test (Gate D) and no live rollout. Both are
refused in code (`execution/rollout.py`). Legitimate next steps, none of them
automatic:

1. A higher timeframe (H1/H4), where a similar gross edge per trade would be
   large relative to a roughly $0.50 round-trip cost.
2. A different hypothesis. The Asian-session result is a lead to pre-register
   and test on new data, not a finding. It was found by looking.
3. Conclude there is no edge in this signal. That is a legitimate outcome.

Any new variant must be written down here **before** it is run, and all
variants tried must be reported. Trying configurations until one passes is how
backtests lie.

---

## H1 timeframe test (2026-09-14): FALSIFIED, more decisively than M5

Per the plan's own fallback ("a higher timeframe where the spread is a smaller
fraction of the expected move"), the same signal was re-run unmodified on H1
bars -- no code change beyond fetching H1 data and pointing the gauntlet at it
(`python scripts/run_gate_c.py --timeframe H1`). 17 years of real M5-broker
history were available at H1 (2009-09 to 2026-09), versus 1.43 years at M5.

**Diagnostic (halts disabled), full 17 years:**

| Measure | Value |
|---|---|
| Balance | $1,000.00 -> $323.86 (-67.6%) |
| Total trades | 1,373 |
| Wins / losses | 429 / 944 |
| Win rate | 31.25% |
| Profit factor | 0.84 |
| Expectancy | -$0.49/trade (-0.089 R), **t = -2.65** |
| Max drawdown | 73.2% |
| Every session negative | New York -$1.13, overlap -$0.59, London -$0.35, Asian -$0.08/trade |

The t-statistic is the important number: -2.65 is a materially stronger signal
that this is a real, non-random loss than the M5 result's -0.89. Costs were
130% of gross. No session was profitable, unlike M5 where Asian-session trades
were the one bright spot -- that lead does not survive a longer sample.

**Gate C (realistic-cost gauntlet): FAILED at step 2**, expectancy
-$0.4925/trade over 1,373 trades. Reports:
`docs/reports/backtest-xauusd-h1-live-rules-no-halts.txt`,
`docs/reports/gauntlet-xauusd-h1-live-rules.txt`.

This run was exploratory (`config.TIMEFRAME` is still M5) and was **not**
recorded as the project's Gate C -- see `docs/reports/gates.json`.

### Conclusion

The higher-timeframe fallback did not rescue the edge; it made the case
against it stronger. The EMA(12/26)/RSI(14)/Bollinger(20,2) state-follower
scored by `strategies/signal_strength.py` does not have a demonstrated edge
on gold at M5 or H1, over 1.4 or 17 years, with or without the discretionary
exits. Per the user's own instruction, the next step is a genuinely different
signal hypothesis (not a timeframe or parameter change), pre-registered here
before it is run.

---

## First run (2026-09-13, superseded): steps 1-3 passed, step 4 failed


Run 2026-09-13 against 99,999 real M5 XAUUSD bars fetched read-only from the
demo account (`5055880630`, MetaQuotes-Demo), 2025-04-07 → 2026-09-11 — **1.43
years**, short of the plan's 2+ year target because that is the full depth of
history this server retains (confirmed: paging past it returns "Terminal: Call
failed", not a fetch-size problem). Spread costs are the *measured* mean
per-session spread from the real data (8.6–10.7 broker points); swap is the
real `swap_long`/`swap_short` from the account's own symbol spec; commission and
slippage remain the module's documented, unverified retail assumptions — this
feed does not expose either. Reproducible via `scripts/fetch_historical_data.py`
then `scripts/run_gate_c.py`, both offline after the one read-only fetch.

**Step 1 (zero-cost sanity): PASS.** 1,870 trades, log reconciles.

**Step 2 (Gate C, realistic cost): PASS.** Expectancy **+$0.1988/trade** over
1,687 trades. Gross profit $595.37; total costs $712.99 (spread $303.75,
commission $215.46 unverified, swap $44.50, slippage $149.29 unverified) —
**costs were 120% of gross**, consistent with the structural argument above,
and net profit of $335.41 survived them anyway.

**Step 3 (out-of-sample, most recent 30%): PASS.** In-sample $0.1852,
out-of-sample $0.3535 — held up, did not decay.

**Step 4 (walk-forward, 4 rolling windows): FAIL.** Expectancy per window:
**+0.72, −0.28, +1.11, +0.23.** Three of four positive, but the plan's
criterion is *consistent sign across all windows*, and one failed it. Per the
plan's rule — stop at the first failure — **steps 5–7 were not run.**

The negative window does not correspond to the sample's calmest period; it is
the second quarter (2025-08-14 → 2025-12-19), which had the **strongest**
raw uptrend in the whole sample (close +28.9%, $3,357 → $4,327), while the
final, *losing*-trend quarter (2026-05-01 → 2026-09-11, close −6.1%) was
still net positive for the strategy. So the failure is not simply "this
system only wins when gold rallies" — something about that specific quarter's
internal volatility (likely sharp whipsaws inside the rally) punished the
EMA-state-follower logic specifically. That is exactly the kind of
regime-dependence walk-forward analysis exists to catch, and it caught it.

### What this does and does not mean

It does **not** mean "no edge, stop entirely" — step 2 passed with real,
measured costs, which the structural argument above predicted would fail. It
does **not** mean "there is a validated edge" either — the plan requires all
seven steps, and the strategy failed the fourth. The honest reading is: this
configuration shows a real but **inconsistent** edge over 1.43 years dominated
by an extraordinary gold bull market (close ranged $2,959 → $5,589 across the
sample) — not the more typical, mixed-regime data the gauntlet is designed to
stress-test against. A result built mostly on one secular trend is the
textbook setup for a walk-forward failure, and that is what happened.

**Per the plan's gate logic, this is a STOP: do not proceed to Phase 11 demo
forward testing with this configuration.** Legitimate next steps, in the
plan's own terms: gather more (and more regime-diverse) history once more
becomes available; try a different hypothesis for signal construction;
investigate what made the 2025-08–12 window fail as a diagnostic rather than
a strategy change; or move to a higher timeframe. This decision belongs to the
user, not to an automatic continuation into Phase 11.
