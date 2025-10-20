import streamlit as st

def render_tab(tab, get_latest_forex_news):
    with tab:
        st.subheader("📰 Market News & Sentiment")

        # News controls
        col_news1, col_news2 = st.columns(2)
        with col_news1:
            if st.button("🔄 Refresh News", width='stretch', key="refresh_news_tab"):
                st.rerun()
        with col_news2:
            auto_refresh = st.checkbox("Auto-refresh every 5 min", value=True, key="auto_refresh_tab")

        try:
            news_data = get_latest_forex_news()

            # Extract sentiment from the news data
            if isinstance(news_data, dict):
                sentiment = news_data.get('sentiment', 'neutral')
                available = news_data.get('available', False)
                article_count = news_data.get('article_count', 0)
                avg_score = news_data.get('avg_sentiment_score', 0.0)
                reason = news_data.get('reason', '')
            else:
                # Fallback if news data is not in expected format
                sentiment = 'neutral'
                available = False
                article_count = 0
                avg_score = 0.0
                reason = 'News data format error'

            # Sentiment indicator
            sentiment_colors = {'bullish': 'green', 'bearish': 'red', 'neutral': 'gray'}
            sentiment_icons = {'bullish': '📈', 'bearish': '📉', 'neutral': '➡️'}

            if available:
                st.metric(
                    "Market Sentiment",
                    f"{sentiment_icons[sentiment]} {sentiment.upper()}",
                    help=f"Based on {article_count} recent forex news articles (24h window)"
                )
            else:
                st.metric(
                    "Market Sentiment",
                    f"{sentiment_icons[sentiment]} {sentiment.upper()}",
                    help="No recent news available - using neutral sentiment"
                )

            # Enhanced news summary with more details
            st.subheader("📊 Sentiment Analysis")

            if available:
                col_detail1, col_detail2, col_detail3 = st.columns(3)

                with col_detail1:
                    st.metric("Articles Found", article_count, help="Number of relevant articles in last 24h")
                with col_detail2:
                    st.metric("Time Window", "24 Hours", help="News analysis timeframe")
                with col_detail3:
                    st.metric("Data Freshness", "Real-time", help="News updates continuously")

                # Show sentiment score
                st.metric("Sentiment Score", f"{avg_score:.3f}",
                         help="Average sentiment score (-1 to 1, where positive = bullish)")

                # Sentiment interpretation
                if sentiment == 'bullish':
                    st.success("🟢 **Bullish signals detected** - Positive market sentiment from recent news")
                elif sentiment == 'bearish':
                    st.error("🔴 **Bearish signals detected** - Negative market sentiment from recent news")
                else:
                    st.info("⚪ **Neutral sentiment** - Mixed or unclear market signals")

                # Show reason if available
                if reason:
                    st.info(f"ℹ️ {reason}")
            else:
                # No news available
                st.warning("⚠️ **No recent news available** - Trading based on technical analysis only")
                if reason:
                    st.info(f"Reason: {reason}")

                st.info("💡 **Trading will continue** with technical indicators (EMA, RSI, Bollinger Bands)")

            # Additional market context
            st.subheader("💡 Trading Implications")
            if sentiment == 'bullish' and available:
                st.write("🟢 **News-enhanced bullish bias** - Consider long positions or reducing short exposure")
            elif sentiment == 'bearish' and available:
                st.write("🔴 **News-enhanced bearish bias** - Consider short positions or reducing long exposure")
            elif not available:
                st.write("⚪ **Technical-only trading** - Monitor price action and technical indicators closely")
            else:
                st.write("⚪ **Neutral sentiment** - Monitor price action and technical indicators closely")

        except Exception as e:
            st.error(f"Unable to fetch news: {str(e)}")
            # Fallback sentiment display
            st.info("⚪ Using neutral sentiment as fallback - technical analysis will continue")
