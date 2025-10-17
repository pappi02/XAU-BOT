try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests module not available. News functionality will be limited.")

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    print("Warning: vaderSentiment module not available. Sentiment analysis will be basic.")

from datetime import datetime, timedelta
try:
    from config import NEWS_API_KEY
except ImportError:
    NEWS_API_KEY = None
    print("Warning: NEWS_API_KEY not found in config.")

import time
import hashlib
import logging

# Setup logger
logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache = {}
CACHE_EXPIRY = 300  # 5 minutes

# Enhanced keyword sets with impact weights
HIGH_IMPACT_KEYWORDS = {
    'FOMC': 1.5, 'federal reserve': 1.4, 'fed': 1.3, 'NFP': 1.5, 'non-farm payrolls': 1.4,
    'CPI': 1.4, 'consumer price index': 1.3, 'GDP': 1.4, 'unemployment': 1.3,
    'interest rate': 1.4, 'rate hike': 1.5, 'rate cut': 1.5, 'quantitative easing': 1.4,
    'central bank': 1.3, 'ecb': 1.4, 'boe': 1.3, 'boj': 1.3, 'rba': 1.3,
    'recession': 1.5, 'inflation': 1.4, 'deflation': 1.3, 'stagflation': 1.4
}

MEDIUM_IMPACT_KEYWORDS = {
    'gold': 1.2, 'XAU': 1.3, 'USD': 1.2, 'forex': 1.1, 'currency': 1.1,
    'economic data': 1.2, 'economic indicators': 1.2, 'trade war': 1.3,
    'tariffs': 1.2, 'sanctions': 1.3, 'geopolitical': 1.2, 'oil prices': 1.2,
    'commodities': 1.1, 'bond yields': 1.2, 'treasury': 1.1
}

LOW_IMPACT_KEYWORDS = {
    'market analysis': 1.0, 'trading': 1.0, 'investment': 1.0, 'economy': 1.0,
    'financial': 1.0, 'stocks': 1.0, 'bonds': 1.0
}

# Credible news sources with trust scores
CREDIBLE_SOURCES = {
    'reuters.com': 1.2, 'bloomberg.com': 1.2, 'wsj.com': 1.2, 'ft.com': 1.2,
    'cnbc.com': 1.1, 'marketwatch.com': 1.1, 'economist.com': 1.1,
    'bbc.com': 1.0, 'nytimes.com': 1.0, 'washingtonpost.com': 1.0
}

def _get_cache_key(params):
    """Generate cache key from request parameters."""
    param_str = str(sorted(params.items()))
    return hashlib.md5(param_str.encode()).hexdigest()

def _is_cache_valid(cache_entry):
    """Check if cache entry is still valid."""
    return time.time() - cache_entry['timestamp'] < CACHE_EXPIRY

def _get_cached_result(cache_key):
    """Retrieve result from cache if valid."""
    if cache_key in _cache and _is_cache_valid(_cache[cache_key]):
        logger.debug("Returning cached news sentiment result")
        return _cache[cache_key]['data']
    return None

def _set_cache_result(cache_key, data):
    """Store result in cache."""
    _cache[cache_key] = {
        'data': data,
        'timestamp': time.time()
    }
    # Clean old cache entries
    current_time = time.time()
    expired_keys = [k for k, v in _cache.items() if current_time - v['timestamp'] > CACHE_EXPIRY]
    for k in expired_keys:
        del _cache[k]

def _calculate_keyword_weight(text, keywords_dict):
    """Calculate weighted keyword matches in text."""
    text_lower = text.lower()
    total_weight = 0
    matches = 0

    for keyword, weight in keywords_dict.items():
        if keyword in text_lower:
            total_weight += weight
            matches += 1

    return total_weight, matches

def _get_source_credibility(url):
    """Get credibility score for news source."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return CREDIBLE_SOURCES.get(domain, 0.8)  # Default credibility score
    except:
        return 0.8

def _calculate_recency_weight(pub_date, now):
    """Calculate weight based on article recency (newer = higher weight)."""
    hours_old = (now - pub_date).total_seconds() / 3600

    if hours_old <= 1:
        return 1.5  # Very recent
    elif hours_old <= 6:
        return 1.2  # Recent
    elif hours_old <= 12:
        return 1.0  # Moderately recent
    elif hours_old <= 24:
        return 0.8  # Within 24 hours
    else:
        return 0.5  # Older

def _retry_api_call(url, params, max_retries=3, backoff_factor=2):
    """Retry API call with exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = backoff_factor ** attempt
            logger.warning(f"API call failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
            time.sleep(wait_time)
    return None

def get_simple_sentiment():
    """
    Simple fallback sentiment function that returns a basic sentiment string.
    
    Returns:
        str: 'bullish', 'bearish', or 'neutral'
    """
    import random
    # Simple fallback - in a real implementation, you might use cached data or basic indicators
    sentiments = ['bullish', 'bearish', 'neutral']
    weights = [0.3, 0.3, 0.4]  # Slightly favor neutral
    return random.choices(sentiments, weights=weights)[0]

def _get_fallback_news_response():
    """
    Return a fallback news response when API is not available.
    
    Returns:
        dict: Fallback news data structure
    """
    import random
    
    # Generate a simple fallback sentiment
    sentiment = get_simple_sentiment()
    
    return {
        'available': False,
        'sentiment': sentiment,
        'impact': 'low',
        'time_to_release': None,
        'reason': 'News API not available - using fallback sentiment',
        'confidence': 0.1,  # Very low confidence for fallback
        'article_count': 0,
        'avg_sentiment_score': 0.0
    }

def get_latest_forex_news():
    """
    Enhanced forex news sentiment analysis with improved filtering, caching, and scoring.

    Returns:
        dict: News data with keys:
            - 'available': bool (True if relevant news found)
            - 'sentiment': str ('bullish', 'bearish', 'neutral') if available
            - 'impact': str ('high', 'medium', 'low') if available
            - 'time_to_release': int (minutes until release, if applicable)
            - 'reason': str (explanation if no news available)
            - 'confidence': float (0-1, confidence in sentiment analysis)
            - 'article_count': int (number of relevant articles)
            - 'avg_sentiment_score': float (average compound sentiment score)
    """
    
    # Check if required dependencies are available
    if not REQUESTS_AVAILABLE:
        logger.warning("Requests module not available, returning fallback sentiment")
        return _get_fallback_news_response()
    
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not configured, returning fallback sentiment")
        return _get_fallback_news_response()
    
    try:
        # Check cache first
        cache_key = _get_cache_key({"news": "forex"})
        cached_result = _get_cached_result(cache_key)
        if cached_result:
            return cached_result

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "(gold OR USD OR forex OR XAU OR economic OR FOMC OR NFP OR CPI OR federal reserve OR interest rate)",
            "apiKey": NEWS_API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 75  # Increased for better filtering
        }

        # Use retry logic for API calls
        response = _retry_api_call(url, params)
        if not response:
            return {
                'available': False,
                'sentiment': 'neutral',
                'impact': 'none',
                'time_to_release': None,
                'reason': 'API request failed after retries',
                'confidence': 0.0,
                'article_count': 0,
                'avg_sentiment_score': 0.0
            }

        articles = response.json().get("articles", [])

        if not articles:
            result = {
                'available': False,
                'sentiment': 'neutral',
                'impact': 'none',
                'time_to_release': None,
                'reason': 'No articles found',
                'confidence': 0.0,
                'article_count': 0,
                'avg_sentiment_score': 0.0
            }
            _set_cache_result(cache_key, result)
            return result

        # Filter for recent and relevant articles (last 48 hours for better coverage)
        now = datetime.now()
        recent_articles = []
        for article in articles:
            published_at = article.get("publishedAt", "")
            if published_at:
                try:
                    pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    if (now - pub_date).total_seconds() < 172800:  # 48 hours
                        recent_articles.append(article)
                except:
                    continue

        if not recent_articles:
            result = {
                'available': False,
                'sentiment': 'neutral',
                'impact': 'none',
                'time_to_release': None,
                'reason': 'No recent articles (last 48h)',
                'confidence': 0.0,
                'article_count': 0,
                'avg_sentiment_score': 0.0
            }
            _set_cache_result(cache_key, result)
            return result

        # Enhanced sentiment analysis with weighted scoring
        weighted_scores = []
        relevant_articles = []
        total_weight = 0

        for article in recent_articles:
            title = article.get("title", "")
            description = article.get("description", "") or ""
            url = article.get("url", "")

            # Combine title and description for analysis
            full_text = f"{title}. {description}"

            # Calculate keyword weights
            high_weight, high_matches = _calculate_keyword_weight(full_text, HIGH_IMPACT_KEYWORDS)
            med_weight, med_matches = _calculate_keyword_weight(full_text, MEDIUM_IMPACT_KEYWORDS)
            low_weight, low_matches = _calculate_keyword_weight(full_text, LOW_IMPACT_KEYWORDS)

            total_keyword_weight = high_weight + med_weight + low_weight

            # Skip if no relevant keywords
            if total_keyword_weight == 0:
                continue

            # Get sentiment scores
            if VADER_AVAILABLE:
                sentiment_scores = analyzer.polarity_scores(full_text)
                compound_score = sentiment_scores['compound']
            else:
                # Basic fallback sentiment analysis
                positive_words = ['positive', 'bullish', 'growth', 'increase', 'rise', 'gain', 'strong', 'good', 'up']
                negative_words = ['negative', 'bearish', 'decline', 'decrease', 'fall', 'drop', 'weak', 'bad', 'down']
                
                text_lower = full_text.lower()
                positive_count = sum(1 for word in positive_words if word in text_lower)
                negative_count = sum(1 for word in negative_words if word in text_lower)
                
                if positive_count > negative_count:
                    compound_score = 0.3
                elif negative_count > positive_count:
                    compound_score = -0.3
                else:
                    compound_score = 0.0

            # Calculate credibility and recency weights
            credibility_weight = _get_source_credibility(url)
            recency_weight = _calculate_recency_weight(
                datetime.fromisoformat(article.get("publishedAt", "").replace('Z', '+00:00')),
                now
            )

            # Calculate final weighted score
            final_weight = total_keyword_weight * credibility_weight * recency_weight
            weighted_score = compound_score * final_weight

            weighted_scores.append(weighted_score)
            total_weight += final_weight

            # Determine impact level
            if high_matches > 0:
                impact = 'high'
            elif med_matches > 0:
                impact = 'medium'
            else:
                impact = 'low'

            relevant_articles.append({
                'title': title,
                'impact': impact,
                'sentiment_score': compound_score,
                'weighted_score': weighted_score,
                'weight': final_weight,
                'source_credibility': credibility_weight,
                'recency_weight': recency_weight,
                'keyword_matches': high_matches + med_matches + low_matches
            })

        if not relevant_articles:
            result = {
                'available': False,
                'sentiment': 'neutral',
                'impact': 'none',
                'time_to_release': None,
                'reason': 'No relevant economic/news articles found',
                'confidence': 0.0,
                'article_count': 0,
                'avg_sentiment_score': 0.0
            }
            _set_cache_result(cache_key, result)
            return result

        # Calculate weighted average sentiment score
        if total_weight > 0:
            avg_weighted_score = sum(weighted_scores) / total_weight
        else:
            avg_weighted_score = sum(weighted_scores) / len(weighted_scores)

        # Calculate confidence based on article count and score consistency
        article_count = len(relevant_articles)
        confidence = min(1.0, article_count / 10.0)  # More articles = higher confidence

        # Adjust confidence based on score variance
        if len(weighted_scores) > 1:
            variance = sum((x - avg_weighted_score) ** 2 for x in weighted_scores) / len(weighted_scores)
            confidence *= max(0.5, 1.0 - variance)  # Lower variance = higher confidence

        # Classify sentiment with adjusted thresholds based on confidence
        threshold = 0.03 if confidence > 0.7 else 0.05  # Stricter threshold for high confidence

        if avg_weighted_score >= threshold:
            sentiment = "bullish"
        elif avg_weighted_score <= -threshold:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Determine overall impact level
        impact_counts = {'high': 0, 'medium': 0, 'low': 0}
        for article in relevant_articles:
            impact_counts[article['impact']] += 1

        if impact_counts['high'] > 0:
            overall_impact = 'high'
        elif impact_counts['medium'] > 0:
            overall_impact = 'medium'
        else:
            overall_impact = 'low'

        # Calculate time to release (assume immediate for news)
        time_to_release = 0

        result = {
            'available': True,
            'sentiment': sentiment,
            'impact': overall_impact,
            'time_to_release': time_to_release,
            'reason': None,
            'confidence': round(confidence, 3),
            'article_count': article_count,
            'avg_sentiment_score': round(avg_weighted_score, 4),
            'impact_breakdown': impact_counts,
            'quality_score': round(total_weight / article_count, 2) if article_count > 0 else 0
        }

        # Cache the result
        _set_cache_result(cache_key, result)

        logger.info(f"News sentiment analysis complete: {sentiment} ({overall_impact} impact, {confidence:.1%} confidence, {article_count} articles)")
        return result

    except Exception as e:
        logger.error(f"News fetch error: {e}")
        # Return a structured response even on error
        return {
            'available': False,
            'sentiment': 'neutral',
            'impact': 'none',
            'time_to_release': None,
            'reason': f'API error: {str(e)}',
            'confidence': 0.0,
            'article_count': 0,
            'avg_sentiment_score': 0.0
        }

if __name__ == "__main__":
    # Test the news reader
    sentiment = get_latest_forex_news()
    print(f"Current market sentiment: {sentiment}")
