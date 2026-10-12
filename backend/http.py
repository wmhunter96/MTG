"""
http.py — shared outbound HTTP client.

Scryfall asks every client to send a descriptive User-Agent and Accept header
and to stay under ~10 requests/second, so its calls go through a throttle.
Archidekt rate-limits harder (HTTP 429), so get_patiently() backs off and retries.
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


_sleep = asyncio.sleep   # swapped out in tests


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return float(r.headers.get("Retry-After", ""))
    except ValueError:
        return None


async def get_patiently(url: str, throttle: Throttle | None = None, retries: int = 4,
                        max_wait: float = 30.0) -> httpx.Response:
    """GET that waits out 429 / 503 (honoring Retry-After, else 2, 4, 8, 16 s) before giving up."""
    for attempt in range(retries + 1):
        if throttle:
            await throttle.wait()
        r = await client().get(url)
        if r.status_code not in (429, 503) or attempt == retries:
            return r
        await _sleep(min(max_wait, _retry_after(r) or 2.0 ** (attempt + 1)))
    return r
