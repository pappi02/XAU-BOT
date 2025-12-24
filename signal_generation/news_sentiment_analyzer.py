"""
News Sentiment Analyzer - Analyzes news and fundamental sentiment
Integrates economic calendar events and market sentiment
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timedelta

from utils.news_reader import get_latest_forex_news

logger = logging.getLogger(__name__)

@dataclass
class SentimentSignal:
    """Container for sentiment analysis results"""
    source: str
    signal: int  # 1 (bullish), -1 (bearish), 0 (neutral)
    strength: float  # 0-100
    headline: str
    impact: str  # 'high', 'medium', 'low'
    details: Dict = None

class NewsSentimentAnalyzer:
    """
    Professional-grade news and fundamental sentiment analyzer.
    Integrates forex news, economic calendar, and macro sentiment.
    """
    
    def __init__(self):
        """Initialize sentiment analyzer"""
        self.news_cache = None
        self.cache_time = None
        self.cache_duration = 300  # 5 minutes in seconds
    
    def analyze(self) -> Dict:
        """
        Comprehensive sentiment analysis from news and fundamentals.
        
        Returns:
            Dict: Sentiment analysis with signals and impact assessment
        """
        try:
            # Get latest news
            news_data = self._get_news_data()
            
            if not news_data:
                return self._neutral_sentiment("No news data available")
            
            # Analyze news sentiment
            bullish_sentiment = 0
            bearish_sentiment = 0
            news_count = 0
            sentiment_details = []
            
            for news in news_data:
                try:
                    signal, strength, impact = self._analyze_single_news(news)
                    
                    sentiment_details.append({
                        'headline': news.get('headline', 'Unknown'),
                        'signal': signal,
                        'strength': strength,
                        'impact': impact,
                        'timestamp': news.get('timestamp', '')
                    })
                    
                    if signal == 1:
                        bullish_sentiment += strength * self._impact_weight(impact)
                        news_count += 1
                    elif signal == -1:
                        bearish_sentiment += strength * self._impact_weight(impact)
                        news_count += 1
                except Exception as e:
                    logger.debug(f"Error analyzing individual news: {e}")
            
            # Calculate combined sentiment
            if news_count > 0:
                bullish_avg = bullish_sentiment / max(1, len([s for s in sentiment_details if s['signal'] == 1]))
                bearish_avg = bearish_sentiment / max(1, len([s for s in sentiment_details if s['signal'] == -1]))
                
                if bullish_avg > bearish_avg + 20:
                    sentiment_signal = 1
                    confidence = min(100, bullish_avg)
                    condition = "Bullish Sentiment"
                elif bearish_avg > bullish_avg + 20:
                    sentiment_signal = -1
                    confidence = min(100, bearish_avg)
                    condition = "Bearish Sentiment"
                else:
                    sentiment_signal = 0
                    confidence = 40
                    condition = "Mixed Sentiment"
            else:
                sentiment_signal = 0
                confidence = 0
                condition = "Insufficient News Data"
            
            return {
                'signal': sentiment_signal,
                'confidence': confidence,
                'condition': condition,
                'sentiment_details': sentiment_details,
                'bullish_count': len([s for s in sentiment_details if s['signal'] == 1]),
                'bearish_count': len([s for s in sentiment_details if s['signal'] == -1]),
                'neutral_count': len([s for s in sentiment_details if s['signal'] == 0]),
                'impact_assessment': self._assess_overall_impact(sentiment_details),
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return self._neutral_sentiment(str(e))
    
    def _get_news_data(self) -> Optional[list]:
        """
        Get latest forex news with caching.
        
        Returns:
            list: News articles
        """
        try:
            # Check cache
            if self.news_cache is not None and self.cache_time is not None:
                time_since_cache = (datetime.now() - self.cache_time).total_seconds()
                if time_since_cache < self.cache_duration:
                    return self.news_cache
            
            # Fetch fresh news
            news = get_latest_forex_news()
            
            # Cache the result
            self.news_cache = news
            self.cache_time = datetime.now()
            
            return news
        except Exception as e:
            logger.warning(f"Error fetching news: {e}")
            return None
    
    def _analyze_single_news(self, news: Dict) -> tuple:
        """
        Analyze sentiment of a single news article.
        
        Args:
            news: News article dictionary
            
        Returns:
            tuple: (signal, strength, impact)
        """
        headline = news.get('headline', '').lower()
        impact = news.get('impact', 'low')
        
        # Keywords for sentiment analysis
        bullish_keywords = [
            'gains', 'rally', 'surge', 'spike', 'bull', 'recovery',
            'strength', 'rising', 'upbeat', 'optimism', 'growth', 'profit',
            'positive', 'strong', 'boost', 'improve', 'beat', 'outperform'
        ]
        
        bearish_keywords = [
            'falls', 'plunge', 'crash', 'slump', 'bear', 'decline',
            'weakness', 'falling', 'pessimism', 'recession', 'loss',
            'negative', 'weak', 'miss', 'underperform', 'downside',
            'inflation', 'risk', 'warning'
        ]
        
        # Count keyword occurrences
        bullish_count = sum(1 for keyword in bullish_keywords if keyword in headline)
        bearish_count = sum(1 for keyword in bearish_keywords if keyword in headline)
        
        # Determine signal
        if bullish_count > bearish_count:
            signal = 1
            strength = min(100, bullish_count * 20)
        elif bearish_count > bullish_count:
            signal = -1
            strength = min(100, bearish_count * 20)
        else:
            signal = 0
            strength = 0
        
        return signal, strength, impact
    
    def _impact_weight(self, impact: str) -> float:
        """Get weight multiplier for impact level"""
        impact_weights = {
            'high': 1.5,
            'medium': 1.0,
            'low': 0.5,
            'unknown': 0.3
        }
        return impact_weights.get(impact.lower(), 0.3)
    
    def _assess_overall_impact(self, sentiment_details: list) -> str:
        """Assess overall market impact of sentiment"""
        if not sentiment_details:
            return "NONE"
        
        high_impact_count = len([s for s in sentiment_details if s['impact'] == 'high'])
        medium_impact_count = len([s for s in sentiment_details if s['impact'] == 'medium'])
        
        if high_impact_count > 0:
            return "HIGH"
        elif medium_impact_count > 2:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _neutral_sentiment(self, reason: str = "") -> Dict:
        """Return neutral sentiment"""
        return {
            'signal': 0,
            'confidence': 0,
            'condition': f'Neutral Sentiment: {reason}',
            'sentiment_details': [],
            'bullish_count': 0,
            'bearish_count': 0,
            'neutral_count': 0,
            'impact_assessment': 'NONE',
            'timestamp': datetime.now().isoformat()
        }
    
    def get_sentiment_description(self, sentiment_signal: int) -> str:
        """Get human-readable sentiment description"""
        if sentiment_signal == 1:
            return "News is Bullish"
        elif sentiment_signal == -1:
            return "News is Bearish"
        else:
            return "News is Neutral/Mixed"
