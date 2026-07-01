"""Web page source: scrapes a single URL and returns its clean text."""
import time

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)


@retry(**RETRY)
def scrape_website_text(url):
    """Fetches and extracts clean text from a given URL, retrying on transient request failures."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    for script_or_style in soup(['script', 'style']):
        script_or_style.decompose()
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = '\n'.join(chunk for chunk in chunks if chunk)
    return clean_text


class WebSource:
    """Fetches a single web page and wraps it as raw content."""

    def fetch(self, config):
        """Scrapes config['url'] and returns it as a single-item RawContent list."""
        url = config['url']
        text = scrape_website_text(url)
        if not text:
            return []
        return [{
            'source_type': 'web',
            'source_url': url,
            'text': text,
            'fetched_at': time.time(),
        }]
