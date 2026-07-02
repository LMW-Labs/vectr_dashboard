"""X (Twitter) source: searches recent tweets for keywords."""
import logging
import time

import tweepy
from tenacity import retry, stop_after_attempt, wait_exponential

from secret_manager import get_secret

logger = logging.getLogger(__name__)

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)


@retry(**RETRY)
def fetch_from_x_api(keywords):
    """
    Searches for recent tweets using the X API v2 and returns their text, retrying on transient API errors.
    """
    bearer_token = get_secret("X_BEARER_TOKEN")

    if not bearer_token:
        logger.error("X_BEARER_TOKEN not found in Secret Manager.")
        return None

    client = tweepy.Client(bearer_token)
    query = f"({' OR '.join(keywords)}) -is:retweet lang:en"
    response = client.search_recent_tweets(query=query, max_results=100)

    tweets = response.data
    if not tweets:
        logger.info("No tweets found for the given keywords.")
        return ""

    combined_text = "\n".join(tweet.text for tweet in tweets)
    return combined_text


class XSource:
    """Fetches recent matching tweets and wraps them as raw content."""

    def fetch(self, config):
        """Searches for config['keywords'] and returns a single-item RawContent list."""
        keywords = config['keywords']
        text = fetch_from_x_api(keywords)
        if not text:
            return []
        return [{
            'source_type': 'x',
            'source_url': f"x://search?q={','.join(keywords)}",
            'text': text,
            'fetched_at': time.time(),
        }]
