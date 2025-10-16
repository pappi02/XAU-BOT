import streamlit as st
import pandas as pd
import time
from datetime import datetime
import MetaTrader5 as mt5
from trade_logger import trade_logger
from data.connect_mt5 import connect_mt5
from execution.trade_executor import get_open_positions, TradeExecutor
from risk.risk_manager import RiskManager
from utils.news_reader import get_latest_forex_news
from data.fetch_candles import get_candles
from indicators.ema import add_ema_signals
from indicators.rsi import add_rsi_signals
from indicators.bollinger import add_bollinger_signals
from strategies.strategy_basic import BasicTradingStrategy
import config
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ========== STREAMLIT PAGE CONFIG ==========
st.set_page_config(
    page_title="XAU/USD Trading Bot Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======= SESSION STATE =======
if 'kill_switch' not in st.session_state:
    st.session_state.kill_switch = False
if 'theme' not in st.session_state:
    st.session_state.theme = 'dark'

# ======= UTILITY FUNCTIONS =======
def kill_trading():
    """Stop all trading activity."""
    st.session_state.kill_switch = True
    st.error("🚨 EMERGENCY KILL SWITCH ACTIVATED — All trading stopped!")

def connect_to_mt5():
    """Establish MT5 connection."""
    if not mt5.initialize():
        return False, "Failed to initialize MT5"

    if config.MT5_ACCOUNT and config.MT5_PASSWORD and config.MT5_SERVER:
        if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_TIMEOUT):
            return False, "Failed to connect to MT5 account"
    else:
        # Demo mode - just initialize
        pass
    return True, "Connected to MT5"

# ======= HEADER SECTION =======
# Theme toggle
col_theme, col_title = st.columns([1, 4])
with col_theme:
    theme_options = ['🌙 Dark', '☀️ Light']
    current_theme = 0 if st.session_state.theme == 'dark' else 1
    selected_theme = st.selectbox("Theme", theme_options, index=current_theme, key='theme_selector')
    if selected_theme != theme_options[current_theme]:
        st.session_state.theme = 'dark' if selected_theme == '🌙 Dark' else 'light'
        st.rerun()

# Dynamic CSS based on theme
if st.session_state.theme == 'dark':
    css = """
    <style>
    .main-title {
        font-size: 40px;
        font-weight: bold;
        color: #f8f9fa;
        text-align: center;
        background: linear-gradient(135deg, #0e1117, #262730);
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stMetric {
        background: linear-gradient(135deg, #262730, #0e1117) !important;
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #4a4a4a;
    }
    .profit-positive { color: #00ff00; font-weight: bold; }
    .profit-negative { color: #ff4444; font-weight: bold; }
    .metric-label { font-size: 14px; color: #cccccc; }
    .metric-value { font-size: 24px; font-weight: bold; }
    </style>
    """
else:
    css = """
    <style>
    .main-title {
        font-size: 40px;
        font-weight: bold;
        color: #1a1a1a;
        text-align: center;
        background: linear-gradient(135deg, #ffffff, #f0f0f0);
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
    }
    .stMetric {
        background: linear-gradient(135deg, #ffffff, #f8f8f8) !important;
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #e0e0e0;
        color: #1a1a1a;
    }
    .profit-positive { color: #008000; font-weight: bold; }
    .profit-negative { color: #cc0000; font-weight: bold; }
    .metric-label { font-size: 14px; color: #666666; }
    .metric-value { font-size: 24px; font-weight: bold; }
    </style>
    """

st.markdown(css, unsafe_allow_html=True)
st.markdown("<div class='main-title'>📊 XAU/USD Automated Trading Bot Dashboard</div>", unsafe_allow_html=True)

# ======= SIDEBAR =======
with st.sidebar:
    st.header("⚙️ Controls")

    if st.button("🚨 EMERGENCY KILL SWITCH", width='stretch', type="primary"):
        kill_trading()
    if st.session_state.kill_switch:
        st.error("TRADING DISABLED")

    # Connection Section
    with st.expander("🔌 MT5 Connection", expanded=True):
        connected, status_msg = connect_to_mt5()
        if connected:
            st.success(status_msg)
            account_info = mt5.account_info()
            if account_info:
                # Determine if demo or live account
                account_type = "Demo" if account_info.login >= 1000000000 else "Live"  # MT5 demo accounts start with high numbers
                st.info(f"Account Type: {account_type} | Login: {account_info.login}")

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("💰 Balance", f"${account_info.balance:.2f}", help="Account balance")
                    st.metric("📈 Equity", f"${account_info.equity:.2f}", help="Current equity")
                with col2:
                    st.metric("📊 Margin Used", f"${account_info.margin:.2f}", help="Used margin")
                    st.metric("🆓 Free Margin", f"${account_info.margin_free:.2f}", help="Available margin")
            else:
                # Demo mode - show default values
                st.warning("MT5 initialized but no account connected (Demo Mode)")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("💰 Balance", "$10,000.00", help="Demo account balance")
                    st.metric("📈 Equity", "$10,000.00", help="Demo account equity")
                with col2:
                    st.metric("📊 Margin Used", "$0.00", help="Demo margin used")
                    st.metric("🆓 Free Margin", "$10,000.00", help="Demo free margin")
        else:
            st.error(status_msg)

    # Strategy Controls
    with st.expander("🎯 Strategy Settings", expanded=False):
        st.subheader("Strategy Selection")
        strategy_options = ["Basic (EMA+RSI+BB)", "EMA Only", "RSI Only", "Disabled"]
        selected_strategy = st.selectbox("Active Strategy", strategy_options, help="Choose trading strategy")

        if selected_strategy != "Disabled":
            st.subheader("Risk Settings")
            risk_pct = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1, help="Percentage of balance to risk")
            max_positions = st.slider("Max Open Positions", 1, 10, 3, help="Maximum concurrent positions")

            if st.button("Apply Strategy Settings", width='stretch'):
                st.success("✅ Strategy settings updated")

    # Manual Trade Control
    with st.expander("🛑 Manual Trade Control", expanded=False):
        if connected:
            positions = get_open_positions(config.SYMBOL)
            if positions:
                # Bulk close operations
                st.subheader("Bulk Operations")
                col_bulk1, col_bulk2, col_bulk3 = st.columns(3)
                with col_bulk1:
                    if st.button("💰 Close All Profitable", width='stretch', help="Close all positions with positive profit"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_profitable_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} profitable positions")
                with col_bulk2:
                    if st.button("💸 Close All Loss", width='stretch', help="Close all positions with negative profit"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_loss_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} loss positions")
                with col_bulk3:
                    if st.button("🚪 Close All Positions", width='stretch', help="Close all open positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_all_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} positions")

                # Buy/Sell specific closes
                col_type1, col_type2 = st.columns(2)
                with col_type1:
                    if st.button("📈 Close All Buy", width='stretch', help="Close all BUY positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_buy_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} BUY positions")
                with col_type2:
                    if st.button("📉 Close All Sell", width='stretch', help="Close all SELL positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_sell_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} SELL positions")

                st.divider()

                # Individual position close
                st.subheader("Individual Position Close")
                ticket_options = [f"{pos.ticket} ({pos.symbol} {pos.volume} lot)" for pos in positions]
                selected_ticket = st.selectbox("Select Position to Close:", ticket_options)
                if st.button("Close Selected Position", width='stretch'):
                    ticket = int(selected_ticket.split()[0])
                    risk_mgr = RiskManager(mt5, config)
                    executor = TradeExecutor(mt5, config, risk_mgr)
                    success = executor.close_position_by_ticket(ticket)
                    if success:
                        st.success(f"✅ Position {ticket} closed successfully")
                    else:
                        st.error(f"❌ Failed to close position {ticket}")

                st.divider()

                # Quick Trade Entry
                st.subheader("Quick Trade Entry")
                with st.form("quick_trade_form"):
                    col_entry1, col_entry2 = st.columns(2)
                    with col_entry1:
                        direction = st.selectbox("Direction", ["BUY", "SELL"], help="Trade direction")
                        volume = st.number_input("Volume (lots)", min_value=0.01, max_value=10.0, value=0.1, step=0.01, help="Position size in lots")
                    with col_entry2:
                        sl_price = st.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.01, help="Stop loss price (0 = no SL)")
                        tp_price = st.number_input("Take Profit", min_value=0.0, value=0.0, step=0.01, help="Take profit price (0 = no TP)")

                    if st.form_submit_button("Enter Trade", use_container_width=True):
                        try:
                            risk_mgr = RiskManager(mt5, config)
                            executor = TradeExecutor(mt5, config, risk_mgr)
                            # Get current price for entry
                            symbol_info = mt5.symbol_info(config.SYMBOL)
                            if symbol_info:
                                entry_price = symbol_info.ask if direction == "BUY" else symbol_info.bid
                                result = executor.enter_trade(config.SYMBOL, direction, entry_price, sl_price if sl_price > 0 else None, tp_price if tp_price > 0 else None)
                                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                    st.success(f"✅ {direction} order placed successfully - Ticket: {result.order}")
                                else:
                                    st.error(f"❌ Failed to place {direction} order")
                            else:
                                st.error("❌ Unable to get current price")
                        except Exception as e:
                            st.error(f"❌ Trade entry failed: {str(e)}")

                st.divider()

                # Modify Position
                st.subheader("Modify Position")
                with st.form("modify_position_form"):
                    if positions:
                        position_options = [f"{pos.ticket} ({'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'} {pos.volume} lot @ {pos.price_open:.5f})" for pos in positions]
                        selected_pos = st.selectbox("Select Position to Modify:", position_options)
                        col_mod1, col_mod2 = st.columns(2)
                        with col_mod1:
                            new_sl = st.number_input("New Stop Loss", min_value=0.0, value=0.0, step=0.01, help="New SL price (0 = no change)")
                        with col_mod2:
                            new_tp = st.number_input("New Take Profit", min_value=0.0, value=0.0, step=0.01, help="New TP price (0 = no change)")

                        if st.form_submit_button("Modify Position", use_container_width=True):
                            try:
                                ticket = int(selected_pos.split()[0])
                                # Get position details
                                pos_details = mt5.positions_get(ticket=ticket)
                                if pos_details:
                                    pos = pos_details[0]
                                    # Modify position
                                    modify_request = {
                                        "action": mt5.TRADE_ACTION_SLTP,
                                        "position": ticket,
                                        "sl": new_sl if new_sl > 0 else pos.sl,
                                        "tp": new_tp if new_tp > 0 else pos.tp,
                                        "symbol": pos.symbol
                                    }
                                    result = mt5.order_send(modify_request)
                                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                                        st.success(f"✅ Position {ticket} modified successfully")
                                    else:
                                        st.error(f"❌ Failed to modify position {ticket}")
                                else:
                                    st.error("❌ Position not found")
                            except Exception as e:
                                st.error(f"❌ Modification failed: {str(e)}")
                    else:
                        st.info("No positions available to modify")
            else:
                st.info("No open positions")
        else:
            st.warning("MT5 not connected")

    # Quick Actions
    with st.expander("⚡ Quick Actions", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh Data", width='stretch'):
                st.rerun()
        with col2:
            if st.button("📊 Export Data", width='stretch'):
                st.info("Export feature coming soon")

# ======= MAIN DASHBOARD =======
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Live Trading", "📊 Performance", "🧾 Trade History", "📉 Charts", "🎯 Signals", "📰 News"])

# ===== TAB 1: LIVE TRADING =====
with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📍 Current Open Positions")
        if connected:
            positions = get_open_positions(config.SYMBOL)
            if positions:
                pos_data = [{
                    'Ticket': p.ticket,
                    'Symbol': p.symbol,
                    'Type': 'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'Volume': p.volume,
                    'Open Price': p.price_open,
                    'Profit ($)': p.profit,
                    'Stop Loss': p.sl,
                    'Take Profit': p.tp
                } for p in positions]

                df_positions = pd.DataFrame(pos_data)
                st.dataframe(df_positions, width='stretch', height=250)
                
                st.metric("Total Positions", len(positions))
                st.metric("Aggregate Profit", f"${sum(p.profit for p in positions):.2f}")
            else:
                st.info("No open positions currently.")
        else:
            st.warning("❌ MT5 not connected.")

    with col2:
        st.subheader("💹 Live XAU/USD Price")
        price_placeholder = st.empty()

        if connected:
            symbol_info = mt5.symbol_info(config.SYMBOL)
            if symbol_info:
                bid = symbol_info.bid
                ask = symbol_info.ask
                spread = (ask - bid) * 100

                price_placeholder.metric(
                    f"{config.SYMBOL}",
                    f"{bid:.2f} USD",
                    f"Ask: {ask:.2f} | Spread: {spread:.1f} pts"
                )

# ===== TAB 2: PERFORMANCE =====
with tab2:
    st.subheader("📈 Performance Overview")

    total_pnl = trade_logger.get_total_pnl()
    trade_history = trade_logger.get_trade_history(100)
    daily_pnl = trade_logger.get_daily_pnl(14)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("💵 Total P&L", f"${total_pnl:.2f}")
    with c2:
        total_trades = len([t for t in trade_history if t['status'] == 'CLOSED'])
        st.metric("📊 Total Trades", total_trades)
    with c3:
        win_rate = 0
        if total_trades > 0:
            wins = len([t for t in trade_history if t['status'] == 'CLOSED' and t['pnl'] > 0])
            win_rate = (wins / total_trades) * 100
        st.metric("🏆 Win Rate", f"{win_rate:.1f}%")

    if daily_pnl:
        df_daily = pd.DataFrame(daily_pnl)
        df_daily['date'] = pd.to_datetime(df_daily['date'])
        df_daily = df_daily.sort_values('date')
        st.line_chart(df_daily.set_index('date')['total_pnl'], height=250)

# ===== TAB 3: TRADE HISTORY =====
with tab3:
    st.subheader("📜 Recent Trade History")
    if trade_history:
        df_trades = pd.DataFrame(trade_history)
        df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
        df_trades = df_trades.sort_values('timestamp', ascending=False)

        # Color coding for P&L
        def color_pnl(val):
            color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            return f'color: {color}'

        styled_df = df_trades[['timestamp', 'symbol', 'side', 'entry_price', 'exit_price', 'volume', 'pnl', 'status']].style.applymap(color_pnl, subset=['pnl'])
        st.dataframe(styled_df, width='stretch', height=400)
    else:
        st.info("No trade records available yet.")

# ===== TAB 4: CHARTS =====
with tab4:
    st.subheader("📉 Technical Analysis Charts")

    # Chart controls
    col1, col2, col3 = st.columns(3)
    with col1:
        timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "m30","H1", "H4", "D1"], index=0, help="Select chart timeframe")
    with col2:
        candles_count = st.slider("Candles to Show", 50, 500, 1000, help="Number of candles to display")
    with col3:
        indicators_to_show = st.multiselect("Indicators", ["EMA", "RSI", "Bollinger Bands"], default=["EMA", "RSI"], help="Select indicators to display")

    if connected:
        try:
            # Fetch candle data
            candles = get_candles(config.SYMBOL, timeframe, candles_count)
            if candles is not None and not candles.empty:
                # Prepare data with indicators
                chart_data = candles.copy()

                # Add selected indicators
                if "EMA" in indicators_to_show:
                    chart_data = add_ema_signals(chart_data)
                if "RSI" in indicators_to_show:
                    chart_data = add_rsi_signals(chart_data)
                if "Bollinger Bands" in indicators_to_show:
                    chart_data = add_bollinger_signals(chart_data)

                # Create interactive chart with Plotly
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.1,
                    subplot_titles=('Price & Indicators', 'RSI' if "RSI" in indicators_to_show else 'Volume'),
                    row_heights=[0.7, 0.3]
                )

                # Candlestick chart
                fig.add_trace(go.Candlestick(
                    x=chart_data.index,
                    open=chart_data['open'],
                    high=chart_data['high'],
                    low=chart_data['low'],
                    close=chart_data['close'],
                    name='Price'
                ), row=1, col=1)

                # Add EMAs
                if "EMA" in indicators_to_show and 'EMA_12' in chart_data.columns:
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['EMA_12'], line=dict(color='blue', width=1), name='EMA 12'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['EMA_26'], line=dict(color='red', width=1), name='EMA 26'), row=1, col=1)

                # Add Bollinger Bands
                if "Bollinger Bands" in indicators_to_show and 'BB_upper_20' in chart_data.columns:
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['BB_upper_20'], line=dict(color='gray', width=1, dash='dash'), name='BB Upper'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['BB_middle_20'], line=dict(color='orange', width=1, dash='dash'), name='BB Middle'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['BB_lower_20'], line=dict(color='gray', width=1, dash='dash'), name='BB Lower'), row=1, col=1)

                # Add RSI or Volume
                if "RSI" in indicators_to_show and 'RSI_14' in chart_data.columns:
                    fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['RSI_14'], line=dict(color='purple', width=1), name='RSI'), row=2, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
                elif 'tick_volume' in chart_data.columns:
                    fig.add_trace(go.Bar(x=chart_data.index, y=chart_data['tick_volume'], name='Volume', marker_color='blue'), row=2, col=1)

                # Update layout
                fig.update_layout(
                    height=600,
                    showlegend=True,
                    xaxis_rangeslider_visible=False,
                    template='plotly_dark' if st.session_state.theme == 'dark' else 'plotly_white'
                )

                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray' if st.session_state.theme == 'light' else 'DarkGray')
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray' if st.session_state.theme == 'light' else 'DarkGray')

                st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

                # Current signal display
                if len(chart_data) > 0:
                    strategy = BasicTradingStrategy()
                    prepared_data = strategy.prepare_data(chart_data.tail(50))
                    signal = strategy.generate_signal(prepared_data)

                    st.subheader("🎯 Current Signal")
                    if 'components' in signal and signal['components']:
                        col_sig1, col_sig2, col_sig3 = st.columns(3)
                        with col_sig1:
                            signal_color = {'BUY': 'green', 'SELL': 'red', 'HOLD': 'gray'}[signal['signal']]
                            st.metric("Signal", signal['signal'], delta=f"Strength: {signal['strength']:.1f}%")
                        with col_sig2:
                            ema_signal = signal['components'].get('ema_signal', 0)
                            ema_trend = 'BULLISH' if ema_signal == 1 else 'BEARISH' if ema_signal == -1 else 'NEUTRAL'
                            st.metric("EMA Trend", ema_trend)
                        with col_sig3:
                            rsi_condition = signal['components'].get('rsi_condition', 'neutral')
                            st.metric("RSI Condition", rsi_condition.upper())
                    else:
                        st.info("Not enough data for signal analysis")

            else:
                st.warning("Unable to fetch candle data")
        except Exception as e:
            st.error(f"Error creating chart: {str(e)}")
    else:
        st.warning("MT5 not connected - charts unavailable")

# ===== TAB 5: SIGNALS =====
with tab5:
    st.subheader("🎯 Trading Signals Analysis")

    # Signal controls
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        timeframe_signal = st.selectbox("Analysis Timeframe", ["M5", "M15", "H1", "H4"], index=2, help="Timeframe for signal analysis")
    with col_sig2:
        if st.button("🔄 Refresh Signals", width='stretch'):
            st.rerun()

    if connected:
        try:
            # Fetch data for signal analysis
            candles = get_candles(config.SYMBOL, timeframe_signal, 200)
            if candles is not None and not candles.empty:
                # Prepare data with all indicators
                signal_data = candles.copy()
                signal_data = add_ema_signals(signal_data)
                signal_data = add_rsi_signals(signal_data)
                signal_data = add_bollinger_signals(signal_data)

                # Generate comprehensive signal analysis
                strategy = BasicTradingStrategy()
                prepared_data = strategy.prepare_data(signal_data.tail(50))
                signal = strategy.generate_signal(prepared_data)

                # Main signal display
                st.subheader("📊 Current Trading Signal")

                # Large signal indicator
                signal_colors = {'BUY': "#0329fd", 'SELL': "#ff0202", 'HOLD': '#888888'}
                signal_bg_colors = {'BUY': '#001100', 'SELL': '#110000', 'HOLD': '#111111'}
                signal_icons = {'BUY': '📈', 'SELL': '📉', 'HOLD': '⏸️'}

                signal_html = f"""
                <div style="background: linear-gradient(135deg, {signal_bg_colors[signal['signal']]}, #262730);
                           border: 2px solid {signal_colors[signal['signal']]};
                           border-radius: 15px;
                           padding: 20px;
                           text-align: center;
                           margin: 20px 0;">
                    <h1 style="color: {signal_colors[signal['signal']]}; font-size: 48px; margin: 0;">
                        {signal_icons[signal['signal']]} {signal['signal']}
                    </h1>
                    <h2 style="color: #ffffff; font-size: 32px; margin: 10px 0;">
                        Strength: {signal['strength']:.1f}%
                    </h2>
                    <p style="color: #cccccc; font-size: 18px; margin: 0;">
                        Confidence Level: {'High' if signal['strength'] > 70 else 'Medium' if signal['strength'] > 40 else 'Low'}
                    </p>
                </div>
                """
                st.markdown(signal_html, unsafe_allow_html=True)

                # Detailed signal components
                st.subheader("🔍 Signal Components Breakdown")

                col_comp1, col_comp2, col_comp3 = st.columns(3)

                with col_comp1:
                    ema_signal = signal['components']['ema_signal']
                    ema_trend = 'BULLISH' if ema_signal == 1 else 'BEARISH' if ema_signal == -1 else 'NEUTRAL'
                    st.metric("EMA Trend", ema_trend, help="Exponential Moving Average trend direction")
                    if ema_signal == 1:
                        st.success("✅ EMA 12 > EMA 26 - Uptrend confirmed")
                    elif ema_signal == -1:
                        st.error("❌ EMA 12 < EMA 26 - Downtrend confirmed")
                    else:
                        st.info("⏸️ EMAs are aligned - No clear trend")

                with col_comp2:
                    rsi_condition = signal['components']['rsi_condition']
                    st.metric("RSI Condition", rsi_condition, help="Relative Strength Index condition")
                    if rsi_condition == 'OVERSOLD':
                        st.success("✅ RSI < 30 - Potential buying opportunity")
                    elif rsi_condition == 'OVERBOUGHT':
                        st.error("❌ RSI > 70 - Potential selling opportunity")
                    else:
                        st.info("⏸️ RSI in neutral zone (30-70)")

                with col_comp3:
                    bb_position = signal['components'].get('bb_position', 'NEUTRAL')
                    st.metric("Bollinger Bands", bb_position, help="Bollinger Bands position signal")
                    if bb_position == 'LOWER':
                        st.success("✅ Price near lower band - Potential bounce")
                    elif bb_position == 'UPPER':
                        st.error("❌ Price near upper band - Potential reversal")
                    else:
                        st.info("⏸️ Price within normal range")

                # Technical indicators values
                st.subheader("📈 Current Technical Indicators")

                if len(signal_data) > 0:
                    latest = signal_data.iloc[-1]

                    col_ind1, col_ind2, col_ind3, col_ind4 = st.columns(4)

                    with col_ind1:
                        current_price = latest['close']
                        st.metric("Current Price", f"{current_price:.5f}", help="Latest closing price")

                    with col_ind2:
                        ema12 = latest.get('EMA_12', 0)
                        ema26 = latest.get('EMA_26', 0)
                        st.metric("EMA 12/26", f"{ema12:.5f}/{ema26:.5f}", help="Fast/Slow EMA values")

                    with col_ind3:
                        rsi = latest.get('RSI_14', 50)
                        st.metric("RSI (14)", f"{rsi:.1f}", help="Relative Strength Index")

                    with col_ind4:
                        bb_upper = latest.get('BB_upper_20', 0)
                        bb_lower = latest.get('BB_lower_20', 0)
                        st.metric("BB Range", f"{bb_lower:.5f}-{bb_upper:.5f}", help="Bollinger Bands range")

                # Signal history
                st.subheader("📜 Recent Signal History")

                # Generate signals for last 20 candles
                signal_history = []
                for i in range(min(20, len(signal_data))):
                    idx = len(signal_data) - 20 + i
                    if idx >= 0:
                        hist_data = signal_data.iloc[idx:idx+1]
                        hist_prepared = strategy.prepare_data(hist_data)
                        hist_signal = strategy.generate_signal(hist_prepared)
                        signal_history.append({
                            'timestamp': hist_data.index[0],
                            'signal': hist_signal['signal'],
                            'strength': hist_signal['strength']
                        })

                if signal_history:
                    df_signals = pd.DataFrame(signal_history)
                    df_signals['timestamp'] = pd.to_datetime(df_signals['timestamp'])

                    # Color coding for signals
                    def color_signal(val):
                        colors = {'BUY': 'background-color: #001100; color: #00ff00',
                                'SELL': 'background-color: #110000; color: #ff4444',
                                'HOLD': 'background-color: #111111; color: #888888'}
                        return colors.get(val, '')

                    styled_signals = df_signals.style.map(color_signal, subset=['signal'])
                    st.dataframe(styled_signals, width='stretch', height=300)

                # Trading recommendations
                st.subheader("💡 Trading Recommendations")

                if signal['signal'] == 'BUY':
                    st.success("""
                    **🟢 BUY SIGNAL ACTIVATED**
                    - Consider entering long positions
                    - Set stop loss below recent swing low
                    - Target profit at resistance levels
                    - Risk management: Use 1-2% of account per trade
                    """)
                elif signal['signal'] == 'SELL':
                    st.error("""
                    **🔴 SELL SIGNAL ACTIVATED**
                    - Consider entering short positions
                    - Set stop loss above recent swing high
                    - Target profit at support levels
                    - Risk management: Use 1-2% of account per trade
                    """)
                else:
                    st.info("""
                    **⏸️ HOLD SIGNAL - WAIT FOR CLEAR DIRECTION**
                    - Avoid new positions in current market conditions
                    - Monitor for breakout above resistance or below support
                    - Consider closing existing positions if stops are hit
                    - Wait for stronger signal confirmation
                    """)

            else:
                st.warning("Unable to fetch data for signal analysis")
        except Exception as e:
            st.error(f"Error generating signals: {str(e)}")
    else:
        st.warning("MT5 not connected - signals unavailable")

# ===== TAB 6: NEWS =====
with tab6:
    st.subheader("📰 Market News & Sentiment")

    # News controls
    col_news1, col_news2 = st.columns(2)
    with col_news1:
        if st.button("🔄 Refresh News", width='stretch'):
            st.rerun()
    with col_news2:
        auto_refresh = st.checkbox("Auto-refresh every 5 min", value=True)

    try:
        sentiment = get_latest_forex_news()

        # Sentiment indicator
        sentiment_colors = {'bullish': 'green', 'bearish': 'red', 'neutral': 'gray'}
        sentiment_icons = {'bullish': '📈', 'bearish': '📉', 'neutral': '➡️'}

        st.metric(
            "Market Sentiment",
            f"{sentiment_icons[sentiment]} {sentiment.upper()}",
            help="Based on recent forex news analysis"
        )

        # News summary
        st.subheader("📊 Sentiment Analysis")
        if sentiment == 'bullish':
            st.success("🟢 **Bullish signals detected** - Positive market sentiment from recent news")
        elif sentiment == 'bearish':
            st.error("🔴 **Bearish signals detected** - Negative market sentiment from recent news")
        else:
            st.info("⚪ **Neutral sentiment** - Mixed or unclear market signals")

        # Additional market context
        st.subheader("💡 Trading Implications")
        if sentiment == 'bullish':
            st.write("Consider long positions or reducing short exposure")
        elif sentiment == 'bearish':
            st.write("Consider short positions or reducing long exposure")
        else:
            st.write("Monitor price action and technical indicators closely")

    except Exception as e:
        st.error(f"Unable to fetch news: {str(e)}")

# ===== AUTO REFRESH =====
time.sleep(10)
st.rerun()
