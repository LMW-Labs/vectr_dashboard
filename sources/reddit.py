"""Reddit source: searches a subreddit for keywords and returns matching posts."""
import logging
import time

import praw
from tenacity import retry, stop_after_attempt, wait_exponential

from secret_manager import get_secret

logger = logging.getLogger(__name__)

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)


@retry(**RETRY)
def fetch_from_reddit_api(subreddit, keywords):
    """
    Searches a subreddit for keywords and returns the content of new posts, retrying on transient API errors.
    """
    reddit = praw.Reddit(
        client_id=get_secret("REDDIT_CLIENT_ID"),
        client_secret=get_secret("REDDIT_CLIENT_SECRET"),
        user_agent=get_secret("REDDIT_USER_AGENT"),
    )

    query = ' OR '.join(f'"{keyword}"' for keyword in keywords)
    combined_text = ""
    for submission in reddit.subreddit(subreddit).search(query, sort='new', time_filter='week'):
        combined_text += submission.title + "\n" + submission.selftext + "\n\n"

    if not combined_text:
        logger.info(f"No new posts found in r/{subreddit} for the given keywords.")

    return combined_text


class RedditSource:
    """Fetches recent matching posts from a subreddit and wraps them as raw content."""

    def fetch(self, config):
        """Searches config['subreddit'] for config['keywords'] and returns a single-item RawContent list."""
        subreddit = config['subreddit']
        keywords = config['keywords']
        text = fetch_from_reddit_api(subreddit, keywords)
        if not text:
            return []
        return [{
            'source_type': 'reddit',
            'source_url': f"reddit://r/{subreddit}?q={','.join(keywords)}",
            'text': text,
            'subreddit': subreddit,
            'fetched_at': time.time(),
        }]
