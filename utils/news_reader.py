"""News sentiment with a stated contract (Phase 10, audit H-05).

Three defects lived in this one module, and they compounded:

1. **The return type changed but the callers did not.** This returns a `dict`;
   every consumer compared it against a string (`news_sentiment == "bullish"`).
   A dict is never equal to a string, so **every news check in the system
   silently evaluated false**, at all four sites. The feature was dead while
   appearing to work -- the worst failure mode, because nobody investigates a
   check that never fires.

2. **`requests.get` had no timeout, inside the trading loop.** A hung socket
   blocked the loop indefinitely: no position managed, no stop checked, no
   heartbeat. The default is to wait forever.

3. **`cache_age` was referenced in three error handlers but assigned only
   inside an `if`.** Every one of those paths raised `UnboundLocalError` -- so
   the rate-limit fallback, the one designed to keep working when NewsAPI says
   no, crashed instead.

The fix for (1) is not to change the return type back. It is to give the module
a stated contract and a normaliser, so a caller cannot get this wrong silently:
`sentiment_of()` accepts either shape and returns a plain string.

On whether any of this is worth keeping, see `docs/STRATEGY-HYPOTHESIS.md`:
averaging headline tone over `"gold OR USD OR forex OR XAU"` is ambiguous by
construction, because USD-bullish and gold-bullish are *opposite* signals for
the same trade. It is **off by default** until it demonstrates out-of-sample
value.
"""

import threading
from datetime import datetime, timedelta

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config import NEWS_API_KEY

analyzer = SentimentIntensityAnalyzer()

# (connect timeout, read timeout). Without these the loop can hang forever.
REQUEST_TIMEOUT = (3, 5)

CACHE_DURATION_MINUTES = 30
STALE_TOLERANCE_MINUTES = 240   # serve stale news rather than block the loop

_cache_lock = threading.Lock()
news_cache = {"data": None, "timestamp": None}


def unavailable(reason):
    """The canonical 'no usable sentiment' result."""
    return {
        "sentiment": "neutral",
        "available": False,
        "article_count": 0,
        "avg_sentiment_score": 0.0,
        "reason": reason,
    }


def sentiment_of(value):
    """Normalise either shape to a plain sentiment string.

    THE H-05 FIX. Callers used to compare the dict directly against a string,
    which is always False. Passing whatever you have through here makes that
    impossible:

        if sentiment_of(news) == "bearish": ...

    Accepts a dict, a bare string, or None.
    """
    if value is None:
        return "neutral"
    if isinstance(value, dict):
        return str(value.get("sentiment", "neutral"))
    return str(value)


def score_of(value):
    """The average compound score, or 0.0 when unavailable."""
    if isinstance(value, dict):
        try:
            return float(value.get("avg_sentiment_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def is_available(value):
    """True only when a real fetch produced articles."""
    return bool(value.get("available")) if isinstance(value, dict) else False


def _cache_age_minutes(now=None):
    """Age of the cached entry in minutes, or None when there is none.

    Defect 3: `cache_age` used to be computed only inside the freshness check,
    then referenced in three error handlers -- each of which raised
    UnboundLocalError instead of serving the cache it was written to serve.
    """
    with _cache_lock:
        stamp = news_cache["timestamp"]
    if stamp is None:
        return None
    return ((now or datetime.now()) - stamp).total_seconds() / 60.0


def _serve_cache(reason, now=None):
    """Return cached data if it is within the stale tolerance."""
    age = _cache_age_minutes(now)
    with _cache_lock:
        data = news_cache["data"]
    if data is None or age is None:
        return unavailable(reason + " (no cached data)")
    if age > STALE_TOLERANCE_MINUTES:
        return unavailable("%s (cache is %.0f minutes old)" % (reason, age))
    result = dict(data)
    result["reason"] = "%s -- serving cache (%.0f minutes old)" % (reason, age)
    return result


def get_latest_forex_news(force=False, now=None):
    """Fetch and score recent gold/USD headlines.

    Returns:
        dict with 'sentiment', 'available', 'article_count',
        'avg_sentiment_score' and 'reason'. **Never** compare this against a
        string -- use ``sentiment_of()``.
    """
    now = now or datetime.now()

    if not NEWS_API_KEY:
        return unavailable("NEWS_API_KEY is not set -- news sentiment disabled")

    age = _cache_age_minutes(now)
    if not force and age is not None and age < CACHE_DURATION_MINUTES:
        with _cache_lock:
            return dict(news_cache["data"])

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "gold OR USD OR forex OR XAU",
                "apiKey": NEWS_API_KEY,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 30,
                "from": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
            },
            timeout=REQUEST_TIMEOUT,      # defect 2
        )
        response.raise_for_status()
        articles = response.json().get("articles", []) or []
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        return _serve_cache("rate limited" if status == 429
                            else "HTTP error %s" % status, now)
    except requests.exceptions.RequestException as exc:
        return _serve_cache("network error: %s" % exc, now)
    except ValueError as exc:
        return _serve_cache("malformed response: %s" % exc, now)

    if not articles:
        result = unavailable("no recent articles found")
    else:
        scores = []
        for article in articles:
            title = article.get("title") or ""
            description = article.get("description") or ""
            scores.append(analyzer.polarity_scores(
                "%s. %s" % (title, description))["compound"])

        average = sum(scores) / len(scores) if scores else 0.0
        if average >= 0.05:
            label = "bullish"
        elif average <= -0.05:
            label = "bearish"
        else:
            label = "neutral"

        result = {
            "sentiment": label,
            "available": True,
            "article_count": len(articles),
            "avg_sentiment_score": average,
            "reason": "%d recent articles, %s" % (len(articles), label),
        }

    with _cache_lock:
        news_cache["data"] = result
        news_cache["timestamp"] = now
    return result


class NewsRefresher:
    """Background refresher, so the trading loop never waits on a socket.

    Even with a timeout, up to 8 seconds of the loop can be spent waiting on
    NewsAPI -- during which no position is managed and no stop is checked. The
    loop should read a cache; only this thread should ever block.
    """

    def __init__(self, interval_seconds=CACHE_DURATION_MINUTES * 60):
        self.interval = interval_seconds
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="news-refresher")
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                get_latest_forex_news(force=True)
            except Exception:
                pass          # a refresher that dies stops refreshing
            self._stop.wait(self.interval)

    @staticmethod
    def current():
        """The cached sentiment, without ever making a network call."""
        with _cache_lock:
            data = news_cache["data"]
        return dict(data) if data else unavailable("no news fetched yet")
