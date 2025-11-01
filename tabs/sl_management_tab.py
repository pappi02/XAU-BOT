import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import MetaTrader5 as mt5
from execution.trade_executor import TradeExecutor
from risk.risk_manager import RiskManager

def render_tab(tab, config, mt5, get_open_positions):
    with tab:
        st.subheader("🛡️ Stop Loss Management Dashboard")

        # --- Inject CSS styling ---
        st.markdown("""
        <style>
        .sl-card {
            background: white !important;
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
        """, unsafe_allow_html=True)

        # --- Add JavaScript for handling action buttons ---
        components.html("""
        <script>
        function handleAction(ticket, action) {
            window.parent.postMessage({
                type: 'streamlit:setSessionState',
                key: action + '_ticket',
                value: ticket
            }, '*');
            window.parent.postMessage({
                type: 'streamlit:rerun'
            }, '*');
        }
        </script>
        """, height=0, width=0)

        # --- Ensure MT5 is connected ---
        if not st.session_state.get('connected', False):
            st.warning("❌ MT5 not connected - SL management unavailable")
            return

        # --- Retrieve positions ---
        positions = get_open_positions(config.SYMBOL)
        if not positions:
            st.info("📭 No open positions to manage")
            return

        st.markdown("### 📊 Position SL Status Overview")

        # --- Initialize counters ---
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
                current_price = mt5.symbol_info(config.SYMBOL).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info(config.SYMBOL).ask
                pip_distance = abs(current_price - pos.price_open) * 10000
                if pip_distance > 10:
                    trailing_positions += 1
                else:
                    standard_sl_positions += 1

        # --- Summary Metrics ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Break-even", be_positions)
        col2.metric("Trailing", trailing_positions)
        col3.metric("Standard SL", standard_sl_positions)
        col4.metric("No SL", no_sl_positions)

        # --- Display position details ---
        st.markdown("### 📋 Detailed Position Analysis")
        for pos in positions:
            is_buy = pos.type == mt5.POSITION_TYPE_BUY
            current_price = mt5.symbol_info(config.SYMBOL).bid if is_buy else mt5.symbol_info(config.SYMBOL).ask
            pip_distance = abs(current_price - pos.price_open) * 10000
            duration_hours = (datetime.utcnow() - datetime.utcfromtimestamp(pos.time)).total_seconds() / 3600

            sl_display = f"{pos.sl:.5f}" if pos.sl > 0 else "None"
            tp_display = f"{pos.tp:.5f}" if pos.tp > 0 else "None"

            st.markdown(f"""
            <div class="sl-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3 style="margin: 0; color: black;">
                        {'🟢 BUY' if is_buy else '🔴 SELL'} Ticket #{pos.ticket} - {pos.symbol}
                    </h3>
                    <span class="sl-status {'sl-breakeven' if pos.sl else 'sl-none'}">
                        {'Break-even' if pos.sl else 'No SL'}
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                    <div>
                        <strong>Volume:</strong> {pos.volume} lots<br>
                        <strong>Entry:</strong> ${pos.price_open:.5f}<br>
                        <strong>Current:</strong> ${current_price:.5f}<br>
                        <strong>Duration:</strong> {duration_hours:.1f}h
                    </div>
                    <div>
                        <strong>SL:</strong> {sl_display}<br>
                        <strong>TP:</strong> {tp_display}<br>
                        <strong>Profit:</strong> ${pos.profit:.2f}
                    </div>
                    <div>
                        <button class="action-btn" onclick="handleAction('{pos.ticket}', 'break_even')">🔄 Break-even</button>
                        <button class="action-btn" onclick="handleAction('{pos.ticket}', 'trailing')">📈 Trailing</button>
                        <button class="action-btn" onclick="handleAction('{pos.ticket}', 'partial_close')">✂️ Partial Close</button>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
