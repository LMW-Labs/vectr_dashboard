"""Hacker News source: searches stories and comments for keywords via the HN Algolia Search API."""
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)

SEARCH_URL = "https://hn.algolia.com/api/v1/search"


@retry(**RETRY)
def fetch_from_hackernews(keywords):
    """
    Searches HN stories and comments for keywords (OR'd together) from the past
    week, sorted by recency, and returns their combined title/text.
    """
    query = ' '.join(keywords)
    params = {
        'query': query,
        'tags': '(story,comment)',
        'numericFilters': f'created_at_i>{int(time.time()) - 7 * 24 * 3600}',
    }
    response = requests.get(SEARCH_URL, params=params, timeout=15)
    response.raise_for_status()
    hits = response.json().get('hits', [])

    combined_text = ""
    for hit in hits:
        title = hit.get('title') or hit.get('story_title') or ''
        body = hit.get('comment_text') or hit.get('story_text') or ''
        if title or body:
            combined_text += title + "\n" + body + "\n\n"

    return combined_text


class HackerNewsSource:
    """Fetches recent matching HN stories/comments and wraps them as raw content."""

    def fetch(self, config):
        """Searches config['keywords'] and returns a single-item RawContent list."""
        keywords = config['keywords']
        text = fetch_from_hackernews(keywords)
        if not text:
            return []
        return [{
            'source_type': 'hackernews',
            'source_url': f"hn://search?q={','.join(keywords)}",
            'text': text,
            'fetched_at': time.time(),
        }]
