"""
edhrec.py — "cards you might be missing" from EDHREC's commander pages.

EDHREC serves each commander page as JSON at
  https://json.edhrec.com/pages/commanders/<slug>[/<variant>].json
where <variant> is empty, "budget", "expensive", or a theme slug ("tokens",
"plus-1-plus-1-counters", ...). Every card list on the page is compared with
the user's deck and only the cards not already in it are returned.
"""

import re
import unicodedata
from typing import Iterable, List, Optional

from backend import cache
from backend.decklist import normalize_name
from backend.http import client

BASE = "https://json.edhrec.com/pages"
SITE = "https://edhrec.com"
CACHE_HOURS = 24


class EdhrecError(Exception):
    pass


def slugify(name: str) -> str:
    front = name.split("//")[0]
    s = unicodedata.normalize("NFKD", front).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s-]", "", s.lower())
    return re.sub(r"[\s-]+", "-", s).strip("-")


def commander_slug(commanders: List[str]) -> str:
    # Partner pairs live under both names joined, alphabetically.
    return "-".join(sorted(slugify(c) for c in commanders if c.strip()))


async def _fetch(path: str) -> Optional[dict]:
    r = await client().get(f"{BASE}/{path}.json")
    if r.status_code == 404 or r.status_code == 403:
        return None
    if r.status_code >= 400:
        raise EdhrecError(f"EDHREC {r.status_code}")
    return r.json()


async def commander_page(commanders: List[str], variant: str = "") -> dict:
    slug = commander_slug(commanders)
    if not slug:
        raise EdhrecError("No commander given")
    path = f"commanders/{slug}" + (f"/{slugify(variant)}" if variant.strip() else "")

    data = cache.get(f"edhrec:{path}", CACHE_HOURS)
    if data is None:
        data = await _fetch(path)
        # Alias pages (e.g. a reprinted commander's old name) just redirect.
        if data and data.get("redirect"):
            data = await _fetch(data["redirect"].strip("/"))
        if data is None:
            raise EdhrecError(f"EDHREC has no page for '{' + '.join(commanders)}' ({SITE}/{path})")
        cache.put(f"edhrec:{path}", data)
    return {"path": path, "data": data}


def _pct(part, whole) -> Optional[float]:
    try:
        return round(100.0 * float(part) / float(whole), 1) if whole else None
    except (TypeError, ValueError):
        return None


def suggestions(page: dict, deck_names: Iterable[str], min_inclusion_pct: float = 0) -> dict:
    data = page["data"]
    have = {normalize_name(n) for n in deck_names}
    container = (data.get("container") or {}).get("json_dict") or {}
    header = data.get("header") or (container.get("card") or {}).get("name") or ""

    lists = []
    for cl in container.get("cardlists") or []:
        cards = []
        for cv in cl.get("cardviews") or []:
            name = cv.get("name")
            if not name or normalize_name(name) in have:
                continue
            inclusion = _pct(cv.get("num_decks", cv.get("inclusion")), cv.get("potential_decks"))
            if min_inclusion_pct and inclusion is not None and inclusion < min_inclusion_pct:
                continue
            synergy = cv.get("synergy")
            cards.append({
                "name": name,
                "synergy_pct": round(100.0 * synergy) if isinstance(synergy, (int, float)) else None,
                "inclusion_pct": inclusion,
                "num_decks": cv.get("num_decks", cv.get("inclusion")),
                "url": f"{SITE}{cv['url']}" if cv.get("url") else f"{SITE}/cards/{slugify(name)}",
            })
        if cards:
            lists.append({"header": cl.get("header", ""), "tag": cl.get("tag", ""), "cards": cards})

    return {
        "commander": header,
        "url": f"{SITE}/{page['path']}",
        "lists": lists,
        "missing_count": len({normalize_name(c["name"]) for l in lists for c in l["cards"]}),
    }
