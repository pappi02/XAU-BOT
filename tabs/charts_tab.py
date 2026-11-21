"""Price chart from the published candle cache (read-only, Phase 12.1).

The previous version called get_candles(), which calls mt5.initialize() itself
-- a hidden MT5 client inside the Streamlit process. The bars now come from the
file the trading loop writes each bar, so the chart shows exactly the closed
bars the bot decided on.
"""

import plotly.graph_objects as go
import streamlit as st


def render_tab(tab, data, config, strategy_factory):
    with tab:
        st.subheader("%s %s — closed bars" % (config.SYMBOL, config.TIMEFRAME))
        bars = data.candles()
        if bars.empty:
            st.info("No candles published yet. The bot writes them each bar "
                    "once it is running.")
            return

        prepared = strategy_factory().prepare_data(bars)
        figure = go.Figure()
        figure.add_trace(go.Candlestick(
            x=prepared.index, open=prepared["open"], high=prepared["high"],
            low=prepared["low"], close=prepared["close"], name="Price"))

        overlays = [("EMA_%d" % config.EMA_FAST, "EMA fast"),
                    ("EMA_%d" % config.EMA_SLOW, "EMA slow"),
                    ("BB_upper_%d" % config.BB_PERIOD, "BB upper"),
                    ("BB_lower_%d" % config.BB_PERIOD, "BB lower")]
        for column, label in overlays:
            if column in prepared.columns:
                figure.add_trace(go.Scatter(x=prepared.index, y=prepared[column],
                                            mode="lines", name=label))

        figure.update_layout(height=600, xaxis_rangeslider_visible=False)
        st.plotly_chart(figure, use_container_width=True)
