import streamlit as st
import datetime

def render_tab(tab, config, get_candles, add_ema_signals, add_rsi_signals, add_bollinger_signals, BasicTradingStrategy):
    with tab:
        # ======= HEADER =======
        st.markdown("### 📊 Advanced Signal Analysis")
        with st.container():
            col_sig1, col_sig2 = st.columns([2, 1])
            with col_sig1:
                timeframe_signal = st.selectbox(
                    "Select Analysis Timeframe",
                    ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
                    index=2,
                    key="signals_tab_timeframe"
                )
            with col_sig2:
                st.button("🔄 Refresh Signals", use_container_width=True, on_click=st.rerun)

        # ======= CONNECTION CHECK =======
        if not st.session_state.get('connected', False):
            st.warning("⚠️ MT5 not connected — connect to fetch signals.")
            return

        try:
            candles = get_candles(config.SYMBOL, timeframe_signal, 200)
            if candles is None or candles.empty:
                st.info("No signal data available for the selected timeframe.")
                return

            # ======= STRATEGY PROCESS =======
            signal_data = candles.copy()
            signal_data = add_ema_signals(signal_data)
            signal_data = add_rsi_signals(signal_data)
            signal_data = add_bollinger_signals(signal_data)

            strategy = BasicTradingStrategy()
            prepared_data = strategy.prepare_data(signal_data.tail(50))
            signal = strategy.generate_signal(prepared_data)

            # ======= MAIN SIGNAL CARD =======
            signal_icons = {'BUY': '📈', 'SELL': '📉', 'HOLD': '⏸️'}
            signal_colors = {'BUY': 'text-green-400', 'SELL': 'text-red-400', 'HOLD': 'text-yellow-400'}
            signal_text = signal.get("signal", "Unknown")
            signal_strength = signal.get("strength", 0)

            st.markdown(f"""
            <div class="bg-gradient-to-br from-[#0f172a] to-[#1e293b] rounded-2xl p-8 border border-sky-500/30 shadow-lg mb-6">
                <div class="text-center mb-2 text-sky-400 text-2xl font-bold tracking-tight">
                    Market Signal Overview
                </div>
                <div class="text-center text-gray-400 text-sm mb-6">
                    Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </div>
                <div class="text-center py-4">
                    <div class="text-5xl font-extrabold {signal_colors.get(signal_text, 'text-white')}">
                        {signal_icons.get(signal_text, '')} {signal_text}
                    </div>
                    <div class="text-lg text-white mt-2">Signal Strength: {signal_strength:.1f}%</div>
                    <div class="text-sm text-amber-400 mt-1 font-medium">
                        Confidence Level: <b>{"High" if signal_strength>70 else "Medium" if signal_strength>40 else "Low"}</b>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ======= METRIC GRID =======
            if "components" in signal:
                comps = signal["components"]
                st.markdown('<div class="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">', unsafe_allow_html=True)

                def metric_card(label, value, color_class="text-emerald-400"):
                    st.markdown(f"""
                    <div class="bg-white/5 rounded-xl p-4 text-center border border-sky-500/20 hover:bg-white/10 transition-all">
                        <div class="text-sm text-sky-300 mb-1">{label}</div>
                        <div class="text-xl font-semibold {color_class}">{value}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # EMA
                ema_signal = comps.get('ema_signal', 0)
                ema_trend = 'Bullish' if ema_signal == 1 else 'Bearish' if ema_signal == -1 else 'Neutral'
                metric_card("EMA Trend", ema_trend,
                            "text-emerald-400" if ema_signal == 1 else "text-red-400" if ema_signal == -1 else "text-yellow-400")

                # RSI
                rsi = comps.get('rsi_condition', 'Neutral').capitalize()
                metric_card("RSI Condition", rsi,
                            "text-emerald-400" if rsi == 'Bullish' else "text-red-400" if rsi == 'Bearish' else "text-yellow-400")

                # Bollinger
                bb = comps.get('bb_signal', 'Neutral').capitalize()
                metric_card("BB Signal", bb,
                            "text-emerald-400" if bb == 'Bullish' else "text-red-400" if bb == 'Bearish' else "text-yellow-400")

                # Confluence
                metric_card("Confluence Score", f"{comps.get('confluence', 0):.1f}")

                # Risk Bias
                metric_card("Risk Bias", comps.get('risk_bias', 'Balanced'), "text-amber-400")

                # Sizing
                metric_card("Position Size", f"{comps.get('size_factor', 1.0):.2f}x")

                st.markdown('</div>', unsafe_allow_html=True)

            # ======= INSIGHTS =======
            st.markdown("""
            <div class="bg-white/5 border border-sky-500/20 rounded-xl p-5 text-gray-300 text-[15px] leading-relaxed">
                <div class="text-sky-300 font-semibold mb-2">📘 Signal Interpretation:</div>
                • <b>BUY</b> suggests a potential upward move — scale in gradually if RSI confirms momentum.<br>
                • <b>SELL</b> implies downward bias — ideal for pullbacks or short continuation setups.<br>
                • <b>HOLD</b> means indecision — wait for more confluence or confirmation.<br><br>
                <b class="text-amber-400">Pro Tip:</b> Always confirm with a higher timeframe and volatility before increasing position size.
            </div>
            """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"⚠️ Error loading signals: {str(e)}")
