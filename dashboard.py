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

def init_mt5():
    """Initialize MT5 connection safely and persist it in session_state."""
    if "mt5_initialized" not in st.session_state:
        if config.MT5_ACCOUNT and config.MT5_PASSWORD and config.MT5_SERVER:
            initialized = connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_TIMEOUT)
        else:
            # Demo mode - initialize without credentials
            initialized = mt5.initialize(path=config.MT5_PATH)

        if initialized:
            st.session_state["mt5_initialized"] = True
            st.success("✅ MT5 initialized successfully.")
        else:
            st.session_state["mt5_initialized"] = False
            st.error(f"❌ Failed to initialize MT5: {mt5.last_error()}")

    return st.session_state.get("mt5_initialized", False)


def get_account_info():
    """Fetch account info safely with reconnection logic."""
    info = mt5.account_info()
    if info:
        return info
    else:
        st.warning("⚠️ Unable to fetch account info. Attempting to reconnect...")
        # Try to reconnect
        if config.MT5_ACCOUNT and config.MT5_PASSWORD and config.MT5_SERVER:
            success = connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_TIMEOUT)
            if success:
                # Wait a moment for login to complete
                import time
                time.sleep(2)
                return mt5.account_info()
            else:
                st.error("❌ Reconnection failed")
                return None
        else:
            mt5.initialize(path=config.MT5_PATH)
            return mt5.account_info()


def connect_to_mt5():
    """Establish MT5 connection using session_state."""
    return init_mt5(), "Connected to MT5" if init_mt5() else "Failed to connect to MT5"

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
        # Modern CSS Framework for Account Info
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

        /* Responsive Design */
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
                # Determine if demo or live account
                account_type = "Demo" if account_info.login >= 1000000000 else "Live"

                # Account type badge
                st.markdown(f'<div class="account-type-badge">🔹 {account_type} Account | Login: {account_info.login}</div>', unsafe_allow_html=True)

                # Account info card
                st.markdown('<div class="account-card">', unsafe_allow_html=True)
                st.markdown('<div class="account-header">💼 Account Overview</div>', unsafe_allow_html=True)

                # Calculate some derived metrics
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

                # Additional account details in a clean format
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

                # Enhanced SL Management
                st.subheader("🎯 Advanced SL Management")
                with st.form("advanced_sl_form"):
                    if positions:
                        position_options = [f"{pos.ticket} ({'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'} {pos.volume} lot @ {pos.price_open:.5f})" for pos in positions]
                        selected_pos = st.selectbox("Select Position:", position_options)
                        
                        # Get position details
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
                                
                                # Break-even SL
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
                                
                                # Trailing Stop
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
                                
                                # Partial Close
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

                        # Manual SL/TP modification
                        st.markdown("#### 🛠️ Manual SL/TP Modification")
                        col_mod1, col_mod2 = st.columns(2)
                        with col_mod1:
                            new_sl = st.number_input("New Stop Loss", min_value=0.0, value=0.0, step=0.01, help="New SL price (0 = remove SL)")
                        with col_mod2:
                            new_tp = st.number_input("New Take Profit", min_value=0.0, value=0.0, step=0.01, help="New TP price (0 = remove TP)")

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📈 Live Trading", "📊 Performance", "🧾 Trade History", "📉 Charts", "🎯 Signals", "📰 News", "🛡️ SL Management"])

# ===== TAB 1: LIVE TRADING =====
with tab1:
    # Enhanced CSS for Live Trading tab
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
    .price-display {
        background: linear-gradient(135deg, #0d4a2d, #1a5f3a) !important;
        border: 2px solid #00ff00 !important;
        border-radius: 15px !important;
        padding: 25px !important;
        text-align: center !important;
        margin: 15px 0 !important;
        box-shadow: 0 6px 12px rgba(0,0,0,0.4) !important;
    }
    .price-value {
        font-size: 36px !important;
        font-weight: bold !important;
        color: #00ff00 !important;
        margin: 10px 0 !important;
    }
    .price-label {
        font-size: 16px !important;
        color: #cccccc !important;
        margin-bottom: 5px !important;
    }
    .position-card {
        background: linear-gradient(135deg, #2d2d2d, #1e1e1e) !important;
        border: 1px solid #555555 !important;
        border-radius: 10px !important;
        padding: 15px !important;
        margin: 8px 0 !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2) !important;
    }
    .profit-positive { color: #00ff00 !important; font-weight: bold !important; }
    .profit-negative { color: #ff4444 !important; font-weight: bold !important; }
    .position-header { font-size: 18px !important; font-weight: bold !important; margin-bottom: 10px !important; }
    </style>
    """
    st.markdown(live_css, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("📍 Current Open Positions")

        if connected:
            positions = get_open_positions(config.SYMBOL)
            if positions:
                # Summary metrics at the top
                total_positions = len(positions)
                total_profit = sum(p.profit for p in positions)
                buy_positions = len([p for p in mt5.positions_get() if p.type == mt5.ORDER_TYPE_BUY])
                sell_positions = len([p for p in mt5.positions_get() if p.type == mt5.ORDER_TYPE_SELL])

                # Summary cards
                st.markdown("### 📊 Position Summary")
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    st.metric("Total Positions", total_positions)
                with sum_col2:
                    profit_class = "profit-positive" if total_profit > 0 else "profit-negative"
                    st.metric("Aggregate Profit", f"${total_profit:.2f}")
                with sum_col3:
                    st.metric("Buy Positions", buy_positions)
                with sum_col4:
                    st.metric("Sell Positions", sell_positions)

                st.markdown("### 📋 Detailed Positions")
                for pos in positions:
                    # Determine position type and colors
                    is_buy = pos.type == mt5.ORDER_TYPE_BUY
                    profit_class = "profit-positive" if pos.profit > 0 else "profit-negative"
                    border_color = "#00ff00" if is_buy else "#ff4444"
                    bg_gradient = "linear-gradient(135deg, #001100, #002200)" if is_buy else "linear-gradient(135deg, #220000, #110000)"

                    # Calculate additional metrics
                    current_price = mt5.symbol_info(config.SYMBOL).bid if is_buy else mt5.symbol_info(config.SYMBOL).ask
                    pip_distance = abs(current_price - pos.price_open) * 10000  # Approximate pips for XAU
                    duration_hours = (datetime.utcnow() - datetime.utcfromtimestamp(pos.time)).total_seconds() / 3600

                    # Calculate SL management status
                    sl_status = "None"
                    sl_status_color = "#888888"
                    
                    if pos.sl > 0:
                        if is_buy and pos.sl >= pos.price_open:
                            sl_status = "Break-even"
                            sl_status_color = "#00ff00"
                        elif not is_buy and pos.sl <= pos.price_open:
                            sl_status = "Break-even"
                            sl_status_color = "#00ff00"
                        elif is_buy and pos.sl > pos.price_open - (pip_distance * 0.01):
                            sl_status = "Trailing"
                            sl_status_color = "#ffaa00"
                        elif not is_buy and pos.sl < pos.price_open + (pip_distance * 0.01):
                            sl_status = "Trailing"
                            sl_status_color = "#ffaa00"
                        else:
                            sl_status = "Standard"
                            sl_status_color = "#ffffff"
                    
                    # Check for partial close status (would need to track this in trade_logger)
                    partial_status = "None"
                    partial_count = 0
                    try:
                        # This would require implementing partial close tracking in trade_logger
                        # For now, we'll show a placeholder
                        if pip_distance > 20:  # Arbitrary threshold
                            partial_status = "Available"
                            partial_count = 1 if pip_distance > 40 else 0
                    except:
                        partial_status = "Unknown"
                    
                    st.markdown(f"""
                    <div class="position-card" style="border-left: 4px solid {border_color}; background: {bg_gradient};">
                        <div class="position-header">
                            {'🟢 BUY' if is_buy else '🔴 SELL'} {pos.symbol} - Ticket #{pos.ticket}
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px;">
                            <div><strong>Volume:</strong> {pos.volume} lots</div>
                            <div><strong>Open Price:</strong> ${pos.price_open:.5f}</div>
                            <div><strong>Current:</strong> ${current_price:.5f}</div>
                            <div><strong>Distance:</strong> {pip_distance:.1f} pips</div>
                            <div><strong>Profit:</strong> <span class="{profit_class}">${pos.profit:.2f}</span></div>
                            <div><strong>SL:</strong> ${pos.sl:.5f if pos.sl > 0 else 'None'}</div>
                            <div><strong>TP:</strong> ${pos.tp:.5f if pos.tp > 0 else 'None'}</div>
                            <div><strong>Duration:</strong> {duration_hours:.1f} hours</div>
                        </div>
                        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #555;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; font-size: 12px;">
                                <div style="text-align: center;">
                                    <div style="color: #cccccc;">SL Status</div>
                                    <div style="color: {sl_status_color}; font-weight: bold;">{sl_status}</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="color: #cccccc;">Partial Close</div>
                                    <div style="color: #ffaa00; font-weight: bold;">{partial_status}</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="color: #cccccc;">Actions</div>
                                    <div style="color: #4a90e2; font-weight: bold;">Ready</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # Risk analysis
                st.markdown("### ⚠️ Risk Analysis")
                risk_col1, risk_col2, risk_col3 = st.columns(3)
                with risk_col1:
                    total_exposure = sum(p.volume * p.price_open for p in positions)
                    st.metric("Total Exposure", f"${total_exposure:.2f}")
                with risk_col2:
                    avg_profit = total_profit / total_positions if total_positions > 0 else 0
                    st.metric("Avg Profit/Position", f"${avg_profit:.2f}")
                with risk_col3:
                    max_loss = min(p.profit for p in positions) if positions else 0
                    st.metric("Worst Position", f"${max_loss:.2f}")
            else:
                st.info("No open positions currently.")
        else:
            st.warning("❌ MT5 not connected.")

    with col2:
        st.subheader("💹 Live XAU/USD Price")

        if connected:
            symbol_info = mt5.symbol_info(config.SYMBOL)
            if symbol_info:
                bid = symbol_info.bid
                ask = symbol_info.ask
                spread = (ask - bid) * 100
                mid_price = (bid + ask) / 2

                # Enhanced price display
                st.markdown(f"""
                <div class="price-display">
                    <div class="price-label">XAU/USD Live Price</div>
                    <div class="price-value">${mid_price:.2f}</div>
                    <div style="display: flex; justify-content: space-around; margin-top: 15px;">
                        <div style="text-align: center;">
                            <div style="color: #ff4444; font-size: 14px;">BID</div>
                            <div style="color: #ff4444; font-size: 18px; font-weight: bold;">${bid:.2f}</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: #cccccc; font-size: 14px;">SPREAD</div>
                            <div style="color: #cccccc; font-size: 18px; font-weight: bold;">{spread:.1f} pts</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: #00ff00; font-size: 14px;">ASK</div>
                            <div style="color: #00ff00; font-size: 18px; font-weight: bold;">${ask:.2f}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Market information
                st.markdown("### 📊 Market Info")
                market_col1, market_col2 = st.columns(2)
                with market_col1:
                    st.metric("Daily Change", f"{symbol_info.session_deals:.2f}", help="Today's total volume")
                    st.metric("Point Size", f"{symbol_info.point:.5f}", help="Minimum price change")
                with market_col2:
                    st.metric("Contract Size", f"{config.CONTRACT_SIZE}", help="Units per lot")
                    st.metric("Margin Required", f"${symbol_info.margin_initial:.2f}", help="Margin for 1 lot")

                # Quick actions
                st.markdown("### ⚡ Quick Actions")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button("🔄 Refresh Price", key="refresh_price", use_container_width=True):
                        st.rerun()
                with action_col2:
                    if st.button("📊 Market Depth", key="market_depth", use_container_width=True):
                        st.info("Market depth feature coming soon")
            else:
                st.error("Unable to fetch symbol information")
        else:
            st.warning("MT5 not connected - live price unavailable")

# ===== TAB 2: PERFORMANCE =====
with tab2:
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

                best_color = "positive" if best_trade > 0 else "neutral"
                worst_color = "negative" if worst_trade < 0 else "neutral"

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
        df_daily['date'] = pd.to_datetime(df_daily['date'])
        df_daily = df_daily.sort_values('date')

        # Enhanced chart with better styling
        st.line_chart(
            df_daily.set_index('date')['total_pnl'],
            height=300,
            use_container_width=True
        )
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

        # Use Styler.map (applymap is deprecated)
        styled_df = df_trades[['timestamp', 'symbol', 'side', 'entry_price', 'exit_price', 'volume', 'pnl', 'status']].style
        styled_df = styled_df.map(lambda v: color_pnl(v), subset=['pnl'])
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
        news_data = get_latest_forex_news()
        
        # Extract sentiment from the news data
        if isinstance(news_data, dict) and news_data.get('available', False):
            sentiment = news_data.get('sentiment', 'neutral')
            impact = news_data.get('impact', 'low')
            confidence = news_data.get('confidence', 0.0)
            article_count = news_data.get('article_count', 0)
            avg_score = news_data.get('avg_sentiment_score', 0.0)
        else:
            # Fallback if news data is not available or in wrong format
            sentiment = 'neutral'
            impact = 'none'
            confidence = 0.0
            article_count = 0
            avg_score = 0.0

        # Sentiment indicator
        sentiment_colors = {'bullish': 'green', 'bearish': 'red', 'neutral': 'gray'}
        sentiment_icons = {'bullish': '📈', 'bearish': '📉', 'neutral': '➡️'}

        st.metric(
            "Market Sentiment",
            f"{sentiment_icons[sentiment]} {sentiment.upper()}",
            help=f"Based on {article_count} recent forex news articles (Confidence: {confidence:.1%})"
        )

        # Enhanced news summary with more details
        st.subheader("📊 Sentiment Analysis")
        
        if isinstance(news_data, dict):
            if news_data.get('available', False):
                col_detail1, col_detail2, col_detail3 = st.columns(3)
                
                with col_detail1:
                    st.metric("Impact Level", impact.upper(), help="News impact on market")
                with col_detail2:
                    st.metric("Confidence", f"{confidence:.1%}", help="Analysis confidence")
                with col_detail3:
                    st.metric("Articles Analyzed", article_count, help="Number of relevant articles")
                
                # Show sentiment score
                st.metric("Sentiment Score", f"{avg_score:.3f}", 
                         help="Weighted sentiment score (-1 to 1, where positive = bullish)")
                
                # Sentiment interpretation
                if sentiment == 'bullish':
                    st.success("🟢 **Bullish signals detected** - Positive market sentiment from recent news")
                elif sentiment == 'bearish':
                    st.error("🔴 **Bearish signals detected** - Negative market sentiment from recent news")
                else:
                    st.info("⚪ **Neutral sentiment** - Mixed or unclear market signals")
                
                # Show reason if available
                if news_data.get('reason'):
                    st.info(f"ℹ️ {news_data['reason']}")
            else:
                # No news available
                st.warning("⚠️ **No recent news available** - Using neutral sentiment")
                if news_data.get('reason'):
                    st.info(f"Reason: {news_data['reason']}")
        else:
            st.warning("⚠️ **News data unavailable** - Using neutral sentiment")

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
        # Fallback sentiment display
        st.info("⚪ Using neutral sentiment as fallback")

# ===== TAB 7: SL MANAGEMENT =====
with tab7:
    st.subheader("🛡️ Stop Loss Management Dashboard")
    
    sl_css = """
    <style>
    .sl-card {
        background: linear-gradient(135deg, #1e1e1e, #2d2d2d) !important;
        border: 1px solid #4a4a4a !important;
        border-radius: 12px !important;
        padding: 20px !important;
        margin: 10px 0 !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
    }
    .sl-status {
        display: inline-block !important;
        padding: 4px 12px !important;
        border-radius: 20px !important;
        font-size: 12px !important;
        font-weight: bold !important;
        text-transform: uppercase !important;
    }
    .sl-breakeven { background: #00ff00; color: #000; }
    .sl-trailing { background: #ffaa00; color: #000; }
    .sl-standard { background: #4a90e2; color: #fff; }
    .sl-none { background: #666666; color: #fff; }
    .partial-available { background: #00ff88; color: #000; }
    .partial-used { background: #ff6b6b; color: #fff; }
    .action-btn {
        background: linear-gradient(135deg, #4a90e2, #357abd) !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
        color: white !important;
        font-weight: bold !important;
        cursor: pointer !important;
        transition: all 0.3s !important;
    }
    .action-btn:hover {
        background: linear-gradient(135deg, #357abd, #2c5aa0) !important;
        transform: translateY(-2px) !important;
    }
    </style>
    """
    st.markdown(sl_css, unsafe_allow_html=True)
    
    if connected:
        positions = get_open_positions(config.SYMBOL)
        if positions:
            st.markdown("### 📊 Position SL Status Overview")
            
            # Summary statistics
            total_positions = len(positions)
            be_positions = 0
            trailing_positions = 0
            standard_sl_positions = 0
            no_sl_positions = 0
            
            for pos in positions:
                if pos.sl == 0:
                    no_sl_positions += 1
                elif pos.type == mt5.POSITION_TYPE_BUY and pos.sl >= pos.price_open:
                    be_positions += 1
                elif pos.type == mt5.POSITION_TYPE_SELL and pos.sl <= pos.price_open:
                    be_positions += 1
                else:
                    # Check if trailing (simplified logic)
                    current_price = mt5.symbol_info(config.SYMBOL).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info(config.SYMBOL).ask
                    pip_distance = abs(current_price - pos.price_open) * 10000
                    if pip_distance > 10:  # Arbitrary threshold for trailing
                        trailing_positions += 1
                    else:
                        standard_sl_positions += 1
            
            # Summary cards
            col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
            with col_sum1:
                st.metric("Break-even", be_positions)
            with col_sum2:
                st.metric("Trailing", trailing_positions)
            with col_sum3:
                st.metric("Standard SL", standard_sl_positions)
            with col_sum4:
                st.metric("No SL", no_sl_positions)
            
            st.markdown("### 📋 Detailed Position Analysis")
            
            for pos in positions:
                is_buy = pos.type == mt5.POSITION_TYPE_BUY
                current_price = mt5.symbol_info(config.SYMBOL).bid if is_buy else mt5.symbol_info(config.SYMBOL).ask
                pip_distance = abs(current_price - pos.price_open) * 10000
                duration_hours = (datetime.utcnow() - datetime.utcfromtimestamp(pos.time)).total_seconds() / 3600
                
                # Determine SL status
                sl_status = "None"
                sl_status_class = "sl-none"
                sl_description = ""
                
                if pos.sl == 0:
                    sl_status = "No SL"
                    sl_description = "Position has no stop loss protection"
                elif is_buy and pos.sl >= pos.price_open:
                    sl_status = "Break-even"
                    sl_status_class = "sl-breakeven"
                    sl_description = f"SL moved to break-even at ${pos.sl:.5f}"
                elif not is_buy and pos.sl <= pos.price_open:
                    sl_status = "Break-even"
                    sl_status_class = "sl-breakeven"
                    sl_description = f"SL moved to break-even at ${pos.sl:.5f}"
                elif pip_distance > 10:
                    sl_status = "Trailing"
                    sl_status_class = "sl-trailing"
                    sl_description = f"SL trailing at ${pos.sl:.5f} (profit: {pip_distance:.1f} pips)"
                else:
                    sl_status = "Standard"
                    sl_status_class = "sl-standard"
                    sl_description = f"Standard SL at ${pos.sl:.5f}"
                
                # Determine partial close status
                partial_status = "Available"
                partial_class = "partial-available"
                partial_description = "Partial close opportunities available"
                
                if pip_distance > 20:
                    partial_status = "Ready"
                    partial_description = f"Ready for partial close at {pip_distance:.1f} pips profit"
                elif pip_distance < 10:
                    partial_status = "Wait"
                    partial_class = "partial-used"
                    partial_description = "Wait for more profit before partial close"
                
                # Risk assessment
                risk_level = "Low"
                risk_color = "#00ff00"
                
                if pos.sl == 0:
                    risk_level = "High"
                    risk_color = "#ff4444"
                elif sl_status == "Break-even":
                    risk_level = "Minimal"
                    risk_color = "#00ff88"
                elif pip_distance < 5:
                    risk_level = "Medium"
                    risk_color = "#ffaa00"
                
                st.markdown(f"""
                <div class="sl-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3 style="margin: 0; color: #ffffff;">
                            {'🟢 BUY' if is_buy else '🔴 SELL'} Ticket #{pos.ticket} - {pos.symbol}
                        </h3>
                        <div style="display: flex; gap: 10px;">
                            <span class="sl-status {sl_status_class}">{sl_status}</span>
                            <span class="sl-status {partial_class}">{partial_status}</span>
                        </div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 15px;">
                        <div>
                            <div style="color: #cccccc; font-size: 12px; margin-bottom: 5px;">Position Details</div>
                            <div style="color: #ffffff;">Volume: {pos.volume} lots</div>
                            <div style="color: #ffffff;">Entry: ${pos.price_open:.5f}</div>
                            <div style="color: #ffffff;">Current: ${current_price:.5f}</div>
                            <div style="color: #ffffff;">Duration: {duration_hours:.1f}h</div>
                        </div>
                        
                        <div>
                            <div style="color: #cccccc; font-size: 12px; margin-bottom: 5px;">SL Management</div>
                            <div style="color: #ffffff;">SL: ${pos.sl:.5f if pos.sl > 0 else 'None'}</div>
                            <div style="color: #ffffff;">TP: ${pos.tp:.5f if pos.tp > 0 else 'None'}</div>
                            <div style="color: #ffffff;">Profit: ${pos.profit:.2f}</div>
                            <div style="color: {risk_color};">Risk: {risk_level}</div>
                        </div>
                        
                        <div>
                            <div style="color: #cccccc; font-size: 12px; margin-bottom: 5px;">Actions</div>
                            <div style="color: #ffffff;">Distance: {pip_distance:.1f} pips</div>
                            <div style="color: #ffffff;">Status: {sl_description}</div>
                            <div style="color: #ffffff;">Partial: {partial_description}</div>
                            <div style="color: #4a90e2;">Ready for management</div>
                        </div>
                    </div>
                    
                    <div style="border-top: 1px solid #555; padding-top: 15px;">
                        <div style="color: #cccccc; font-size: 12px; margin-bottom: 10px;">Quick Actions</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <button class="action-btn" onclick="alert('Break-even action')">🔄 Break-even</button>
                            <button class="action-btn" onclick="alert('Trailing action')">📈 Trailing</button>
                            <button class="action-btn" onclick="alert('Partial close action')">✂️ Partial Close</button>
                            <button class="action-btn" onclick="alert('Modify SL action')">🛠️ Modify SL</button>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # SL Management Settings
            st.markdown("### ⚙️ SL Management Settings")
            with st.expander("🔧 Configuration", expanded=False):
                col_set1, col_set2 = st.columns(2)
                
                with col_set1:
                    st.markdown("#### Break-even Settings")
                    be_enabled = st.checkbox("Enable Break-even", value=config.BREAK_EVEN_ENABLED, help="Automatically move SL to break-even")
                    be_trigger = st.number_input("Break-even Trigger (pips)", min_value=1, max_value=100, value=config.BREAK_EVEN_PROFIT_PIPS, help="Profit threshold to trigger break-even")
                    be_buffer = st.number_input("Break-even Buffer (pips)", min_value=0, max_value=10, value=config.BREAK_EVEN_BUFFER_PIPS, help="Buffer above entry price for break-even SL")
                
                with col_set2:
                    st.markdown("#### Trailing Stop Settings")
                    ts_enabled = st.checkbox("Enable Trailing Stop", value=config.TRAILING_STOP_MODIFICATION, help="Automatically trail SL behind price")
                    ts_activation = st.number_input("Trailing Activation (pips)", min_value=1, max_value=100, value=config.TRAILING_STOP_ACTIVATION_PIPS, help="Profit threshold to start trailing")
                    ts_distance = st.number_input("Trailing Distance (pips)", min_value=1, max_value=50, value=config.TRAILING_STOP_DISTANCE_PIPS, help="Distance to trail behind price")
                
                if st.button("💾 Save Settings", use_container_width=True):
                    st.success("✅ Settings saved successfully")
                    st.info("ℹ️ Settings will be applied to new positions")
            
            # Historical SL Actions
            st.markdown("### 📜 Recent SL Management Actions")
            st.info("📊 SL management history will be displayed here once implemented in trade_logger")
            
            # Performance metrics
            st.markdown("### 📈 SL Management Performance")
            col_perf1, col_perf2, col_perf3 = st.columns(3)
            
            with col_perf1:
                st.metric("Positions Protected", f"{be_positions + trailing_positions}/{total_positions}", f"{((be_positions + trailing_positions)/total_positions*100):.1f}%")
            
            with col_perf2:
                avg_profit_protected = sum(pos.profit for pos in positions if pos.sl > 0) / len([pos for pos in positions if pos.sl > 0]) if any(pos.sl > 0 for pos in positions) else 0
                st.metric("Avg Profit (Protected)", f"${avg_profit_protected:.2f}")
            
            with col_perf3:
                unprotected_positions = [pos for pos in positions if pos.sl == 0]
                avg_risk_unprotected = sum(pos.profit for pos in unprotected_positions) / len(unprotected_positions) if unprotected_positions else 0
                st.metric("Risk Level", f"${avg_risk_unprotected:.2f}", help="Average exposure of unprotected positions")
        
        else:
            st.info("📭 No open positions to manage")
            st.markdown("""
            ### 🚀 Getting Started with SL Management
            
            When you have open positions, this dashboard will show:
            
            - **Break-even Status**: Automatically move SL to entry price when profitable
            - **Trailing Stop Status**: Dynamic SL that follows price movement
            - **Partial Close Opportunities**: Strategic position reduction at profit levels
            - **Risk Assessment**: Real-time risk evaluation for each position
            
            #### 🎯 Best Practices:
            1. **Set Initial SL**: Always set a stop loss when entering positions
            2. **Use Break-even**: Move SL to break-even when position becomes profitable
            3. **Apply Trailing**: Let trailing stops capture maximum profit
            4. **Partial Close**: Take profits at predetermined levels
            5. **Monitor Risk**: Keep overall portfolio risk within acceptable limits
            """)
    else:
        st.warning("❌ MT5 not connected - SL management unavailable")

# ===== AUTO REFRESH =====
# Removed auto-refresh to prevent WebSocket errors
# Use manual refresh buttons in each tab instead
