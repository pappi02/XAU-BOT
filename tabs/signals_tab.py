"""The bot's actual decisions, and why (read-only, Phase 12.1).

The authoritative view is the decision log: what the bot really decided on each
bar and which gate, if any, blocked the entry. The component breakdown below is
recomputed from the same published closed bars with the same strategy code, to
explain the most recent score -- it is an explanation, never a second opinion.
"""

import streamlit as st

from utils.indicators import atr


def render_tab(tab, data, config, strategy_factory):
    with tab:
        st.subheader("Recent decisions")
        decisions = data.decisions(limit=200)
        if decisions.empty:
            st.info("No decisions recorded yet.")
        else:
            columns = [c for c in ("ts", "bar", "signal", "strength",
                                   "spread_points", "session", "entry_blocked",
                                   "action") if c in decisions.columns]
            st.dataframe(decisions[columns], use_container_width=True,
                         hide_index=True, height=350)

            if "entry_blocked" in decisions.columns:
                blocked = decisions["entry_blocked"].dropna()
                if not blocked.empty:
                    st.caption("Why entries were blocked (last 200 bars)")
                    reasons = blocked.str.split(":").str[0].value_counts()
                    st.bar_chart(reasons)

        st.subheader("Latest score, explained")
        bars = data.candles()
        if bars.empty:
            st.info("No candles published yet.")
            return

        strategy = strategy_factory()
        prepared = strategy.prepare_data(bars)
        prepared["ATR"] = atr(prepared, period=config.ATR_PERIOD)
        result = strategy.generate_signal(prepared)

        c1, c2 = st.columns(2)
        c1.metric("Signal", result.get("signal", "?"))
        c2.metric("Strength", "{:.1f}".format(float(result.get("strength", 0))))
        st.caption("Entries require strength >= %.0f." % config.MIN_ENTRY_STRENGTH)
        st.json(result.get("components", {}))
