"""
cardkingdom.py — Card Kingdom's public retail price list.

CK publishes its whole catalogue (NM retail price + in-stock quantity per
printing, tagged with the Scryfall printing id) as one JSON file. It's
downloaded to /config/cache, refreshed every `cache_hours`, and indexed in
memory, so a lookup never hits cardkingdom.com per card.
"""

import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import CACHE_DIR
from backend.decklist import normalize_name
from backend.http import client

PRICELIST_URL = "https://api.cardkingdom.com/api/v2/pricelist"
SITE = "https://www.cardkingdom.com"

# Rows with no Scryfall id fall back to name matching; skip non-tournament
# printings there the same way the Scryfall side excludes memorabilia.
_EXCLUDED_EDITIONS = ("collectors", "world championship", "30th anniversary", "oversized", "art series")


class CardKingdomError(Exception):
    pass


def _path() -> Path:
    return Path(CACHE_DIR) / "ck_pricelist.json"


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _row(raw: dict) -> Optional[dict]:
    if _truthy(raw.get("is_foil")):
        return None
    try:
        price = float(raw.get("price_retail") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    url = raw.get("url") or ""
    return {
        "scryfall_id": raw.get("scryfall_id") or None,
        "name": raw.get("name", ""),
        "edition": raw.get("edition", ""),
        "variation": raw.get("variation") or "",
        "price": price,
        "qty": int(raw.get("qty_retail") or 0),
        "url": url if url.startswith("http") else f"{SITE}/{url.lstrip('/')}",
    }


class PriceList:
    def __init__(self, rows: List[dict], fetched_at: float):
        self.fetched_at = fetched_at
        self.by_scryfall: Dict[str, List[dict]] = defaultdict(list)
        self.by_name: Dict[str, List[dict]] = defaultdict(list)
        for r in rows:
            if r["scryfall_id"]:
                self.by_scryfall[r["scryfall_id"]].append(r)
            self.by_name[normalize_name(r["name"])].append(r)

    def offers(self, name: str, scryfall_ids: List[str]) -> List[dict]:
        """All non-foil CK offers for a card, matched by printing id (or name as a fallback)."""
        found = [r for sid in scryfall_ids for r in self.by_scryfall.get(sid, [])]
        seen = {id(r) for r in found}
        for r in self.by_name.get(normalize_name(name), []):
            if id(r) in seen:
                continue
            # Name-only rows: only trust ones without a Scryfall id, otherwise
            # they're a printing Scryfall excluded (e.g. memorabilia).
            if r["scryfall_id"] is None and not any(x in r["edition"].lower() for x in _EXCLUDED_EDITIONS):
                found.append(r)
        return found


_list: Optional[PriceList] = None
_lock = asyncio.Lock()


def parse_pricelist(payload: dict, fetched_at: float) -> PriceList:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    rows = [r for r in (_row(x) for x in data or []) if r]
    return PriceList(rows, fetched_at)


async def get_pricelist(cache_hours: float, force: bool = False) -> PriceList:
    global _list
    async with _lock:
        path = _path()
        fresh = path.exists() and time.time() - path.stat().st_mtime < cache_hours * 3600
        if _list is not None and fresh and not force:
            return _list
        if not fresh or force:
            r = await client().get(PRICELIST_URL)
            if r.status_code >= 400:
                if path.exists():   # serve stale rather than fail
                    _list = _list or await asyncio.to_thread(_load, path)
                    return _list
                raise CardKingdomError(f"Card Kingdom price list {r.status_code}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        _list = await asyncio.to_thread(_load, path)
        return _list


def _load(path: Path) -> PriceList:
    with open(path) as f:
        return parse_pricelist(json.load(f), path.stat().st_mtime)
