"""Stack Exchange source: searches a site (default stackoverflow) for keywords via the Stack Exchange API."""
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from secret_manager import get_secret

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)

SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"


@retry(**RETRY)
def fetch_from_stackexchange(site, keywords):
    """
    Searches `site` (e.g. "stackoverflow", "superuser") for questions matching
    keywords (OR'd together) from the past week and returns their combined
    title/body text. Works without an API key at a lower (shared) rate limit;
    set the STACKEXCHANGE_KEY secret to raise the quota.
    """
    params = {
        'q': ' '.join(keywords),
        'site': site,
        'sort': 'creation',
        'order': 'desc',
        'fromdate': int(time.time()) - 7 * 24 * 3600,
        'filter': 'withbody',
    }
    key = get_secret("STACKEXCHANGE_KEY")
    if key:
        params['key'] = key

    response = requests.get(SEARCH_URL, params=params, timeout=15)
    response.raise_for_status()
    items = response.json().get('items', [])

    combined_text = ""
    for item in items:
        title = item.get('title', '')
        body = item.get('body', '')
        combined_text += title + "\n" + body + "\n\n"

    return combined_text


class StackExchangeSource:
    """Fetches recent matching questions from a Stack Exchange site and wraps them as raw content."""

    def fetch(self, config):
        """Searches config['site'] for config['keywords'] and returns a single-item RawContent list."""
        site = config.get('site', 'stackoverflow')
        keywords = config['keywords']
        text = fetch_from_stackexchange(site, keywords)
        if not text:
            return []
        return [{
            'source_type': 'stackexchange',
            'source_url': f"https://{site}.com/search?q={'+'.join(keywords)}",
            'text': text,
            'fetched_at': time.time(),
        }]
