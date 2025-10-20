import streamlit as st
import pandas as pd
from datetime import datetime
import MetaTrader5 as mt5
import requests

def render_tab(tab, config, mt5, get_open_positions):
    with tab:
        st.subheader("📈 Live Trading Dashboard")

        # Live Trading CSS
        live_css = """
        <style>
        .live-card {
            background: linear-gradient(135deg, #1e1e1e, #2d2d2d) !important;
            border: 1px solid #4a4a4a !important;
            border-radius: 12px !important;
            padding: 20px !important;
            margin: 10px 0 !important;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
        }
        .position-card {
            background: linear-gradient(135deg, #232a3d, #1a1f2b) !important;
            border: 2px solid #4a90e2 !important;
            border-radius: 16px !important;
            padding: 24px !important;
            margin: 16px 0 !important;
            box-shadow: 0 6px 20px rgba(0,0,0,0.4) !important;
            position: relative !important;
            overflow: hidden !important;
        }
        .position-card::before {
            content: '' !important;
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            height: 4px !important;
            background: linear-gradient(90deg, #00ff88, #4a90e2) !important;
        }
        .position-header {
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            margin-bottom: 20px !important;
        }
        .position-title {
            font-size: 24px !important;
            font-weight: 700 !important;
            color: #ffffff !important;
            margin: 0 !important;
        }
        .position-status {
            display: inline-block !important;
            padding: 6px 16px !important;
            border-radius: 20px !important;
            font-size: 14px !important;
            font-weight: bold !important;
            text-transform: uppercase !important;
        }
        .status-profit { background: #00ff88; color: #000; }
        .status-loss { background: #ff4444; color: #fff; }
        .status-neutral { background: #ffa500; color: #000; }
        .trade-btn {
            background: linear-gradient(135deg, #00ff88, #00cc66) !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 12px 24px !important;
            color: #000 !important;
            font-weight: bold !important;
            font-size: 16px !important;
            cursor: pointer !important;
            transition: all 0.3s !important;
            margin: 8px !important;
        }
        .trade-btn:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(0,255,136,0.3) !important;
        }
        .sell-btn {
            background: linear-gradient(135deg, #ff4444, #cc0000) !important;
        }
        .sell-btn:hover {
            box-shadow: 0 4px 12px rgba(255,68,68,0.3) !important;
        }
        .metric-grid {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)) !important;
            gap: 16px !important;
            margin: 20px 0 !important;
        }
        .metric-item {
            background: #333 !important;
            border-radius: 8px !important;
            padding: 12px !important;
            text-align: center !important;
            border: 1px solid #555 !important;
        }
        .metric-label {
            color: #cccccc !important;
            font-size: 12px !important;
            margin-bottom: 4px !important;
            text-transform: uppercase !important;
        }
        .metric-value {
            color: #ffffff !important;
            font-size: 18px !important;
            font-weight: bold !important;
        }
        .metric-value.positive { color: #00ff88 !important; }
        .metric-value.negative { color: #ff4444 !important; }
        .quick-trade-section {
            background: linear-gradient(135deg, #2d2d2d, #1e1e1e) !important;
            border-radius: 12px !important;
            padding: 24px !important;
            margin: 20px 0 !important;
            border: 2px solid #4a90e2 !important;
        }
        .quick-trade-title {
            font-size: 20px !important;
            font-weight: 700 !important;
            color: #4a90e2 !important;
            margin-bottom: 16px !important;
        }
        .trade-form {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 16px !important;
        }
        .form-group {
            margin-bottom: 16px !important;
        }
        .form-label {
            color: #cccccc !important;
            font-size: 14px !important;
            margin-bottom: 8px !important;
            display: block !important;
        }
        .form-input {
            width: 100% !important;
            padding: 12px !important;
            border-radius: 8px !important;
            border: 1px solid #555 !important;
            background: #222 !important;
            color: #fff !important;
            font-size: 16px !important;
        }
        .submit-btn {
            background: linear-gradient(135deg, #4a90e2, #357abd) !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 12px 24px !important;
            color: white !important;
            font-weight: bold !important;
            cursor: pointer !important;
            transition: all 0.3s !important;
            width: 100% !important;
        }
        .submit-btn:hover {
            background: linear-gradient(135deg, #357abd, #2c5aa0) !important;
            transform: translateY(-2px) !important;
        }
        </style>
        """
        st.markdown(live_css, unsafe_allow_html=True)

        if st.session_state.get('mt5_initialized', False):
            # Live Market Data
            st.markdown("### 📊 Live Market Data")
            try:
                response = requests.get("http://127.0.0.1:5001/market_data", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Bid", f"${data['bid']:.5f}")
                    with col2:
                        st.metric("Ask", f"${data['ask']:.5f}")
                    with col3:
                        st.metric("Spread", f"{data['spread']:.1f} pips")
                    with col4:
                        st.metric("Volume", f"{data['volume']}")
                    with col5:
                        st.metric("Last Update", datetime.fromtimestamp(data['time']).strftime("%H:%M:%S"))
                else:
                    st.warning("Unable to fetch live market data")
            except requests.exceptions.RequestException:
                st.error("❌ Cannot connect to Flask API for market data")
            except Exception as e:
                st.error(f"Error fetching market data: {str(e)}")

            # Open Positions
            positions = get_open_positions(config.SYMBOL)
            if positions:
                st.markdown("### 📋 Open Positions")

                # Summary metrics
                total_positions = len(positions)
                total_profit = sum(pos.profit for pos in positions)
                buy_positions = len([p for p in positions if p.type == mt5.POSITION_TYPE_BUY])
                sell_positions = len([p for p in positions if p.type == mt5.POSITION_TYPE_SELL])

                col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
                with col_sum1:
                    st.metric("Total Positions", total_positions)
                with col_sum2:
                    profit_color = "normal" if total_profit > 0 else "inverse" if total_profit < 0 else "off"
                    st.metric("Total P&L", f"${total_profit:.2f}", delta_color=profit_color)
                with col_sum3:
                    st.metric("Buy Positions", buy_positions)
                with col_sum4:
                    st.metric("Sell Positions", sell_positions)

                # Individual position cards
                for pos in positions:
                    is_buy = pos.type == mt5.POSITION_TYPE_BUY
                    symbol_info = mt5.symbol_info(config.SYMBOL)
                    if symbol_info:
                        current_price = symbol_info.bid if is_buy else symbol_info.ask
                    else:
                        current_price = pos.price_open  # fallback
                    pip_distance = abs(current_price - pos.price_open) * 10000
                    duration_hours = (datetime.utcnow() - datetime.utcfromtimestamp(pos.time)).total_seconds() / 3600

                    # Determine status
                    status_class = "status-profit" if pos.profit > 0 else "status-loss" if pos.profit < 0 else "status-neutral"

                    # Position header
                    st.markdown(f"### {'🟢 BUY' if is_buy else '🔴 SELL'} #{pos.ticket} - {pos.symbol}")
                    st.markdown(f"**P&L:** ${pos.profit:.2f}")

                    # Position details in columns
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Volume", f"{pos.volume} lots")
                        st.metric("Entry Price", f"${pos.price_open:.5f}")
                    with col2:
                        st.metric("Current Price", f"${current_price:.5f}")
                        st.metric("Distance", f"{pip_distance:.1f} pips")
                    with col3:
                        st.metric("Duration", f"{duration_hours:.1f}h")
                        st.metric("Stop Loss", f"${pos.sl:.5f}" if pos.sl > 0 else "None")
                    with col4:
                        st.metric("Take Profit", f"${pos.tp:.5f}" if pos.tp > 0 else "None")
                        st.metric("Swap", f"${pos.swap:.2f}")

                    # Action buttons
                    col_btn1, col_btn2, col_btn3 = st.columns([1,1,2])
                    with col_btn1:
                        if st.button("🔴 Close", key=f"close_{pos.ticket}"):
                            st.info("Close position functionality not yet implemented")
                    with col_btn2:
                        if st.button("⚙️ Modify", key=f"modify_{pos.ticket}"):
                            st.info("Modify SL/TP functionality not yet implemented")
                    with col_btn3:
                        st.empty()

                    st.markdown("---")
            else:
                st.info("📭 No open positions")

            # Quick Trade Section
            st.markdown("### 🚀 Quick Trade Entry")
            with st.expander("💹 Enter New Trade", expanded=False):
                st.markdown('<div class="quick-trade-section">', unsafe_allow_html=True)
                st.markdown('<div class="quick-trade-title">⚡ Quick Trade Setup</div>', unsafe_allow_html=True)

                with st.form("live_trading_quick_trade_form"):
                    col1, col2 = st.columns(2)

                    with col1:
                        direction = st.selectbox("Direction", ["BUY", "SELL"], help="Trade direction", key="live_trading_direction")
                        volume = st.number_input("Volume (lots)", min_value=0.01, max_value=10.0, value=0.1, step=0.01, help="Position size in lots")
                        sl_pips = st.number_input("Stop Loss (pips)", min_value=0, max_value=1000, value=50, help="Stop loss distance in pips")

                    with col2:
                        entry_type = st.selectbox("Entry Type", ["Market", "Limit", "Stop"], help="Order entry type", key="live_trading_entry_type")
                        if entry_type != "Market":
                            entry_price = st.number_input("Entry Price", min_value=0.0, value=0.0, step=0.01, help="Limit/Stop entry price")
                        else:
                            entry_price = 0.0
                        tp_pips = st.number_input("Take Profit (pips)", min_value=0, max_value=1000, value=100, help="Take profit distance in pips")

                    # Calculate prices
                    if direction == "BUY":
                        current_price = mt5.symbol_info(config.SYMBOL).ask if mt5.symbol_info(config.SYMBOL) else 0
                        sl_price = current_price - (sl_pips / 10000) if sl_pips > 0 else 0
                        tp_price = current_price + (tp_pips / 10000) if tp_pips > 0 else 0
                    else:
                        current_price = mt5.symbol_info(config.SYMBOL).bid if mt5.symbol_info(config.SYMBOL) else 0
                        sl_price = current_price + (sl_pips / 10000) if sl_pips > 0 else 0
                        tp_price = current_price - (tp_pips / 10000) if tp_pips > 0 else 0

                    st.markdown("#### 📊 Trade Preview")
                    col_prev1, col_prev2, col_prev3 = st.columns(3)
                    with col_prev1:
                        st.metric("Entry", f"${current_price:.5f}")
                    with col_prev2:
                        st.metric("Stop Loss", f"${sl_price:.5f}" if sl_price > 0 else "None")
                    with col_prev3:
                        st.metric("Take Profit", f"${tp_price:.5f}" if tp_price > 0 else "None")

                    risk_amount = (abs(current_price - sl_price) * volume * 100000) if sl_price > 0 else 0
                    st.metric("Risk Amount", f"${risk_amount:.2f}" if risk_amount > 0 else "Unlimited")

                    if st.form_submit_button("🚀 Execute Trade", width='stretch'):
                        try:
                            from execution.trade_executor import TradeExecutor
                            from risk.risk_manager import RiskManager

                            risk_mgr = RiskManager(mt5, config)
                            executor = TradeExecutor(mt5, config, risk_mgr)

                            if entry_type == "Market":
                                result = executor.enter_trade(config.SYMBOL, direction, current_price, sl_price if sl_price > 0 else None, tp_price if tp_price > 0 else None, volume)
                            else:
                                # For limit/stop orders, we'd need additional implementation
                                st.error("Limit and Stop orders not yet implemented")
                                result = None

                            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                st.success(f"✅ {direction} order placed successfully - Ticket: {result.order}")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to place {direction} order")
                        except Exception as e:
                            st.error(f"❌ Trade execution failed: {str(e)}")

                st.markdown('</div>', unsafe_allow_html=True)

            # Trading Statistics
            st.markdown("### 📈 Trading Statistics")
            try:
                response = requests.get("http://127.0.0.1:5001/status", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("connected"):
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                        with col_stat1:
                            st.metric("Account Balance", f"${data['balance']:.2f}")
                        with col_stat2:
                            st.metric("Equity", f"${data['equity']:.2f}")
                        with col_stat3:
                            margin_level = (data['equity'] / (data['equity'] - data['free_margin'])) * 100 if (data['equity'] - data['free_margin']) > 0 else 0
                            st.metric("Margin Level", f"{margin_level:.1f}%")
                        with col_stat4:
                            st.metric("Free Margin", f"${data['free_margin']:.2f}")
                    else:
                        st.warning("MT5 not connected - unable to fetch account statistics")
                else:
                    st.warning("Unable to fetch account statistics from API")
            except requests.exceptions.RequestException:
                st.error("❌ Cannot connect to Flask API for account statistics")
            except Exception as e:
                st.error(f"Error fetching trading statistics: {str(e)}")

        else:
            st.warning("❌ MT5 not connected - Live trading unavailable")
            st.markdown("""
            ### 🚀 Getting Started with Live Trading

            To enable live trading features:

            1. **Connect MT5**: Use the connection settings in the sidebar
            2. **Verify Account**: Ensure your trading account is properly configured
            3. **Check Permissions**: Make sure automated trading is enabled

            #### 📊 Live Trading Features:
            - **Real-time Positions**: Monitor all open trades with live P&L
            - **Quick Trade Entry**: Enter market orders with SL/TP in one click
            - **Position Management**: Close or modify positions instantly
            - **Risk Monitoring**: Track margin levels and account health
            - **Market Data**: Live bid/ask prices and spread information

            #### ⚠️ Risk Management:
            - Always set appropriate stop losses
            - Monitor margin levels closely
            - Use position sizing based on risk tolerance
            - Consider market volatility before trading
            """)
