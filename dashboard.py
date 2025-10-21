import os
os.environ['STREAMLIT_SERVER_PORT'] = '8501'

import streamlit as st
import pandas as pd
import time
import requests
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
import streamlit_authenticator as stauth

# ========== STREAMLIT PAGE CONFIG ==========
st.set_page_config(
    page_title="XAU/USD Scalper Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======= SESSION STATE =======
if 'kill_switch' not in st.session_state:
    st.session_state.kill_switch = False
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

# ======= UTILITY FUNCTIONS =======
def kill_trading():
    """Stop all trading activity."""
    st.session_state.kill_switch = True
    st.error("🚨 EMERGENCY KILL SWITCH ACTIVATED — All trading stopped!")

def init_mt5():
    """Initialize MT5 connection safely and persist it in session_state."""
    if "mt5_initialized" not in st.session_state:
        # For integrated mode, MT5 is handled by run_bot.py
        # Just check if Flask API is available
        try:
            response = requests.get("http://127.0.0.1:5001/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                st.session_state["mt5_initialized"] = data.get("connected", False)
                st.session_state['connected'] = st.session_state["mt5_initialized"]  # Set 'connected' for charts tab
                if st.session_state["mt5_initialized"]:
                    st.success("✅ Connected to MT5 via Flask API.")
                else:
                    st.error("❌ MT5 not connected (check run_bot.py)")
            else:
                st.session_state["mt5_initialized"] = False
                st.session_state['connected'] = False
                st.error("❌ Flask API not available. Run run_bot.py first.")
        except requests.exceptions.RequestException:
            st.session_state["mt5_initialized"] = False
            st.session_state['connected'] = False
            st.error("❌ Cannot connect to Flask API. Run run_bot.py first.")
    return st.session_state.get("mt5_initialized", False)

def get_account_info():
    """Fetch account info from Flask API."""
    try:
        response = requests.get("http://127.0.0.1:5001/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("connected"):
                # Convert dict to object-like structure
                class AccountInfo:
                    def __init__(self, data):
                        self.login = data.get("login")
                        self.balance = data.get("balance")
                        self.equity = data.get("equity")
                        self.margin_free = data.get("free_margin")
                        self.margin_level = data.get("margin_level")
                        self.margin = data.get("equity", 0) - data.get("free_margin", 0)  # Approximate
                        self.profit = data.get("equity", 0) - data.get("balance", 0)
                        self.credit = 0  # Not provided
                        self.leverage = 400  # Default
                        self.currency = "USD"
                        self.server = config.MT5_SERVER
                return AccountInfo(data)
            else:
                st.warning("⚠️ MT5 not connected via API")
                return None
        else:
            st.error("❌ API error")
            return None
    except requests.exceptions.RequestException:
        st.error("❌ Cannot connect to Flask API")
        return None

def connect_to_mt5():
    """Establish MT5 connection via Flask API."""
    return init_mt5(), "Connected to MT5 via API" if init_mt5() else "Failed to connect to MT5 via API"

# ======= HEADER SECTION =======
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

    if st.button("🚨 EMERGENCY KILL SWITCH", use_container_width=True, type="primary"):
        kill_trading()
    if st.session_state.kill_switch:
        st.error("TRADING DISABLED")

    # Connection Section
    with st.expander("🔌 MT5 Connection", expanded=True):
        modern_css = """
        <style>
        :root {
            --primary-bg: linear-gradient(135deg, #1e3a5f, #2d4a6b);
            --secondary-bg: linear-gradient(135deg, #2d4a6b, #1e3a5f);
            --accent-color: #4a90e2;
            --accent-hover: #5ba0f2;
            --success-color: #00ff88;
            --error-color: #ff6b6b;
            --warning-color: #f7931e;
            --text-primary: #ffffff;
            --text-secondary: #b8d4f0;
            --text-muted: #888888;
            --border-radius: 12px;
            --border-radius-sm: 8px;
            --shadow-sm: 0 2px 8px rgba(0,0,0,0.15);
            --shadow-md: 0 4px 16px rgba(0,0,0,0.25);
            --shadow-lg: 0 8px 32px rgba(0,0,0,0.35);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .account-card {
            background: var(--primary-bg) !important;
            border: 2px solid var(--accent-color) !important;
            border-radius: var(--border-radius) !important;
            padding: 24px !important;
            margin: 16px 0 !important;
            box-shadow: var(--shadow-lg) !important;
            text-align: center !important;
            position: relative !important;
            overflow: hidden !important;
        }
        .account-card::before {
            content: '' !important;
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            height: 4px !important;
            background: var(--accent-color) !important;
        }
        .account-header {
            color: var(--text-primary) !important;
            font-size: 20px !important;
            font-weight: 700 !important;
            margin-bottom: 20px !important;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5) !important;
            letter-spacing: -0.025em !important;
        }
        .account-metric-grid {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)) !important;
            gap: 16px !important;
            margin-top: 20px !important;
        }
        .account-metric {
            background: var(--secondary-bg) !important;
            border: 1px solid var(--accent-color) !important;
            border-radius: var(--border-radius-sm) !important;
            padding: 16px !important;
            text-align: center !important;
            box-shadow: var(--shadow-sm) !important;
            transition: var(--transition) !important;
            position: relative !important;
            overflow: hidden !important;
        }
        .account-metric::before {
            content: '' !important;
            position: absolute !important;
            top: 0 !important;
            left: -100% !important;
            width: 100% !important;
            height: 100% !important;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent) !important;
            transition: left 0.5s !important;
        }
        .account-metric:hover {
            transform: translateY(-4px) !important;
            box-shadow: var(--shadow-md) !important;
            border-color: var(--accent-hover) !important;
        }
        .account-metric:hover::before {
            left: 100% !important;
        }
        .metric-label {
            color: var(--text-secondary) !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
            margin-bottom: 8px !important;
            display: block !important;
        }
        .metric-value {
            color: var(--text-primary) !important;
            font-size: 18px !important;
            font-weight: 700 !important;
            text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
            line-height: 1.2 !important;
        }
        .metric-value.positive {
            color: var(--success-color) !important;
            text-shadow: 0 0 8px rgba(0, 255, 136, 0.3) !important;
        }
        .metric-value.negative {
            color: var(--error-color) !important;
            text-shadow: 0 0 8px rgba(255, 107, 107, 0.3) !important;
        }
        .account-type-badge {
            background: linear-gradient(135deg, var(--warning-color), #ff6b35) !important;
            color: var(--text-primary) !important;
            padding: 10px 20px !important;
            border-radius: 24px !important;
            font-size: 14px !important;
            font-weight: 700 !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 8px !important;
            margin: 12px 0 !important;
            box-shadow: var(--shadow-md) !important;
            border: none !important;
            transition: var(--transition) !important;
        }
        .account-type-badge:hover {
            transform: scale(1.05) !important;
            box-shadow: var(--shadow-lg) !important;
        }
        .status-indicator {
            display: inline-block !important;
            width: 8px !important;
            height: 8px !important;
            border-radius: 50% !important;
            background: var(--success-color) !important;
            box-shadow: 0 0 6px var(--success-color) !important;
            animation: pulse 2s infinite !important;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .connection-status {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 8px !important;
            margin-bottom: 16px !important;
        }
        .connection-status.success {
            color: var(--success-color) !important;
        }
        .connection-status.error {
            color: var(--error-color) !important;
        }
        @media (max-width: 768px) {
            .account-metric-grid {
                grid-template-columns: 1fr !important;
                gap: 12px !important;
            }
            .account-card {
                padding: 16px !important;
                margin: 12px 0 !important;
            }
            .metric-value {
                font-size: 16px !important;
            }
        }
        </style>
        """
        st.markdown(modern_css, unsafe_allow_html=True)

        connected, status_msg = connect_to_mt5()
        if connected:
            st.success("✅ " + status_msg)
            account_info = get_account_info()
            if account_info:
                account_type = "Demo" if account_info.login >= 1000000000 else "Live"
                st.markdown(f'<div class="account-type-badge">🔹 {account_type} Account | Login: {account_info.login}</div>', unsafe_allow_html=True)
                st.markdown('<div class="account-card">', unsafe_allow_html=True)
                st.markdown('<div class="account-header">💼 Account Overview</div>', unsafe_allow_html=True)
                margin_level = (account_info.equity / account_info.margin) * 100 if account_info.margin > 0 else 0
                free_margin_pct = (account_info.margin_free / account_info.equity) * 100 if account_info.equity > 0 else 0
                st.markdown(f'''
                <div class="account-metric-grid">
                    <div class="account-metric">
                        <div class="metric-label">💰 Balance</div>
                        <div class="metric-value">${account_info.balance:.2f}</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">📈 Equity</div>
                        <div class="metric-value ${"positive" if account_info.equity >= account_info.balance else "negative" if account_info.equity < account_info.balance else ""}">${account_info.equity:.2f}</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">📊 Margin Used</div>
                        <div class="metric-value">${account_info.margin:.2f}</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">🆓 Free Margin</div>
                        <div class="metric-value ${"positive" if account_info.margin_free > 100 else "negative" if account_info.margin_free < 50 else ""}">${account_info.margin_free:.2f}</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">📊 Margin Level</div>
                        <div class="metric-value ${"positive" if margin_level > 200 else "negative" if margin_level < 100 else ""}">{margin_level:.1f}%</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">💯 Free Margin %</div>
                        <div class="metric-value ${"positive" if free_margin_pct > 50 else "negative" if free_margin_pct < 20 else ""}">{free_margin_pct:.1f}%</div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                with st.expander("📋 Account Details", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Server", account_info.server if hasattr(account_info, 'server') else "N/A")
                        st.metric("Currency", account_info.currency if hasattr(account_info, 'currency') else "USD")
                        st.metric("Leverage", f"1:{account_info.leverage}" if hasattr(account_info, 'leverage') else "N/A")
                    with col2:
                        st.metric("Credit", f"${account_info.credit:.2f}" if hasattr(account_info, 'credit') else "$0.00")
                        st.metric("Profit", f"${account_info.profit:.2f}" if hasattr(account_info, 'profit') else "$0.00")
            else:
                st.warning("⚠️ MT5 initialized but no account connected (Demo Mode)")
                st.markdown('<div class="account-card">', unsafe_allow_html=True)
                st.markdown('<div class="account-header">🎮 Demo Account</div>', unsafe_allow_html=True)
                st.markdown('''
                <div class="account-metric-grid">
                    <div class="account-metric">
                        <div class="metric-label">💰 Balance</div>
                        <div class="metric-value">$10,000.00</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">📈 Equity</div>
                        <div class="metric-value">$10,000.00</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">📊 Margin Used</div>
                        <div class="metric-value">$0.00</div>
                    </div>
                    <div class="account-metric">
                        <div class="metric-label">🆓 Free Margin</div>
                        <div class="metric-value">$10,000.00</div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("❌ " + status_msg)

    # Strategy Controls
    with st.expander("🎯 Strategy Settings", expanded=False):
        st.subheader("Strategy Selection")
        strategy_options = ["Basic (EMA+RSI+BB)", "EMA Only", "RSI Only", "Disabled"]
        selected_strategy = st.selectbox("Active Strategy", strategy_options, help="Choose trading strategy", key="strategy_selector")
        if selected_strategy != "Disabled":
            st.subheader("Risk Settings")
            risk_pct = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1, help="Percentage of balance to risk")
            max_positions = st.slider("Max Open Positions", 1, 10, 3, help="Maximum concurrent positions")
            if st.button("Apply Strategy Settings", use_container_width=True):
                st.success("✅ Strategy settings updated")

    # Manual Trade Control
    with st.expander("🛑 Manual Trade Control", expanded=False):
        if connected:
            try:
                response = requests.get("http://127.0.0.1:5001/positions", timeout=5)
                if response.status_code == 200:
                    positions_data = response.json()
                    positions = [pd.Series(p) for p in positions_data]  # Convert to series-like objects
                else:
                    positions = []
            except requests.exceptions.RequestException:
                positions = []
            if positions:
                st.subheader("Bulk Operations")
                col_bulk1, col_bulk2, col_bulk3 = st.columns(3)
                with col_bulk1:
                    if st.button("💰 Close All Profitable", use_container_width=True, help="Close all positions with positive profit"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_profitable_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} profitable positions")
                with col_bulk2:
                    if st.button("💸 Close All Loss", use_container_width=True, help="Close all positions with negative profit"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_loss_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} loss positions")
                with col_bulk3:
                    if st.button("🚪 Close All Positions", use_container_width=True, help="Close all open positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_all_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} positions")
                col_type1, col_type2 = st.columns(2)
                with col_type1:
                    if st.button("📈 Close All Buy", use_container_width=True, help="Close all BUY positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_buy_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} BUY positions")
                with col_type2:
                    if st.button("📉 Close All Sell", use_container_width=True, help="Close all SELL positions"):
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_sell_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} SELL positions")
                st.divider()
                st.subheader("Individual Position Close")
                ticket_options = [f"{pos.ticket} ({pos.symbol} {pos.volume} lot)" for pos in positions]
                selected_ticket = st.selectbox("Select Position to Close:", ticket_options, key="close_ticket_selector")
                if st.button("Close Selected Position", use_container_width=True):
                    ticket = int(selected_ticket.split()[0])
                    risk_mgr = RiskManager(mt5, config)
                    executor = TradeExecutor(mt5, config, risk_mgr)
                    success = executor.close_position_by_ticket(ticket)
                    if success:
                        st.success(f"✅ Position {ticket} closed successfully")
                    else:
                        st.error(f"❌ Failed to close position {ticket}")
                st.divider()
                st.subheader("Quick Trade Entry")
                with st.form("quick_trade_form"):
                    col_entry1, col_entry2 = st.columns(2)
                    with col_entry1:
                        direction = st.selectbox("Direction", ["BUY", "SELL"], help="Trade direction", key="quick_trade_direction")
                        volume = st.number_input("Volume (lots)", min_value=0.01, max_value=10.0, value=0.1, step=0.01, help="Position size in lots")
                    with col_entry2:
                        sl_price = st.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.01, help="Stop loss price (0 = no SL)")
                        tp_price = st.number_input("Take Profit", min_value=0.0, value=0.0, step=0.01, help="Take profit price (0 = no TP)")
                    if st.form_submit_button("Enter Trade", use_container_width=True):
                        try:
                            risk_mgr = RiskManager(mt5, config)
                            executor = TradeExecutor(mt5, config, risk_mgr)
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
                st.subheader("🎯 Advanced SL Management")
                if positions:
                    position_options = [f"{pos.ticket} ({'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'} {pos.volume} lot @ {pos.price_open:.5f})" for pos in positions]
                    selected_pos = st.selectbox("Select Position:", position_options, key="advanced_sl_position")
                    ticket = int(selected_pos.split()[0])
                    pos_details = mt5.positions_get(ticket=ticket)
                    if pos_details:
                        pos = pos_details[0]
                        col_adv1, col_adv2 = st.columns(2)
                        with col_adv1:
                            st.markdown("#### 📊 Current Position Info")
                            st.metric("Entry Price", f"${pos.price_open:.5f}")
                            st.metric("Current SL", f"${pos.sl:.5f}" if pos.sl > 0 else "None")
                            st.metric("Current TP", f"${pos.tp:.5f}" if pos.tp > 0 else "None")
                            st.metric("Current Profit", f"${pos.profit:.2f}")
                        with col_adv2:
                            st.markdown("#### ⚙️ SL Management Actions")
                            if st.button("🔄 Move to Break-even", key="breakeven_btn", use_container_width=True):
                                try:
                                    risk_mgr = RiskManager(mt5, config)
                                    executor = TradeExecutor(mt5, config, risk_mgr)
                                    success = executor.apply_break_even_sl(pos)
                                    if success:
                                        st.success("✅ SL moved to break-even")
                                    else:
                                        st.info("ℹ️ Break-even conditions not met")
                                except Exception as e:
                                    st.error(f"❌ Break-even failed: {str(e)}")
                            if st.button("📈 Apply Trailing Stop", key="trailing_btn", use_container_width=True):
                                try:
                                    risk_mgr = RiskManager(mt5, config)
                                    executor = TradeExecutor(mt5, config, risk_mgr)
                                    current_price = mt5.symbol_info(config.SYMBOL).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info(config.SYMBOL).ask
                                    success = executor.apply_trailing_stop(pos, current_price)
                                    if success:
                                        st.success("✅ Trailing stop applied")
                                    else:
                                        st.info("ℹ️ Trailing stop conditions not met")
                                except Exception as e:
                                    st.error(f"❌ Trailing stop failed: {str(e)}")
                            partial_percentage = st.slider("Partial Close %", 10, 90, 25, 5, help="Percentage of position to close")
                            if st.button("✂️ Partial Close", key="partial_btn", use_container_width=True):
                                try:
                                    risk_mgr = RiskManager(mt5, config)
                                    executor = TradeExecutor(mt5, config, risk_mgr)
                                    current_price = mt5.symbol_info(config.SYMBOL).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info(config.SYMBOL).ask
                                    success = executor.partial_close_position(pos, partial_percentage/100, current_price)
                                    if success:
                                        st.success(f"✅ {partial_percentage}% of position closed")
                                    else:
                                        st.error("❌ Partial close failed")
                                except Exception as e:
                                    st.error(f"❌ Partial close failed: {str(e)}")
                    with st.form("advanced_sl_form"):
                        st.markdown("#### 🛠️ Manual SL/TP Modification")
                        col_mod1, col_mod2 = st.columns(2)
                        with col_mod1:
                            new_sl = st.number_input("New Stop Loss", min_value=0.0, value=0.0, step=0.01, help="New SL price (0 = remove SL)")
                        with col_mod2:
                            new_tp = st.number_input("New Take Profit", min_value=0.0, value=0.0, step=0.01, help="New TP price (0 = remove TP)")
                        if st.form_submit_button("Modify Position", use_container_width=True):
                            try:
                                ticket = int(selected_pos.split()[0])
                                pos_details = mt5.positions_get(ticket=ticket)
                                if pos_details:
                                    pos = pos_details[0]
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
            if st.button("🔄 Refresh Data", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("📊 Export Data", use_container_width=True):
                st.info("Export feature coming soon")

# ======= MAIN DASHBOARD =======
from tabs.live_trading_tab import render_tab as render_live_trading_tab
from tabs.performance_tab import render_tab as render_performance_tab
from tabs.trade_history_tab import render_tab as render_trade_history_tab
from tabs.charts_tab import render_tab as render_charts_tab
from tabs.signals_tab import render_tab as render_signals_tab
from tabs.news_tab import render_tab as render_news_tab
from tabs.sl_management_tab import render_tab as render_sl_management_tab
from tabs.kb_admin_tab import render_tab as render_kb_admin_tab

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["📈 Live Trading", "📊 Performance", "🧾 Trade History", "📉 Charts", "🎯 Signals", "📰 News", "🛡️ SL Management", "🧠 KB Admin"])

def get_open_positions_api(symbol=None):
    """Get open positions from Flask API."""
    try:
        response = requests.get("http://127.0.0.1:5001/positions", timeout=5)
        if response.status_code == 200:
            positions_data = response.json()
            return [pd.Series(p) for p in positions_data]
        else:
            return []
    except requests.exceptions.RequestException:
        return []

render_live_trading_tab(tab1, config, mt5, get_open_positions_api)
render_performance_tab(tab2, trade_logger)
render_trade_history_tab(tab3, trade_logger)
render_charts_tab(tab4, config, mt5, get_candles, add_ema_signals, add_rsi_signals, add_bollinger_signals, BasicTradingStrategy)
render_signals_tab(tab5, config, get_candles, add_ema_signals, add_rsi_signals, add_bollinger_signals, BasicTradingStrategy)
render_news_tab(tab6, get_latest_forex_news)
render_sl_management_tab(tab7, config, mt5, get_open_positions_api)
render_kb_admin_tab(tab8)
