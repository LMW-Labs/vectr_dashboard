"""Protocol and shared types for pluggable content sources."""
from typing import List, Protocol, TypedDict


class RawContent(TypedDict):
    source_type: str
    source_url: str
    text: str
    fetched_at: float


class Source(Protocol):
    def fetch(self, config: dict) -> List[RawContent]: ...
