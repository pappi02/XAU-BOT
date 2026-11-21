"""Performance from BROKER deals (read-only, Phase 12.1 / audit H-07).

The previous version read the local `trades` table for history and daily P&L.
That table's only writer recorded floating P&L before a close, and it never saw
a trade closed by a server-side stop -- so the win rate it produced was biased
upward by construction. Everything here comes from the broker's own deals.
"""

import pandas as pd
import streamlit as st


def render_tab(tab, data):
    with tab:
        stats = data.statistics()
        st.subheader("Performance")
        st.caption("Source: %s — every closing deal, including server-side "
                   "stop-outs." % stats.get("source", "broker_deals"))

        if not stats.get("total_trades"):
            st.info("No closed trades recorded yet.")
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Net P&L", "${:,.2f}".format(stats["total_pnl"]))
        c2.metric("Trades", stats["total_trades"])
        c3.metric("Win rate", "{:.1f}%".format(stats["win_rate"]))
        c4.metric("Expectancy / trade", "${:,.2f}".format(stats["avg_profit"]))

        d1, d2, d3 = st.columns(3)
        d1.metric("Best trade", "${:,.2f}".format(stats["best_trade"]))
        d2.metric("Worst trade", "${:,.2f}".format(stats["worst_trade"]))
        d3.metric("Commission + swap", "${:,.2f}".format(stats["total_costs"]))

        streak = data.loss_streak()
        if streak:
            st.warning("Current losing streak: %d trade(s). Entries halt at "
                       "the configured limit until acknowledged with "
                       "`python main.py --ack-loss-streak`." % streak)

        deals = data.deals(limit=5000)
        if deals.empty:
            return
        deals["deal_time"] = pd.to_datetime(deals["deal_time"], utc=True)
        deals = deals.sort_values("deal_time")
        deals["equity_change"] = deals["net_pnl"].cumsum()

        st.subheader("Cumulative realised P&L")
        st.line_chart(deals.set_index("deal_time")["equity_change"])

        st.subheader("Daily realised P&L")
        daily = deals.set_index("deal_time")["net_pnl"].resample("D").sum()
        st.bar_chart(daily[daily != 0])
