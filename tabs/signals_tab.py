import streamlit as st
import datetime
import time
import os
from strategies.scalping import ScalpingStrategy

# ======== RETRO TERMINAL FULL THEME ========= #
terminal_css = """
<style>
.terminal-container {
    background: radial-gradient(circle, #013b01 0%, #001a00 100%);
    border: 2px solid #00ff55;
    border-radius: 12px;
    padding: 12px;
    margin-top: 10px;
    box-shadow: 0 0 25px #00aa33;
    height: 420px;
    overflow-y: auto;
    font-family: "Courier New", monospace;
}

.terminal-line {
    font-size: 14px;
    color: #00ff55;
    margin: 2px;
}

.buy { color: #00ff55; } /* Green */
.sell { color: #ff4a4a; } /* Red */
.info { color: #42c5f5; } /* Cyan */
.error { color: #ffcc00; } /* Yellow */

.blink {
    animation: blink-animation 1s infinite;
}
@keyframes blink-animation {
    50% { opacity: 0; }
}

.curved {
    border-radius: 18px;
    backdrop-filter: blur(1px);
}
</style>
"""

st.markdown(terminal_css, unsafe_allow_html=True)

# ======== TERMINAL RENDER FUNCTION ========= #
def render_terminal(logs, typing=False):
    st.markdown('<div class="terminal-container curved" id="terminal">', unsafe_allow_html=True)

    for log in logs[-150:]:  # show latest 150 entries
        log_type = "info"
        text = log

        # auto detect signal class
        if "BUY" in log.upper(): log_type = "buy"
        if "SELL" in log.upper(): log_type = "sell"
        if "ERROR" in log.upper() or "FAILED" in log.upper(): log_type = "error"

        # Use the timestamp from the log line if available, otherwise current time
        if " - " in log and len(log.split(" - ")) >= 3:
            # Extract timestamp from log format: "2024-01-01 12:00:00 - INFO - message"
            parts = log.split(" - ", 2)
            if len(parts) >= 2:
                timestamp = parts[0].split(" ")[1] if " " in parts[0] else datetime.datetime.now().strftime("%H:%M:%S")
                text = parts[2] if len(parts) > 2 else parts[1]
            else:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        else:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if typing:
            for char in f"[{timestamp}] >> {text}":
                st.markdown(f'<span class="terminal-line {log_type}">{char}</span>', unsafe_allow_html=True)
                time.sleep(0.01)
            st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="terminal-line {log_type}">[{timestamp}] >> {text}</div>',
                unsafe_allow_html=True
            )

    # blinking cursor
    st.markdown('<span class="terminal-line blink">█</span>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # auto-scroll
    scroll_js = """
    <script>
    var objDiv = document.getElementById("terminal");
    objDiv.scrollTop = objDiv.scrollHeight;
    </script>
    """
    st.markdown(scroll_js, unsafe_allow_html=True)

# ======== FUNCTION TO READ BOT LOGS ========= #
def read_bot_logs(log_file='bot_logs.log', max_lines=150):
    """Read the last max_lines from the bot log file."""
    if not os.path.exists(log_file):
        return ["Bot logs not available yet. Start the bot to see live logs."]

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                return ["Bot logs are empty. Start the bot to generate logs."]
            # Return the last max_lines lines
            return [line.strip() for line in lines[-max_lines:]]
    except Exception as e:
        return [f"Error reading logs: {str(e)}"]

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
                st.button("🔄 Refresh Signals", width='stretch', on_click=st.rerun)

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

            # Strategy selection
            strategy_options = ["Basic (EMA+RSI+BB)", "Scalping Strategy"]
            selected_strategy = st.selectbox("Select Strategy", strategy_options, key="strategy_selection")

            if selected_strategy == "Basic (EMA+RSI+BB)":
                strategy = BasicTradingStrategy()
                prepared_data = strategy.prepare_data(signal_data.tail(50))
                signal = strategy.generate_signal(prepared_data)
            else:  # Scalping Strategy
                strategy = ScalpingStrategy()
                prepared_data = strategy.prepare_data(signal_data.tail(400))  # Scalping needs more data for patterns
                signal = strategy.generate_signal(prepared_data)

            # ======= MAIN SIGNAL CARD =======
            signal_icons = {'BUY': '📈', 'SELL': '📉', 'HOLD': '⏸️'}
            signal_colors = {'BUY': 'text-green-400', 'SELL': 'text-red-400', 'HOLD': 'text-yellow-400'}
            signal_text = signal.get("signal", "Unknown")
            signal_strength = signal.get("strength", 0)

            # Define colors based on signal
            signal_color_map = {
                'BUY': '#22c55e',  # green-500
                'SELL': '#ef4444',  # red-500
                'HOLD': '#eab308'   # yellow-500
            }
            signal_color = signal_color_map.get(signal_text, '#ffffff')

            # Log signal generation
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Signal generated: {signal_text} (Strength: {signal_strength:.1f}%, Timeframe: {timeframe_signal})")

            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #0f172a, #1e293b); border-radius: 16px; padding: 32px; border: 1px solid rgba(14, 165, 233, 0.3); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); margin-bottom: 24px;">
                <div style="text-align: center; margin-bottom: 8px; color: #38bdf8; font-size: 24px; font-weight: bold; letter-spacing: -0.025em;">
                    Market Signal Overview
                </div>
                <div style="text-align: center; color: #9ca3af; font-size: 14px; margin-bottom: 24px;">
                    Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </div>
                <div style="text-align: center; padding: 16px 0;">
                    <div style="font-size: 48px; font-weight: 800; color: {signal_color};">
                        {signal_icons.get(signal_text, '')} {signal_text}
                    </div>
                    <div style="font-size: 18px; color: #ffffff; margin-top: 8px;">Signal Strength: {signal_strength:.1f}%</div>
                    <div style="font-size: 14px; color: #fbbf24; margin-top: 4px; font-weight: 500;">
                        Confidence Level: <b>{"High" if signal_strength>70 else "Medium" if signal_strength>40 else "Low"}</b>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ======= METRIC GRID =======
            if "components" in signal:
                comps = signal["components"]

                # Define color mappings for metric cards
                def get_metric_color(value, positive_values=None, negative_values=None):
                    if positive_values and value in positive_values:
                        return '#22c55e'  # green-500
                    elif negative_values and value in negative_values:
                        return '#ef4444'  # red-500
                    else:
                        return '#eab308'  # yellow-500

                # Create metric cards using Streamlit columns instead of UnoCSS grid
                col1, col2, col3 = st.columns(3)
                col4, col5, col6 = st.columns(3)

                # EMA
                ema_signal = comps.get('ema_signal', 0)
                ema_trend = 'Bullish' if ema_signal == 1 else 'Bearish' if ema_signal == -1 else 'Neutral'
                ema_color = get_metric_color(ema_signal, [1], [-1])
                with col1:
                    st.markdown(f"""
                    <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                        <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">EMA Trend</div>
                        <div style="font-size: 20px; font-weight: 600; color: {ema_color};">{ema_trend}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # RSI
                rsi = comps.get('rsi_condition', 'Neutral').capitalize()
                rsi_color = get_metric_color(rsi, ['Bullish'], ['Bearish'])
                with col2:
                    st.markdown(f"""
                    <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                        <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">RSI Condition</div>
                        <div style="font-size: 20px; font-weight: 600; color: {rsi_color};">{rsi}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Bollinger
                bb = comps.get('bb_signal', 'Neutral').capitalize()
                bb_color = get_metric_color(bb, ['Bullish'], ['Bearish'])
                with col3:
                    st.markdown(f"""
                    <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                        <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">BB Signal</div>
                        <div style="font-size: 20px; font-weight: 600; color: {bb_color};">{bb}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Pattern Detected (for Scalping)
                pattern_detected = comps.get('pattern_detected', None)
                if pattern_detected:
                    with col4:
                        st.markdown(f"""
                        <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                            <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">Pattern Detected</div>
                            <div style="font-size: 20px; font-weight: 600; color: #10b981;">{pattern_detected.replace('_', ' ').title()}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Confluence (for Basic)
                    confluence = comps.get('confluence', 0)
                    with col4:
                        st.markdown(f"""
                        <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                            <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">Confluence Score</div>
                            <div style="font-size: 20px; font-weight: 600; color: #10b981;">{confluence:.1f}</div>
                        </div>
                        """, unsafe_allow_html=True)

                # Risk Bias
                risk_bias = comps.get('risk_bias', 'Balanced')
                with col5:
                    st.markdown(f"""
                    <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                        <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">Risk Bias</div>
                        <div style="font-size: 20px; font-weight: 600; color: #fbbf24;">{risk_bias}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Sizing
                size_factor = comps.get('size_factor', 1.0)
                with col6:
                    st.markdown(f"""
                    <div style="background: black; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(14, 165, 233, 0.2); transition: all 0.3s;">
                        <div style="font-size: 14px; color: #87ceeb; margin-bottom: 8px;">Position Size</div>
                        <div style="font-size: 20px; font-weight: 600; color: #10b981;">{size_factor:.2f}x</div>
                    </div>
                    """, unsafe_allow_html=True)

            # ======= INSIGHTS =======
            if selected_strategy == "Scalping Strategy":
                st.markdown("""
                <div style="background: white; margin-top: 6 border: 1px solid rgba(14, 165, 233, 0.2); border-radius: 12px; padding: 20px; color: black; font-size: 15px; line-height: 1.6;">
                    <div style="color: black; font-weight: 600; margin-bottom: 8px;">📘 Scalping Strategy Interpretation:</div>
                    • <b>BUY</b> signals micro-uptrend with pattern confirmation — quick scalps with tight stops.<br>
                    • <b>SELL</b> signals micro-downtrend with pattern confirmation — short-term bearish scalps.<br>
                    • <b>HOLD</b> means no clear micro-setup — wait for better volatility or pattern alignment.<br><br>
                    <b style="color: green ;">Scalping Tip:</b> Focus on 1-5 minute timeframes with high volume periods. Use 5-15 pip targets and 7-10 pip stops.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: white; margin-top: 6 border: 1px solid rgba(14, 165, 233, 0.2); border-radius: 12px; padding: 20px; color: black; font-size: 15px; line-height: 1.6;">
                    <div style="color: black; font-weight: 600; margin-bottom: 8px;">📘 Signal Interpretation:</div>
                    • <b>BUY</b> suggests a potential upward move — scale in gradually if RSI confirms momentum.<br>
                    • <b>SELL</b> implies downward bias — ideal for pullbacks or short continuation setups.<br>
                    • <b>HOLD</b> means indecision — wait for more confluence or confirmation.<br><br>
                    <b style="color: green ;">Pro Tip:</b> Always confirm with a higher timeframe and volatility before increasing position size.
                </div>
                """, unsafe_allow_html=True)

            # ======= SIGNAL LOGGING =======
            # Log signal details for monitoring and analysis (now goes to bot_logs.log)
            logger.info(f"Signal generated: {signal_text} (Strength: {signal_strength:.1f}%, Timeframe: {timeframe_signal})")
            logger.info(f"Signal components - EMA: {comps.get('ema_signal', 'N/A')}, RSI: {comps.get('rsi_condition', 'N/A')}, BB: {comps.get('bb_signal', 'N/A')}")
            if pattern_detected:
                logger.info(f"Pattern detected: {pattern_detected}")
            logger.info(f"Risk bias: {comps.get('risk_bias', 'N/A')}, Size factor: {comps.get('size_factor', 'N/A')}")

            # ======= TERMINAL DISPLAY =======
            st.markdown("### 🖥️ Live Bot Logs Terminal")
            col_term1, col_term2 = st.columns([3, 1])
            with col_term1:
                st.empty()  # Placeholder for future controls
            with col_term2:
                if st.button("🔄 Refresh Logs", key="refresh_logs_button"):
                    st.rerun()
            # Read live logs from bot_logs.log instead of session state
            live_logs = read_bot_logs()
            render_terminal(live_logs)

        except Exception as e:
            st.error(f"⚠️ Error loading signals: {str(e)}")
