"""Live status: account, open positions, last tick (read-only, Phase 12.1).

Reads the snapshot main.py publishes. The previous version called MetaTrader5
directly from the Streamlit process and embedded an order-entry form whose
submit button could only ever raise TradingDisabled.
"""

import streamlit as st


def _money(value):
    return "—" if value is None else "${:,.2f}".format(float(value))


def render_tab(tab, data):
    with tab:
        report = data.health()
        fresh = data.freshness(report)

        if fresh["never_ran"]:
            st.warning("No state published yet. Start the bot with "
                       "`python main.py`; this page reads what it writes.")
            return

        age = fresh["age_seconds"] or 0
        if fresh["stale"]:
            st.error("State is STALE — last update %.0f minutes ago. The bot "
                     "may have stopped. Values below are history, not the "
                     "present." % (age / 60))
        else:
            st.caption("Last update %.0f s ago (%s)"
                       % (age, fresh["last_loop_time"]))

        acct = data.account(report)
        st.subheader("Account")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Balance", _money(acct.get("balance")))
        c2.metric("Equity", _money(acct.get("equity")))
        c3.metric("Free margin", _money(acct.get("free_margin")))
        level = acct.get("margin_level")
        c4.metric("Margin level", "—" if not level else "{:,.0f}%".format(level))
        mode = acct.get("trade_mode")
        st.caption("Account %s on %s — %s"
                   % (acct.get("login", "?"), acct.get("server", "?"),
                      "DEMO" if mode == 0 else ("LIVE" if mode is not None else "?")))

        tick = data.tick(report)
        st.subheader("Market")
        if tick:
            m1, m2, m3 = st.columns(3)
            m1.metric("Bid", "{:,.2f}".format(tick["bid"]))
            m2.metric("Ask", "{:,.2f}".format(tick["ask"]))
            m3.metric("Spread", "{:.1f} points".format(tick["spread_points"]))
        else:
            st.info("No tick published yet.")

        st.subheader("Open positions")
        frame = data.positions(report)
        if frame.empty:
            st.info("No open positions.")
        else:
            columns = [c for c in ("ticket", "side", "volume", "price_open",
                                   "price_current", "sl", "tp", "profit")
                       if c in frame.columns]
            st.dataframe(frame[columns], use_container_width=True,
                         hide_index=True)
            if "profit" in frame.columns:
                st.metric("Floating P&L", _money(frame["profit"].sum()))
