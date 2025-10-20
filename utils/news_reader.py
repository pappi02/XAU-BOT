import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from config import NEWS_API_KEY
<<<<<<< HEAD
from datetime import datetime, timedelta
=======
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

<<<<<<< HEAD
# Cache for news data to avoid rate limits
news_cache = {
    'data': None,
    'timestamp': None
}
CACHE_DURATION_MINUTES = 30  # Cache for 30 minutes

def get_latest_forex_news():
    """
    Fetch latest forex-related news from NewsAPI and analyze sentiment using VADER.
    Only considers news from the last 24 hours to focus on current market-moving events.
    Uses caching to avoid rate limits (30-minute cache duration).

    Returns:
        dict: Dictionary containing sentiment analysis and availability info
            - 'sentiment': str ('bullish', 'bearish', or 'neutral')
            - 'available': bool (True if recent news found, False otherwise)
            - 'article_count': int (number of recent articles found)
            - 'avg_sentiment_score': float (average compound sentiment score)
    """
    # Check cache first
    now = datetime.now()
    if news_cache['timestamp'] and news_cache['data']:
        cache_age = (now - news_cache['timestamp']).total_seconds() / 60
        if cache_age < CACHE_DURATION_MINUTES:
            print(f"Using cached news data (age: {cache_age:.1f} minutes)")
            return news_cache['data']

    try:
        # Calculate date 24 hours ago for recent news only
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

=======
def get_latest_forex_news():
    """
    Fetch latest forex-related news from NewsAPI and analyze sentiment using VADER.

    Returns:
        str: Sentiment analysis result ('bullish', 'bearish', or 'neutral')
    """
    try:
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "gold OR USD OR forex OR XAU",
            "apiKey": NEWS_API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
<<<<<<< HEAD
            "pageSize": 30,  # Get last 30 articles for better analysis
            "from": yesterday  # Only news from last 24 hours
=======
            "pageSize": 30  # Get last 30 articles for better analysis
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        articles = response.json().get("articles", [])

        if not articles:
<<<<<<< HEAD
            result = {
                'sentiment': 'neutral',
                'available': False,
                'article_count': 0,
                'avg_sentiment_score': 0.0,
                'reason': 'No recent news articles found'
            }
        else:
            # Analyze sentiment using VADER
            compound_scores = []

            for article in articles:
                title = article.get("title", "")
                description = article.get("description", "") if article.get("description") else ""

                # Combine title and description for analysis
                text = title + ". " + description

                # Get sentiment scores
                sentiment = analyzer.polarity_scores(text)
                compound_scores.append(sentiment['compound'])

            # Calculate average compound score
            avg_compound = sum(compound_scores) / len(compound_scores) if compound_scores else 0

            # Classify sentiment based on average compound score
            if avg_compound >= 0.05:
                sentiment_result = "bullish"
            elif avg_compound <= -0.05:
                sentiment_result = "bearish"
            else:
                sentiment_result = "neutral"

            result = {
                'sentiment': sentiment_result,
                'available': True,
                'article_count': len(articles),
                'avg_sentiment_score': avg_compound,
                'reason': f'Found {len(articles)} recent articles with {sentiment_result} sentiment'
            }

        # Update cache with successful fetch
        news_cache['data'] = result
        news_cache['timestamp'] = now
        print(f"Updated news cache with fresh data")
        return result

    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            # Rate limit exceeded, use cached data if available
            if news_cache['data']:
                print(f"Rate limit exceeded, using cached data (age: {cache_age:.1f} minutes)")
                return news_cache['data']
            else:
                print("Rate limit exceeded and no cached data available")
                return {
                    'sentiment': 'neutral',
                    'available': False,
                    'article_count': 0,
                    'avg_sentiment_score': 0.0,
                    'reason': 'Rate limit exceeded and no cached data available'
                }
        else:
            print(f"HTTP error: {e}")
            # Use cached data if available
            if news_cache['data']:
                print(f"HTTP error, using cached data (age: {cache_age:.1f} minutes)")
                return news_cache['data']
            else:
                return {
                    'sentiment': 'neutral',
                    'available': False,
                    'article_count': 0,
                    'avg_sentiment_score': 0.0,
                    'reason': f'HTTP error: {str(e)}'
                }
    except Exception as e:
        print(f"News fetch error: {e}")
        # Use cached data if available
        if news_cache['data']:
            print(f"General error, using cached data (age: {cache_age:.1f} minutes)")
            return news_cache['data']
        else:
            return {
                'sentiment': 'neutral',
                'available': False,
                'article_count': 0,
                'avg_sentiment_score': 0.0,
                'reason': f'Error fetching news: {str(e)}'
            }
=======
            return "neutral"

        # Analyze sentiment using VADER
        compound_scores = []

        for article in articles:
            title = article.get("title", "")
            description = article.get("description", "") if article.get("description") else ""

            # Combine title and description for analysis
            text = title + ". " + description

            # Get sentiment scores
            sentiment = analyzer.polarity_scores(text)
            compound_scores.append(sentiment['compound'])

        # Calculate average compound score
        avg_compound = sum(compound_scores) / len(compound_scores) if compound_scores else 0

        # Classify sentiment based on average compound score
        if avg_compound >= 0.05:
            return "bullish"
        elif avg_compound <= -0.05:
            return "bearish"
        else:
            return "neutral"

    except Exception as e:
        print(f"News fetch error: {e}")
        return "neutral"
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

if __name__ == "__main__":
    # Test the news reader
    sentiment = get_latest_forex_news()
    print(f"Current market sentiment: {sentiment}")
