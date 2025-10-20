import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_tab(tab, config, mt5, get_candles, add_ema_signals, add_rsi_signals, add_bollinger_signals, BasicTradingStrategy):
    with tab:
        st.subheader("📉 Technical Analysis Charts")

        # Enhanced Chart Controls
        st.markdown("""
        <style>
        .modern-chart-controls {margin-bottom: 20px;}
        .modern-chart-controls .stSelectbox, .modern-chart-controls .stSlider, .modern-chart-controls .stMultiSelect {
            background: #222; border-radius: 8px; padding: 8px; color: #fff; border: 1px solid #444;
        }
        </style>
        """, unsafe_allow_html=True)
        with st.container():
            st.markdown('<div class="modern-chart-controls">', unsafe_allow_html=True)
            col1, col2, col3, col4 = st.columns([2,2,2,2])
            with col1:
                timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "m30","H1", "H4", "D1"], index=0, help="Select chart timeframe", key="charts_tab_timeframe")
            with col2:
                candles_count = st.slider("Candles to Show", 50, 1000, 500, help="Number of candles to display", key="charts_tab_candles")
            with col3:
                indicators_to_show = st.multiselect("Indicators", ["EMA", "RSI", "Bollinger Bands"], default=["EMA", "RSI"], help="Select indicators to display", key="charts_tab_indicators")
            with col4:
                show_annotations = st.checkbox("Show Key Levels", value=True, help="Display support/resistance annotations", key="charts_tab_annotations")
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.get('connected', False):
            try:
                candles = get_candles(config.SYMBOL, timeframe, candles_count)
                if candles is not None and not candles.empty:
                    chart_data = candles.copy()
                    if "EMA" in indicators_to_show:
                        chart_data = add_ema_signals(chart_data)
                    if "RSI" in indicators_to_show:
                        chart_data = add_rsi_signals(chart_data)
                    if "Bollinger Bands" in indicators_to_show:
                        chart_data = add_bollinger_signals(chart_data)

                    # Modern Plotly chart with navigation, tooltips, zoom, pan, and annotations
                    fig = make_subplots(
                        rows=2, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.08,
                        subplot_titles=(
                            '<b>Price & Indicators</b>',
                            '<b>RSI</b>' if "RSI" in indicators_to_show else '<b>Volume</b>'
                        ),
                        row_heights=[0.7, 0.3]
                    )

                    # Candlestick chart
                    fig.add_trace(go.Candlestick(
                        x=chart_data.index,
                        open=chart_data['open'],
                        high=chart_data['high'],
                        low=chart_data['low'],
                        close=chart_data['close'],
                        name='Price',
                        increasing_line_color='#00ff88', decreasing_line_color='#ff4444',
                        hoverinfo='x+y+name',
                        showlegend=True
                    ), row=1, col=1)

                    # Add EMAs
                    if "EMA" in indicators_to_show and 'EMA_12' in chart_data.columns:
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['EMA_12'],
                            line=dict(color='#1e90ff', width=2, dash='dot'),
                            name='EMA 12',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=1, col=1)
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['EMA_26'],
                            line=dict(color='#ff6347', width=2, dash='dash'),
                            name='EMA 26',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=1, col=1)

                    # Add Bollinger Bands
                    if "Bollinger Bands" in indicators_to_show and 'BB_upper_20' in chart_data.columns:
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['BB_upper_20'],
                            line=dict(color='#888', width=1, dash='dot'),
                            name='BB Upper',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=1, col=1)
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['BB_middle_20'],
                            line=dict(color='#ffa500', width=1, dash='dash'),
                            name='BB Middle',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=1, col=1)
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['BB_lower_20'],
                            line=dict(color='#888', width=1, dash='dot'),
                            name='BB Lower',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=1, col=1)

                    # Add RSI or Volume
                    if "RSI" in indicators_to_show and 'RSI_14' in chart_data.columns:
                        fig.add_trace(go.Scatter(
                            x=chart_data.index, y=chart_data['RSI_14'],
                            line=dict(color='#800080', width=2),
                            name='RSI',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=2, col=1)
                        fig.add_hline(y=70, line_dash="dash", line_color="#ff4444", row=2, col=1)
                        fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", row=2, col=1)
                    elif 'tick_volume' in chart_data.columns:
                        fig.add_trace(go.Bar(
                            x=chart_data.index, y=chart_data['tick_volume'],
                            name='Volume', marker_color='#1e90ff',
                            hoverinfo='x+y+name',
                            showlegend=True
                        ), row=2, col=1)

                    # Add annotations for key levels
                    if show_annotations:
                        # Example: annotate highest/lowest close in view
                        if 'close' in chart_data.columns:
                            max_close = chart_data['close'].max()
                            min_close = chart_data['close'].min()
                            max_idx = chart_data['close'].idxmax()
                            min_idx = chart_data['close'].idxmin()
                            fig.add_annotation(x=max_idx, y=max_close, text="High", showarrow=True, arrowhead=2, font=dict(color="#00ff88"), bgcolor="#222", row=1, col=1)
                            fig.add_annotation(x=min_idx, y=min_close, text="Low", showarrow=True, arrowhead=2, font=dict(color="#ff4444"), bgcolor="#222", row=1, col=1)

                    # Update layout for modern look
                    fig.update_layout(
                        height=650,
                        showlegend=True,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                            font=dict(size=13, color="#222" if st.session_state.theme == 'light' else "#fff"),
                            bgcolor="#f8f9fa" if st.session_state.theme == 'light' else "#222"
                        ),
                        xaxis=dict(
                            title=dict(text="Date/Time", font=dict(size=14, family="Arial Black")),
                            showgrid=True,
                            gridcolor="#444",
                            rangeslider=dict(visible=True, thickness=0.05),
                            tickfont=dict(size=12),
                        ),
                        yaxis=dict(
                            title=dict(text="Price", font=dict(size=14, family="Arial Black")),
                            showgrid=True,
                            gridcolor="#444",
                            tickfont=dict(size=12),
                        ),
                        xaxis2=dict(
                            title=dict(text="Date/Time", font=dict(size=14, family="Arial Black")),
                            showgrid=True,
                            gridcolor="#444",
                            tickfont=dict(size=12),
                        ),
                        yaxis2=dict(
                            title=dict(text="RSI" if "RSI" in indicators_to_show else "Volume", font=dict(size=14, family="Arial Black")),
                            showgrid=True,
                            gridcolor="#444",
                            tickfont=dict(size=12),
                        ),
                        template='plotly_dark' if st.session_state.theme == 'dark' else 'plotly_white',
                        hovermode="x unified",
                        margin=dict(t=60, b=40, l=10, r=10),
                    )

                    st.plotly_chart(fig, config={
                        'responsive': True,
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'drawrect', 'drawcircle', 'eraseshape'],
                        'scrollZoom': True
                    })

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
