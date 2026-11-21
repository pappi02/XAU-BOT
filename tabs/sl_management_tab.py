"""Risk controls and stops (read-only, Phase 12.1).

The previous version offered break-even, trailing and partial-close buttons that
could only raise TradingDisabled, and read prices from MT5 directly. This shows
the state of every control the bot actually enforces, and the stop on each
open position.
"""

import streamlit as st


def render_tab(tab, data, config):
    with tab:
        report = data.health()
        controls = data.controls(report)

        st.subheader("Controls")
        breaker = controls["circuit_breaker"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Kill switch (STOP file)",
                  "ENGAGED" if controls["kill_switch_file"] else "off")
        c2.metric("Circuit breaker",
                  "TRIPPED" if breaker.get("tripped") else
                  "%s/%s failures" % (breaker.get("consecutive_failures", 0),
                                      breaker.get("threshold", "?")))
        c3.metric("Losing streak", data.loss_streak())
        if controls["halted_reason"]:
            st.error("Halted: %s" % controls["halted_reason"])

        st.subheader("Stop management")
        st.write("Trailing stop: **%s** · Break-even: **%s**"
                 % ("on" if config.TRAILING_STOP_ENABLED else "off",
                    "on" if config.BREAK_EVEN_ENABLED else "off"))
        if not (config.TRAILING_STOP_ENABLED or config.BREAK_EVEN_ENABLED):
            st.caption("No stop is modified in flight: each position keeps "
                       "the SL/TP sent at entry, held server-side.")

        st.subheader("Stops on open positions")
        frame = data.positions(report)
        if frame.empty:
            st.info("No open positions.")
            return

        def risk_row(row):
            if not row.get("sl"):
                return "NO STOP"
            distance = abs(float(row["price_open"]) - float(row["sl"]))
            return "{:.2f} price units".format(distance)

        frame = frame.copy()
        frame["stop_distance"] = frame.apply(risk_row, axis=1)
        columns = [c for c in ("ticket", "side", "volume", "price_open", "sl",
                               "tp", "stop_distance") if c in frame.columns]
        st.dataframe(frame[columns], use_container_width=True, hide_index=True)
