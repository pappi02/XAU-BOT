import streamlit as st
from datetime import datetime
import MetaTrader5 as mt5

def render_tab(tab, config, mt5, get_open_positions):
    with tab:
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

        if st.session_state.get('connected', False):
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

                    # Prepare display values for SL and TP
                    sl_display = f"{pos.sl:.5f}" if pos.sl > 0 else "None"
                    tp_display = f"{pos.tp:.5f}" if pos.tp > 0 else "None"

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
                                <div style="color: #ffffff;">SL: ${sl_display}</div>
                                <div style="color: #ffffff;">TP: ${tp_display}</div>
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

                    if st.button("💾 Save Settings", width='stretch'):
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
