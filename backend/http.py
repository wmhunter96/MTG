"""
http.py — shared outbound HTTP client.

Scryfall asks every client to send a descriptive User-Agent and Accept header
and to stay under ~10 requests/second, so its calls go through a throttle.
"""

import asyncio
import time

import httpx

USER_AGENT = "mtg-brewmaster/0.2 (+https://github.com/wmhunter96/MTG)"

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json;q=0.9,*/*;q=0.8"},
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
        )
    return _client


class Throttle:
    """Space calls at least `interval` seconds apart."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()
