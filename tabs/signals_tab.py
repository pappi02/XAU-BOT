import streamlit as st
import datetime

def render_tab(tab, config, get_candles, add_ema_signals, add_rsi_signals, add_bollinger_signals, BasicTradingStrategy):
    with tab:
        # ======= 🎨 Enhanced Styling =======
        st.markdown("""
        <style>
        .signal-container {
            background: linear-gradient(145deg, #121826, #1c2333);
            border-radius: 18px;
            padding: 28px 32px;
            box-shadow: 0 6px 20px rgba(0,0,0,0.35);
            border: 1.5px solid rgba(72, 133, 237, 0.4);
            margin-bottom: 20px;
        }
        .signal-title {
            font-size: 36px;
            font-weight: 800;
            color: #4a90e2;
            text-align: center;
            letter-spacing: -0.02em;
            margin-bottom: 10px;
        }
        .signal-time {
            color: #b0b8ca;
            font-size: 15px;
            text-align: center;
            margin-bottom: 25px;
        }
        .signal-main {
            text-align: center;
            padding: 20px;
        }
        .signal-action {
            font-size: 60px;
            font-weight: 900;
            color: #00ff88;
            text-shadow: 0 2px 15px rgba(0,255,136,0.3);
        }
        .signal-strength {
            font-size: 22px;
            color: #fff;
            margin-top: 8px;
            font-weight: 500;
        }
        .signal-confidence {
            font-size: 18px;
            margin-top: 5px;
            color: #ffa500;
        }
        .metric-container {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 22px;
            margin-top: 25px;
        }
        .metric-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 14px;
            padding: 18px 24px;
            min-width: 170px;
            text-align: center;
            border: 1px solid rgba(72,133,237,0.4);
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            transition: 0.2s;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            background: rgba(255,255,255,0.08);
        }
        .metric-label {
            font-size: 14px;
            color: #b8d4f0;
            margin-bottom: 4px;
        }
        .metric-value {
            font-size: 20px;
            font-weight: 700;
            color: #00ff88;
        }
        .metric-value.negative { color: #ff5555; }
        .metric-value.neutral { color: #ffa500; }
        .signal-insights {
            margin-top: 25px;
            font-size: 16px;
            color: #d0d4e0;
            line-height: 1.6;
            background: rgba(255,255,255,0.05);
            padding: 20px;
            border-radius: 10px;
        }
        </style>
        """, unsafe_allow_html=True)

        # ======= 🔍 Signal UI Layout =======
        st.subheader("📊 Advanced Signal Analysis")
        col_sig1, col_sig2 = st.columns(2)
        with col_sig1:
            timeframe_signal = st.selectbox(
                "Select Analysis Timeframe",
                ["M1", "M5", "M15", "H1", "H4", "D1"],
                index=2,
                key="signals_tab_timeframe"
            )
        with col_sig2:
            if st.button("🔄 Refresh Signals"):
                st.rerun()

        # ======= 📡 Check Connection =======
        if not st.session_state.get('connected', False):
            st.warning("⚠️ MT5 not connected — connect to fetch signals.")
            return

        try:
            candles = get_candles(config.SYMBOL, timeframe_signal, 200)
            if candles is None or candles.empty:
                st.info("No signal data available for the selected timeframe.")
                return

            # ======= 🧠 Process Signal =======
            signal_data = candles.copy()
            signal_data = add_ema_signals(signal_data)
            signal_data = add_rsi_signals(signal_data)
            signal_data = add_bollinger_signals(signal_data)

            strategy = BasicTradingStrategy()
            prepared_data = strategy.prepare_data(signal_data.tail(50))
            signal = strategy.generate_signal(prepared_data)

            # ======= 💡 Display Main Signal =======
            st.markdown('<div class="signal-container">', unsafe_allow_html=True)
            st.markdown('<div class="signal-title">Market Signal Overview</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="signal-time">Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>', unsafe_allow_html=True)

            signal_icons = {'BUY': '📈', 'SELL': '📉', 'HOLD': '⏸️'}
            signal_colors = {'BUY': '#00ff88', 'SELL': '#ff5555', 'HOLD': '#ffa500'}
            signal_text = signal.get("signal", "Unknown")

            st.markdown(f"""
            <div class="signal-main">
                <div class="signal-action" style="color:{signal_colors.get(signal_text, '#fff')}">
                    {signal_icons.get(signal_text, '')} {signal_text}
                </div>
                <div class="signal-strength">Signal Strength: {signal.get("strength", 0):.1f}%</div>
                <div class="signal-confidence">Confidence Level: <b>{"High" if signal["strength"]>70 else "Medium" if signal["strength"]>40 else "Low"}</b></div>
            </div>
            """, unsafe_allow_html=True)

            # ======= 🧩 Detailed Metrics =======
            if "components" in signal:
                comps = signal["components"]
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)

                # EMA
                ema_signal = comps.get('ema_signal', 0)
                ema_trend = 'Bullish' if ema_signal == 1 else 'Bearish' if ema_signal == -1 else 'Neutral'
                ema_color = 'metric-value' + ('' if ema_signal == 1 else ' negative' if ema_signal == -1 else ' neutral')
                st.markdown(f'<div class="metric-card"><div class="metric-label">EMA Trend</div><div class="{ema_color}">{ema_trend}</div></div>', unsafe_allow_html=True)

                # RSI
                rsi = comps.get('rsi_condition', 'Neutral').capitalize()
                rsi_color = 'metric-value' + ('' if rsi == 'Bullish' else ' negative' if rsi == 'Bearish' else ' neutral')
                st.markdown(f'<div class="metric-card"><div class="metric-label">RSI Condition</div><div class="{rsi_color}">{rsi}</div></div>', unsafe_allow_html=True)

                # Bollinger Bands
                bb = comps.get('bb_signal', 'Neutral').capitalize()
                bb_color = 'metric-value' + ('' if bb == 'Bullish' else ' negative' if bb == 'Bearish' else ' neutral')
                st.markdown(f'<div class="metric-card"><div class="metric-label">BB Signal</div><div class="{bb_color}">{bb}</div></div>', unsafe_allow_html=True)

                # Confluence Score
                conf_score = comps.get('confluence', 0)
                st.markdown(f'<div class="metric-card"><div class="metric-label">Confluence Score</div><div class="metric-value">{conf_score:.1f}</div></div>', unsafe_allow_html=True)

                # Risk Bias
                risk_bias = comps.get('risk_bias', 'Balanced')
                st.markdown(f'<div class="metric-card"><div class="metric-label">Risk Bias</div><div class="metric-value neutral">{risk_bias}</div></div>', unsafe_allow_html=True)

                # Position Sizing Factor
                sizing = comps.get('size_factor', 1.0)
                st.markdown(f'<div class="metric-card"><div class="metric-label">Position Size Factor</div><div class="metric-value">{sizing:.2f}x</div></div>', unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

            # ======= 📘 Insights Section =======
            st.markdown("""
            <div class="signal-insights">
                <b>Signal Interpretation:</b><br>
                • A <b>BUY</b> signal suggests a potential upward move. Consider scaling in gradually, especially if RSI confirms momentum.<br>
                • A <b>SELL</b> signal implies downward bias — ideal for pullback entries or short continuation setups.<br>
                • A <b>HOLD</b> signal means conditions are indecisive. Wait for more confluence or confirmation before entering.<br><br>
                <b>Additional Tip:</b> Always validate the signal on a higher timeframe and monitor volatility before increasing position size.
            </div>
            """, unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"⚠️ Error loading signals: {str(e)}")
