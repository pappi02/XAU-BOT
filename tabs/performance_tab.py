import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

def render_tab(tab, trade_logger):
    with tab:
        perf_css = """
        <style>
        .perf-card {
            background: linear-gradient(135deg, #1e1e1e, #2d2d2d) !important;
            border: 1px solid #4a4a4a !important;
            border-radius: 12px !important;
            padding: 15px !important;
            margin: 5px 0 !important;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
        }
        .perf-metric {
            text-align: center !important;
            font-size: 18px !important;
            font-weight: bold !important;
        }
        .perf-label {
            color: #cccccc !important;
            font-size: 14px !important;
            margin-bottom: 5px !important;
        }
        .perf-value {
            color: #ffffff !important;
            font-size: 24px !important;
            font-weight: bold !important;
        }
        .positive { color: #00ff00 !important; }
        .negative { color: #ff4444 !important; }
        .neutral { color: #ffffff !important; }
        .chart-container {
            background: linear-gradient(135deg, #1e1e1e, #2d2d2d) !important;
            border-radius: 12px !important;
            padding: 15px !important;
            margin: 10px 0 !important;
            border: 1px solid #4a4a4a !important;
        }
        </style>
        """
        st.markdown(perf_css, unsafe_allow_html=True)

        st.subheader("📈 Performance Overview")

        # Get comprehensive statistics
        stats = trade_logger.compute_statistics()
        total_pnl = trade_logger.get_total_pnl()
        trade_history = trade_logger.get_trade_history(100)
        daily_pnl = trade_logger.get_daily_pnl(14)

        # Key Performance Indicators
        st.markdown("### 🎯 Key Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            pnl_color = "positive" if total_pnl > 0 else "negative" if total_pnl < 0 else "neutral"
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">💵 Total P&L</div>
                <div class="perf-value {pnl_color}">${total_pnl:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            total_trades = stats.get("total_trades", 0)
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">📊 Total Trades</div>
                <div class="perf-value neutral">{total_trades}</div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            win_rate = stats.get("win_rate", 0)
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">🏆 Win Rate</div>
                <div class="perf-value positive">{win_rate:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            avg_profit = stats.get("avg_profit", 0)
            avg_color = "positive" if avg_profit > 0 else "negative" if avg_profit < 0 else "neutral"
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">📈 Avg Profit</div>
                <div class="perf-value {avg_color}">${avg_profit:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        # Additional Key Metrics
        col5, col6, col7, col8 = st.columns(4)

        with col5:
            profit_factor = stats.get("profit_factor", 0)
            pf_color = "positive" if profit_factor > 1 else "negative" if profit_factor < 1 else "neutral"
            pf_display = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">📊 Profit Factor</div>
                <div class="perf-value {pf_color}">{pf_display}</div>
            </div>
            """, unsafe_allow_html=True)

        with col6:
            avg_win = stats.get("avg_win", 0)
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">💰 Avg Win</div>
                <div class="perf-value positive">${avg_win:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with col7:
            avg_loss = stats.get("avg_loss", 0)
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">💸 Avg Loss</div>
                <div class="perf-value negative">${avg_loss:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with col8:
            total_win_pnl = stats.get("total_win_pnl", 0)
            st.markdown(f"""
            <div class="perf-card">
                <div class="perf-label">📈 Total Win P&L</div>
                <div class="perf-value positive">${total_win_pnl:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        # Detailed Performance Summary
        with st.expander("📊 Detailed Performance Summary", expanded=True):
            if stats and stats.get("total_trades", 0) > 0:
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### 🏆 Best Trade Details")
                    best_trade_details = trade_logger.get_best_trade_details()
                    if best_trade_details:
                        st.metric("Trade ID", best_trade_details["id"])
                        st.metric("Symbol", best_trade_details["symbol"])
                        st.metric("Side", best_trade_details["side"])
                        st.metric("Entry Price", f"${best_trade_details['entry_price']:.5f}")
                        st.metric("Exit Price", f"${best_trade_details['exit_price']:.5f}" if best_trade_details['exit_price'] else "N/A")
                        pnl_color = "normal" if best_trade_details["pnl"] > 0 else "inverse"
                        st.metric("P&L", f"${best_trade_details['pnl']:.2f}", delta_color=pnl_color)
                        st.metric("Volume", f"{best_trade_details['volume']:.2f}")
                        st.metric("Timestamp", best_trade_details["timestamp"][:19])  # Format timestamp
                    else:
                        st.info("No best trade data available.")

                with col2:
                    st.markdown("#### 💸 Worst Trade Details")
                    worst_trade_details = trade_logger.get_worst_trade_details()
                    if worst_trade_details:
                        st.metric("Trade ID", worst_trade_details["id"])
                        st.metric("Symbol", worst_trade_details["symbol"])
                        st.metric("Side", worst_trade_details["side"])
                        st.metric("Entry Price", f"${worst_trade_details['entry_price']:.5f}")
                        st.metric("Exit Price", f"${worst_trade_details['exit_price']:.5f}" if worst_trade_details['exit_price'] else "N/A")
                        pnl_color = "normal" if worst_trade_details["pnl"] > 0 else "inverse"
                        st.metric("P&L", f"${worst_trade_details['pnl']:.2f}", delta_color=pnl_color)
                        st.metric("Volume", f"{worst_trade_details['volume']:.2f}")
                        st.metric("Timestamp", worst_trade_details["timestamp"][:19])  # Format timestamp
                    else:
                        st.info("No worst trade data available.")
            else:
                st.info("No trades recorded yet. Start trading to see performance metrics!")

        # Daily P&L Chart
        if daily_pnl:
            st.markdown("### 📅 Daily P&L Trend")
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            df_daily = pd.DataFrame(daily_pnl)
            df_daily['date'] = pd.to_datetime(df_daily['date'], errors='coerce')
            df_daily = df_daily.dropna(subset=['date'])
            df_daily = df_daily.sort_values('date')

            # Filter out infinite and NaN values comprehensively
            df_daily = df_daily.replace([np.inf, -np.inf, float('inf'), float('-inf')], np.nan)
            df_daily = df_daily.dropna(subset=['date', 'total_pnl'])

            # Additional validation: ensure total_pnl is finite and not NaN
            df_daily = df_daily[np.isfinite(df_daily['total_pnl'])]

            if not df_daily.empty:
                # Check for valid data before rendering chart
                if df_daily is not None and not df_daily.empty and pd.notna(df_daily['date']).any() and pd.notna(df_daily['total_pnl']).any():
                    # Use Altair for better chart control and to avoid Vega-Lite version issues
                    chart = alt.Chart(df_daily).mark_line(point=True).encode(
                        x=alt.X('date:T', title='Date'),
                        y=alt.Y('total_pnl:Q', title='Total P&L'),
                        tooltip=['date:T', 'total_pnl:Q']
                    ).properties(
                        height=300,
                        title='Daily P&L Trend'
                    ).configure_axis(
                        labelColor='white',
                        titleColor='white'
                    ).configure_title(
                        color='white'
                    ).configure_view(
                        strokeWidth=0
                    )

                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.warning("No valid data for chart (check trade logs).")
            else:
                st.info("No valid daily P&L data to display.")
            st.markdown('</div>', unsafe_allow_html=True)

            # Daily P&L Summary
            total_daily_pnl = df_daily['total_pnl'].sum()
            avg_daily_pnl = df_daily['total_pnl'].mean()
            best_day = df_daily['total_pnl'].max()
            worst_day = df_daily['total_pnl'].min()

            st.markdown("#### 📊 Daily P&L Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Daily P&L", f"${total_daily_pnl:.2f}")
            with col2:
                st.metric("Avg Daily P&L", f"${avg_daily_pnl:.2f}")
            with col3:
                st.metric("Best Day", f"${best_day:.2f}")
            with col4:
                st.metric("Worst Day", f"${worst_day:.2f}")
        else:
            st.info("No daily P&L data available yet.")
