import streamlit as st
import pandas as pd

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

        # Detailed Performance Summary
        with st.expander("📊 Detailed Performance Summary", expanded=True):
            if stats and stats.get("total_trades", 0) > 0:
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### 📈 Trade Statistics")
                    st.metric("Total Trades", stats["total_trades"])
                    st.metric("Win Rate", f"{stats['win_rate']:.1f}%")
                    st.metric("Average Profit", f"${stats['avg_profit']:.2f}")
                    st.metric("Total P&L", f"${stats['total_pnl']:.2f}")

                with col2:
                    st.markdown("#### 🏅 Best/Worst Performance")
                    best_trade = stats.get("best_trade", 0)
                    worst_trade = stats.get("worst_trade", 0)

                    best_color = "normal" if best_trade > 0 else "off"
                    worst_color = "inverse" if worst_trade < 0 else "off"

                    st.metric("Best Trade", f"${best_trade:.2f}", delta=None, delta_color=best_color)
                    st.metric("Worst Trade", f"${worst_trade:.2f}", delta=None, delta_color=worst_color)

                    # Additional metrics
                    profitable_trades = int(stats["total_trades"] * stats["win_rate"] / 100)
                    losing_trades = stats["total_trades"] - profitable_trades
                    st.metric("Profitable Trades", profitable_trades)
                    st.metric("Losing Trades", losing_trades)
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

            # Filter out infinite and NaN values
            df_daily = df_daily.replace([float('inf'), float('-inf')], float('nan'))
            df_daily = df_daily.dropna(subset=['total_pnl'])

            if not df_daily.empty:
                # Enhanced chart with better styling
                st.line_chart(
                    df_daily.set_index('date')['total_pnl'],
                    height=300,
                    width='stretch'
                )
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
