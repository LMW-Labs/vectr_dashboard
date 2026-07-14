"""Registry of pluggable content sources, keyed by source_type."""
from .hackernews import HackerNewsSource
from .quora import QuoraSource
from .reddit import RedditSource
from .stackexchange import StackExchangeSource
from .web import WebSource
from .x import XSource

SOURCES = {
    'web': WebSource,
    'reddit': RedditSource,
    'x': XSource,
    'hackernews': HackerNewsSource,
    'quora': QuoraSource,
    'stackexchange': StackExchangeSource,
}
