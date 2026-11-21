"""Trade history from BROKER deals (read-only, Phase 12.1 / audit H-07)."""

import streamlit as st


def render_tab(tab, data):
    with tab:
        st.subheader("Closed trades")
        st.caption("One row per closed position, newest first, built from broker "
                   "deals. net_pnl = profit + commission + swap over the open and "
                   "close deals — what actually moved the balance.")
        frame = data.closed_trades(limit=500)
        if frame.empty:
            st.info("No closed trades recorded yet.")
            return

        def colour(value):
            if value > 0:
                return "color: green"
            if value < 0:
                return "color: red"
            return ""

        styled = frame.style.map(colour, subset=["net_pnl"])
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     height=500)
