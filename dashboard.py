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
<<<<<<< HEAD
=======
import plotly.graph_objects as go
from plotly.subplots import make_subplots
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

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
<<<<<<< HEAD
    st.session_state.theme = 'light'
=======
    st.session_state.theme = 'dark'
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

# ======= UTILITY FUNCTIONS =======
def kill_trading():
    """Stop all trading activity."""
    st.session_state.kill_switch = True
    st.error("🚨 EMERGENCY KILL SWITCH ACTIVATED — All trading stopped!")

<<<<<<< HEAD
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
=======
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
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
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

<<<<<<< HEAD
    if st.button("🚨 EMERGENCY KILL SWITCH", use_container_width=True, type="primary"):
=======
    if st.button("🚨 EMERGENCY KILL SWITCH", width='stretch', type="primary"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
        kill_trading()
    if st.session_state.kill_switch:
        st.error("TRADING DISABLED")

    # Connection Section
    with st.expander("🔌 MT5 Connection", expanded=True):
<<<<<<< HEAD
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
=======
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
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

    # Strategy Controls
    with st.expander("🎯 Strategy Settings", expanded=False):
        st.subheader("Strategy Selection")
        strategy_options = ["Basic (EMA+RSI+BB)", "EMA Only", "RSI Only", "Disabled"]
<<<<<<< HEAD
        selected_strategy = st.selectbox("Active Strategy", strategy_options, help="Choose trading strategy", key="strategy_selector")
=======
        selected_strategy = st.selectbox("Active Strategy", strategy_options, help="Choose trading strategy")

>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
        if selected_strategy != "Disabled":
            st.subheader("Risk Settings")
            risk_pct = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1, help="Percentage of balance to risk")
            max_positions = st.slider("Max Open Positions", 1, 10, 3, help="Maximum concurrent positions")
<<<<<<< HEAD
            if st.button("Apply Strategy Settings", use_container_width=True):
=======

            if st.button("Apply Strategy Settings", width='stretch'):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                st.success("✅ Strategy settings updated")

    # Manual Trade Control
    with st.expander("🛑 Manual Trade Control", expanded=False):
        if connected:
<<<<<<< HEAD
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
=======
            positions = get_open_positions(config.SYMBOL)
            if positions:
                # Bulk close operations
                st.subheader("Bulk Operations")
                col_bulk1, col_bulk2, col_bulk3 = st.columns(3)
                with col_bulk1:
                    if st.button("💰 Close All Profitable", width='stretch', help="Close all positions with positive profit"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_profitable_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} profitable positions")
                with col_bulk2:
<<<<<<< HEAD
                    if st.button("💸 Close All Loss", use_container_width=True, help="Close all positions with negative profit"):
=======
                    if st.button("💸 Close All Loss", width='stretch', help="Close all positions with negative profit"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_loss_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} loss positions")
                with col_bulk3:
<<<<<<< HEAD
                    if st.button("🚪 Close All Positions", use_container_width=True, help="Close all open positions"):
=======
                    if st.button("🚪 Close All Positions", width='stretch', help="Close all open positions"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_all_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} positions")
<<<<<<< HEAD
                col_type1, col_type2 = st.columns(2)
                with col_type1:
                    if st.button("📈 Close All Buy", use_container_width=True, help="Close all BUY positions"):
=======

                # Buy/Sell specific closes
                col_type1, col_type2 = st.columns(2)
                with col_type1:
                    if st.button("📈 Close All Buy", width='stretch', help="Close all BUY positions"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_buy_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} BUY positions")
                with col_type2:
<<<<<<< HEAD
                    if st.button("📉 Close All Sell", use_container_width=True, help="Close all SELL positions"):
=======
                    if st.button("📉 Close All Sell", width='stretch', help="Close all SELL positions"):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        risk_mgr = RiskManager(mt5, config)
                        executor = TradeExecutor(mt5, config, risk_mgr)
                        closed_count = executor.close_sell_positions(config.SYMBOL)
                        st.success(f"✅ Closed {closed_count} SELL positions")
<<<<<<< HEAD
                st.divider()
                st.subheader("Individual Position Close")
                ticket_options = [f"{pos.ticket} ({pos.symbol} {pos.volume} lot)" for pos in positions]
                selected_ticket = st.selectbox("Select Position to Close:", ticket_options, key="close_ticket_selector")
                if st.button("Close Selected Position", use_container_width=True):
=======

                st.divider()

                # Individual position close
                st.subheader("Individual Position Close")
                ticket_options = [f"{pos.ticket} ({pos.symbol} {pos.volume} lot)" for pos in positions]
                selected_ticket = st.selectbox("Select Position to Close:", ticket_options)
                if st.button("Close Selected Position", width='stretch'):
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                    ticket = int(selected_ticket.split()[0])
                    risk_mgr = RiskManager(mt5, config)
                    executor = TradeExecutor(mt5, config, risk_mgr)
                    success = executor.close_position_by_ticket(ticket)
                    if success:
                        st.success(f"✅ Position {ticket} closed successfully")
                    else:
                        st.error(f"❌ Failed to close position {ticket}")
<<<<<<< HEAD
                st.divider()
=======

                st.divider()

                # Quick Trade Entry
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                st.subheader("Quick Trade Entry")
                with st.form("quick_trade_form"):
                    col_entry1, col_entry2 = st.columns(2)
                    with col_entry1:
<<<<<<< HEAD
                        direction = st.selectbox("Direction", ["BUY", "SELL"], help="Trade direction", key="quick_trade_direction")
=======
                        direction = st.selectbox("Direction", ["BUY", "SELL"], help="Trade direction")
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                        volume = st.number_input("Volume (lots)", min_value=0.01, max_value=10.0, value=0.1, step=0.01, help="Position size in lots")
                    with col_entry2:
                        sl_price = st.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.01, help="Stop loss price (0 = no SL)")
                        tp_price = st.number_input("Take Profit", min_value=0.0, value=0.0, step=0.01, help="Take profit price (0 = no TP)")
<<<<<<< HEAD
=======

>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
                    if st.form_submit_button("Enter Trade", use_container_width=True):
                        try:
                            risk_mgr = RiskManager(mt5, config)
                            executor = TradeExecutor(mt5, config, risk_mgr)
<<<<<<< HEAD
=======
                            # Get current price for entry
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
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
<<<<<<< HEAD
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
=======

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
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
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
<<<<<<< HEAD
                else:
                    st.info("No positions available to modify")
=======
                    else:
                        st.info("No positions available to modify")
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
            else:
                st.info("No open positions")
        else:
            st.warning("MT5 not connected")

    # Quick Actions
    with st.expander("⚡ Quick Actions", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
<<<<<<< HEAD
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📈 Live Trading", "📊 Performance", "🧾 Trade History", "📉 Charts", "🎯 Signals", "📰 News", "🛡️ SL Management"])

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
=======
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
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
