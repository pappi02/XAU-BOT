import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render_tab(tab, trade_logger):
    with tab:
        st.subheader("📜 Recent Trade History")

        if trade_logger:
            # Add filter for number of trades to display
            num_trades_options = ['All', '100', '500', '1000', '2000']
            selected_num_trades = st.selectbox("Number of Trades to Display", num_trades_options, index=0)

            limit = None if selected_num_trades == 'All' else int(selected_num_trades)
            trade_history = trade_logger.get_trade_history(limit)
            if trade_history:
                df_trades = pd.DataFrame(trade_history)
                df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
                df_trades = df_trades.sort_values('timestamp', ascending=False)

                # Filters
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    # Date range filter
                    start_date = st.date_input("Start Date", value=df_trades['timestamp'].min().date() if not df_trades.empty else datetime.now().date() - timedelta(days=30))
                    end_date = st.date_input("End Date", value=datetime.now().date())

                with col2:
                    # Side filter
                    sides = ['All'] + sorted(df_trades['side'].unique().tolist())
                    selected_side = st.selectbox("Side", sides)

                with col3:
                    # Profit/Loss filter
                    pnl_options = ['All', 'Profit', 'Loss']
                    selected_pnl = st.selectbox("Profit/Loss", pnl_options)

                with col4:
                    # Time period filter
                    time_periods = ['All', 'Today', 'Last 7 Days', 'Last 30 Days', 'Last 90 Days']
                    selected_period = st.selectbox("Time Period", time_periods)

                # Apply filters
                filtered_df = df_trades.copy()

                # Date range
                filtered_df = filtered_df[(filtered_df['timestamp'].dt.date >= start_date) & (filtered_df['timestamp'].dt.date <= end_date)]

                # Side
                if selected_side != 'All':
                    filtered_df = filtered_df[filtered_df['side'] == selected_side]

                # Profit/Loss
                if selected_pnl == 'Profit':
                    filtered_df = filtered_df[filtered_df['pnl'] > 0]
                elif selected_pnl == 'Loss':
                    filtered_df = filtered_df[filtered_df['pnl'] < 0]

                # Time period (overrides date range if selected)
                now = datetime.now()
                if selected_period == 'Today':
                    filtered_df = filtered_df[filtered_df['timestamp'].dt.date == now.date()]
                elif selected_period == 'Last 7 Days':
                    filtered_df = filtered_df[filtered_df['timestamp'] >= now - timedelta(days=7)]
                elif selected_period == 'Last 30 Days':
                    filtered_df = filtered_df[filtered_df['timestamp'] >= now - timedelta(days=30)]
                elif selected_period == 'Last 90 Days':
                    filtered_df = filtered_df[filtered_df['timestamp'] >= now - timedelta(days=90)]

                # Color coding for P&L
                def color_pnl(val):
                    if val is None:
                        color = 'gray'
                    else:
                        color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
                    return f'color: {color}'

                # Display filtered results
                if not filtered_df.empty:
                    st.write(f"Showing {len(filtered_df)} trades")
                    # Use Styler.map (applymap is deprecated)
                    styled_df = filtered_df[['timestamp', 'symbol', 'side', 'entry_price', 'exit_price', 'volume', 'pnl', 'status']].style
                    styled_df = styled_df.map(lambda v: color_pnl(v), subset=['pnl'])
                    st.dataframe(styled_df, width='stretch', height=400)
                else:
                    st.info("No trades match the selected filters.")
            else:
                st.info("No trade records available yet.")
        else:
            st.info("Trade logger not available.")
