import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from config import NEWS_API_KEY

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

def get_latest_forex_news():
    """
    Fetch latest forex-related news from NewsAPI and analyze sentiment using VADER.

    Returns:
        str: Sentiment analysis result ('bullish', 'bearish', or 'neutral')
    """
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "gold OR USD OR forex OR XAU",
            "apiKey": NEWS_API_KEY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 30  # Get last 30 articles for better analysis
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        articles = response.json().get("articles", [])

        if not articles:
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

if __name__ == "__main__":
    # Test the news reader
    sentiment = get_latest_forex_news()
    print(f"Current market sentiment: {sentiment}")
