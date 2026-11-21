"""XAU/USD bot dashboard -- a READ-ONLY view of what main.py publishes.

Run with:  python run_bot.py      (or: python -m streamlit run dashboard.py)

Phase 12.1 (audit M-09) rewrote this file. What it no longer does, and why:

* **No MetaTrader5.** It shared a terminal connection with the trading thread
  and a Flask thread; the MT5 package permits one connection per process and is
  not documented as thread-safe. All data now comes from files main.py writes
  (see dashboard_data.py). A test asserts nothing here imports MT5.

* **No manual trading widgets.** Close-all, close-selected, partial close,
  move-to-break-even, apply-trailing and a manual order form were all inert
  since Phase 1.4 -- every one could only raise TradingDisabled. Buttons that
  cannot work teach an operator not to trust the buttons that can.

* **No fake kill switch.** The old "EMERGENCY KILL SWITCH" set a Streamlit
  session variable the bot never read, then displayed "All trading stopped!"
  while trading continued. The button below writes the STOP file the trading
  loop actually checks every bar.

* **No "Apply Strategy Settings".** It changed config inside this process, which
  the bot never sees. Settings live in config.py and take effect on restart.
"""

import streamlit as st

import config
import dashboard_data as data
from strategies.strategy_basic import BasicTradingStrategy
from tabs.charts_tab import render_tab as render_charts
from tabs.live_trading_tab import render_tab as render_live
from tabs.news_tab import render_tab as render_news
from tabs.performance_tab import render_tab as render_performance
from tabs.signals_tab import render_tab as render_signals
from tabs.sl_management_tab import render_tab as render_controls
from tabs.trade_history_tab import render_tab as render_history
from utils.news_reader import get_latest_forex_news


def strategy_factory():
    """The same strategy, with the same configured periods, as main.py."""
    return BasicTradingStrategy(ema_fast=config.EMA_FAST,
                                ema_slow=config.EMA_SLOW,
                                rsi_period=config.RSI_PERIOD,
                                bb_period=config.BB_PERIOD,
                                bb_std=config.BB_STD_DEV)


st.set_page_config(page_title="XAU/USD Bot", page_icon="💰", layout="wide")
st.title("XAU/USD Trading Bot")
st.caption("Read-only view. The trading loop (main.py) is the only process "
           "that talks to the broker; this page reads what it publishes.")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Status")
    fresh = data.freshness()
    if fresh["never_ran"]:
        st.warning("Bot has not published any state yet.")
    elif fresh["stale"]:
        st.error("STALE — no update for %.0f min." % (fresh["age_seconds"] / 60))
    else:
        st.success("Live — updated %.0f s ago." % fresh["age_seconds"])

    controls = data.controls()
    st.header("Kill switch")
    st.caption("Stops NEW entries on the next bar. Open positions keep their "
               "server-side stops. To close everything: "
               "`python main.py --flatten`.")
    if controls["kill_switch_file"]:
        st.error("ENGAGED — no new positions will open.")
        if st.button("Release kill switch", use_container_width=True):
            data.release_kill_switch()
            st.rerun()
    else:
        if st.button("Engage kill switch", type="primary",
                     use_container_width=True):
            data.engage_kill_switch("engaged from dashboard")
            st.rerun()

    if controls["halted_reason"]:
        st.error("Halted: %s" % controls["halted_reason"])

    if st.button("Refresh", use_container_width=True):
        st.rerun()

# --------------------------------------------------------------------- tabs
tabs = st.tabs(["Live", "Performance", "Trade history", "Chart",
                "Decisions", "News", "Controls"])

render_live(tabs[0], data)
render_performance(tabs[1], data)
render_history(tabs[2], data)
render_charts(tabs[3], data, config, strategy_factory)
render_signals(tabs[4], data, config, strategy_factory)
render_news(tabs[5], get_latest_forex_news)
render_controls(tabs[6], data, config)
