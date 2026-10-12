"""
scryfall.py — card identity + every paper printing with its TCGplayer price.

Scryfall's `prices.usd` is TCGplayer's market price for the non-foil printing
(refreshed daily), so it doubles as the TCGplayer side of the comparison
without scraping tcgplayer.com.
"""

from datetime import date
from typing import Dict, List, Optional

from backend import cache
from backend.decklist import normalize_name
from backend.http import Throttle, client

API = "https://api.scryfall.com"
# Scryfall asks for 50–100 ms between requests.
_throttle = Throttle(0.1)

# Card identity never changes, so name lookups are cached for a long time.
NAME_CACHE_HOURS = 24 * 30


class ScryfallError(Exception):
    pass


async def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    await _throttle.wait()
    r = await client().get(url, params=params)
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise ScryfallError(f"Scryfall {r.status_code}: {r.text[:200]}")
    return r.json()


async def _post(url: str, body: dict) -> dict:
    await _throttle.wait()
    r = await client().post(url, json=body)
    if r.status_code >= 400:
        raise ScryfallError(f"Scryfall {r.status_code}: {r.text[:200]}")
    return r.json()


def _identity(card: dict) -> dict:
    faces = card.get("card_faces") or []
    type_line = card.get("type_line") or (faces[0].get("type_line", "") if faces else "")
    return {
        "name": card["name"],
        "oracle_id": card.get("oracle_id") or (faces[0].get("oracle_id") if faces else None),
        "type_line": type_line,
        "color_identity": card.get("color_identity") or [],
    }


def _name_keys(card: dict) -> List[str]:
    keys = {normalize_name(card["name"]), normalize_name(card["name"].replace("//", " "))}
    for face in card.get("card_faces") or []:
        if face.get("name"):
            keys.add(normalize_name(face["name"]))
    return list(keys)


async def resolve_names(names: List[str]) -> Dict[str, Optional[dict]]:
    """Map each input name to {name, oracle_id, type_line}, or None if unknown."""
    out: Dict[str, Optional[dict]] = {}
    pending: List[str] = []
    for n in names:
        hit = cache.get(f"name2:{normalize_name(n)}", NAME_CACHE_HOURS)
        if hit is not None:
            out[n] = hit
        else:
            pending.append(n)

    # Batch exact lookups, 75 per request (Scryfall's limit).
    for i in range(0, len(pending), 75):
        batch = pending[i:i + 75]
        data = await _post(f"{API}/cards/collection",
                           {"identifiers": [{"name": n.split("//")[0].strip()} for n in batch]})
        by_key = {}
        for card in data.get("data", []):
            for k in _name_keys(card):
                by_key[k] = _identity(card)
        for n in batch:
            ident = by_key.get(normalize_name(n))
            if ident:
                out[n] = ident

    # Anything still missing (typos, odd punctuation) gets a fuzzy lookup.
    for n in pending:
        if n in out:
            continue
        card = await _get(f"{API}/cards/named", {"fuzzy": n})
        out[n] = _identity(card) if card else None

    for n in pending:
        if out.get(n):
            cache.put(f"name2:{normalize_name(n)}", out[n])
    return out


async def quick_prices(names: List[str], cache_hours: float) -> Dict[str, Optional[float]]:
    """TCGplayer market price of each card's default printing, 75 cards per request.

    Cheaper than walking every printing (see `printings`), so it's used to
    budget-filter long suggestion lists; the Bargains tab does the full search.
    """
    out: Dict[str, Optional[float]] = {}
    pending = []
    for n in names:
        hit = cache.get(f"qp:{normalize_name(n)}", cache_hours)
        if hit is not None:
            out[n] = hit.get("usd")
        else:
            pending.append(n)
    for i in range(0, len(pending), 75):
        batch = pending[i:i + 75]
        data = await _post(f"{API}/cards/collection",
                           {"identifiers": [{"name": n.split("//")[0].strip()} for n in batch]})
        by_key = {}
        for card in data.get("data", []):
            usd = (card.get("prices") or {}).get("usd")
            for k in _name_keys(card):
                by_key[k] = float(usd) if usd else None
        for n in batch:
            out[n] = by_key.get(normalize_name(n))
            cache.put(f"qp:{normalize_name(n)}", {"usd": out[n]})
    return out


def _printing(card: dict) -> dict:
    usd = (card.get("prices") or {}).get("usd")
    image = (card.get("image_uris") or {}).get("small")
    if not image and card.get("card_faces"):
        image = (card["card_faces"][0].get("image_uris") or {}).get("small")
    return {
        "scryfall_id": card["id"],
        "set": card.get("set", "").upper(),
        "set_name": card.get("set_name", ""),
        "collector_number": card.get("collector_number", ""),
        "usd": float(usd) if usd else None,
        "tcgplayer_url": (card.get("purchase_uris") or {}).get("tcgplayer"),
        "scryfall_url": card.get("scryfall_uri"),
        "image": image,
    }


async def printings(oracle_id: str, cache_hours: float) -> List[dict]:
    """Every paper printing of a card (memorabilia like gold-bordered / Collectors' Edition excluded)."""
    key = f"prints:{oracle_id}"
    hit = cache.get(key, cache_hours)
    if hit is not None:
        return hit

    prints: List[dict] = []
    url = f"{API}/cards/search"
    params: Optional[dict] = {
        "q": f"oracleid:{oracle_id} game:paper -st:memorabilia",
        "unique": "prints",
        "order": "usd",
    }
    while url:
        page = await _get(url, params)
        if page is None:   # 404 = no matching printings
            break
        prints.extend(_printing(c) for c in page.get("data", []))
        url = page.get("next_page") if page.get("has_more") else None
        params = None   # next_page already carries the query string

    cache.put(key, prints)
    return prints


# Set types worth browsing for new cards (skips tokens, promos, art series, ...).
_SET_TYPES = {"expansion", "core", "commander", "draft_innovation", "masters", "funny"}


async def list_sets() -> List[dict]:
    """Paper sets newest first, for the New Sets picker."""
    hit = cache.get("sets", 24)
    if hit is not None:
        return hit
    data = await _get(f"{API}/sets") or {}
    today = date.today().isoformat()
    sets = [
        {"code": s["code"], "name": s["name"], "released_at": s.get("released_at", ""),
         "set_type": s.get("set_type", ""), "icon": s.get("icon_svg_uri")}
        for s in data.get("data", [])
        if s.get("set_type") in _SET_TYPES and not s.get("digital")
        and s.get("card_count", 0) > 0 and s.get("released_at", "9999") <= today
    ]
    sets.sort(key=lambda s: s["released_at"], reverse=True)
    cache.put("sets", sets)
    return sets


async def set_cards(code: str, cache_hours: float) -> List[dict]:
    """Every distinct non-basic card in a set, with color identity and TCGplayer market price."""
    key = f"setcards:{code.lower()}"
    hit = cache.get(key, cache_hours)
    if hit is not None:
        return hit
    cards: List[dict] = []
    url = f"{API}/cards/search"
    params: Optional[dict] = {"q": f"e:{code} game:paper -t:basic", "unique": "cards", "order": "set"}
    while url:
        page = await _get(url, params)
        if page is None:
            break
        for c in page.get("data", []):
            p = _printing(c)
            cards.append({
                "name": c["name"],
                "color_identity": c.get("color_identity") or [],
                "rarity": c.get("rarity", ""),
                "type_line": c.get("type_line") or ((c.get("card_faces") or [{}])[0].get("type_line", "")),
                "usd": p["usd"],
                "image": p["image"],
                "scryfall_url": p["scryfall_url"],
            })
        url = page.get("next_page") if page.get("has_more") else None
        params = None
    cache.put(key, cards)
    return cards
