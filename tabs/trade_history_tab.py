import streamlit as st
import pandas as pd

def render_tab(tab, trade_logger):
    with tab:
        st.subheader("📜 Recent Trade History")
        if trade_logger:
            trade_history = trade_logger.get_trade_history(100)
            if trade_history:
                df_trades = pd.DataFrame(trade_history)
                df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
                df_trades = df_trades.sort_values('timestamp', ascending=False)

                # Color coding for P&L
                def color_pnl(val):
                    color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
                    return f'color: {color}'

                # Use Styler.map (applymap is deprecated)
                styled_df = df_trades[['timestamp', 'symbol', 'side', 'entry_price', 'exit_price', 'volume', 'pnl', 'status']].style
                styled_df = styled_df.map(lambda v: color_pnl(v), subset=['pnl'])
                st.dataframe(styled_df, width='stretch', height=400)
            else:
                st.info("No trade records available yet.")
        else:
            st.info("Trade logger not available.")
