"""
collection.py — your card collection plus a library of saved decks, so a deck
check can say "you own this card, but it's sleeved up in your Built X deck".

Both live in /config/collection.json next to settings.yaml:

  {"collection": {"source", "imported_at", "cards": {key: {"name", "qty"}}},
   "decks": [{"id", "name", "url", "commanders", "decklist", "status", "updated_at"}]}

The collection is everything you own, including cards sitting in decks
(the way Archidekt's collection tracker counts them). Built decks hold their
cards; Brewing decks don't, since they're still on paper.

Archidekt has no official API. The collection and deck-list endpoints below
are the ones its own site uses and can change without notice, so a pasted CSV
export works as a fallback.
"""

import csv
import io
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from backend import importer
from backend.config import CONFIG_PATH
from backend.decklist import normalize_name, parse_decklist
from backend.http import get_patiently


class CollectionError(Exception):
    pass


class RateLimited(CollectionError):
    pass


_lock = threading.Lock()
MAX_PAGES = 400

_BASICS = {normalize_name(n) for n in (
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes",
)}

_COLLECTION_RE = re.compile(r"archidekt\.com/(?:api/)?collection/(?:v2/)?(\d+)")
_USER_RE = re.compile(r"archidekt\.com/(?:u|user|users|profile)/([^/?#]+)")


def _path() -> Path:
    return Path(CONFIG_PATH).parent / "collection.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> dict:
    path = _path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            data = {}
    data.setdefault("collection", {"source": "", "imported_at": None, "cards": {}})
    data.setdefault("decks", [])
    return data


def save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def is_basic(name: str) -> bool:
    return normalize_name(name) in _BASICS


def _add(cards: Dict[str, dict], name: str, qty: int) -> None:
    name = name.strip()
    if not name or qty <= 0:
        return
    key = normalize_name(name)
    if key in cards:
        cards[key]["qty"] += qty
    else:
        cards[key] = {"name": name, "qty": qty}


# ---------------------------------------------------------------------------
# Collection sources
# ---------------------------------------------------------------------------

_QTY_COLS = ("quantity", "qty", "count", "amount")
_NAME_COLS = ("name", "card name", "card")


def parse_collection_text(text: str) -> Dict[str, dict]:
    """A CSV export (Archidekt, Moxfield, Deckbox… anything with quantity + name
    columns) or a plain "1 Sol Ring" list."""
    cards: Dict[str, dict] = {}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return cards
    try:
        dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
    except csv.Error:
        dialect = None
    if dialect:
        header = [h.strip().strip('"').lower() for h in next(csv.reader([lines[0]], dialect))]
        qty_i = next((header.index(c) for c in _QTY_COLS if c in header), None)
        name_i = next((header.index(c) for c in _NAME_COLS if c in header), None)
        if name_i is not None:
            for row in csv.reader(io.StringIO("\n".join(lines[1:])), dialect):
                if len(row) <= name_i:
                    continue
                try:
                    qty = int(float(row[qty_i])) if qty_i is not None and row[qty_i].strip() else 1
                except ValueError:
                    continue
                _add(cards, row[name_i], qty)
            return cards
    for c in parse_decklist(text).cards:
        _add(cards, c.name, c.qty)
    return cards


def collection_id(ref: str) -> Optional[str]:
    ref = ref.strip()
    if m := _COLLECTION_RE.search(ref):
        return m.group(1)
    return ref if ref.isdigit() else None


def parse_archidekt_collection(data) -> Tuple[List[Tuple[int, str]], Optional[str], Optional[int]]:
    """One page of Archidekt's collection endpoint → (cards, next url, total count)."""
    if isinstance(data, list):
        results, nxt, count = data, None, None
    else:
        results = data.get("results") or data.get("cards") or []
        nxt, count = data.get("next"), data.get("count")
    out = []
    for entry in results:
        card = entry.get("card") or {}
        name = (card.get("oracleCard") or {}).get("name") or card.get("name") or entry.get("name")
        if name:
            out.append((int(entry.get("quantity") or 1), name))
    return out, nxt, count


async def _get(url: str, what: str):
    r = await get_patiently(url, importer.archidekt_throttle)
    if r.status_code == 429:
        raise RateLimited("Archidekt is asking us to slow down. Give it a minute and try again.")
    if r.status_code == 404:
        raise CollectionError(f"Archidekt couldn't find that {what}. Is it public?")
    if r.status_code in (401, 403):
        raise CollectionError(f"Archidekt says that {what} is private. Make it public, or export it as CSV and paste it instead.")
    if r.status_code >= 400:
        raise CollectionError(f"Archidekt refused the request ({r.status_code}). Export it as CSV and paste it instead.")
    try:
        return r.json()
    except ValueError:
        raise CollectionError("Archidekt didn't send data back. Export it as CSV and paste it instead.")


async def fetch_archidekt_collection(ref: str) -> Dict[str, dict]:
    cid = collection_id(ref)
    if not cid:
        raise CollectionError("That doesn't look like an Archidekt collection link (archidekt.com/collection/v2/12345).")
    cards: Dict[str, dict] = {}
    url: Optional[str] = f"https://archidekt.com/api/collection/{cid}/?page=1&pageSize=100"
    page, seen = 1, 0
    while url and page <= MAX_PAGES:
        rows, nxt, count = parse_archidekt_collection(await _get(url, "collection"))
        for qty, name in rows:
            _add(cards, name, qty)
        seen += len(rows)
        if not rows or (count is not None and seen >= count):
            break
        page += 1
        if nxt:
            url = nxt
        elif len(rows) >= 100:
            url = f"https://archidekt.com/api/collection/{cid}/?page={page}&pageSize=100"
        else:
            url = None
    if not cards:
        raise CollectionError("That collection came back empty.")
    return cards


def import_collection(cards: Dict[str, dict], source: str) -> dict:
    with _lock:
        data = load()
        data["collection"] = {"source": source, "imported_at": _now(), "cards": cards}
        save(data)
    return summary()


# ---------------------------------------------------------------------------
# Deck library
# ---------------------------------------------------------------------------

def username(ref: str) -> str:
    ref = ref.strip()
    if m := _USER_RE.search(ref):
        return m.group(1)
    return ref.strip("/@ ")


async def fetch_archidekt_user_decks(user: str, known: Optional[Dict[str, str]] = None,
                                     on_deck: Optional[Callable[[dict], None]] = None) -> Tuple[List[dict], int]:
    """Every public deck an Archidekt user owns, as library entries.

    `known` maps library ids to the Archidekt updatedAt they were fetched at;
    unchanged decks are skipped (fewer calls, fewer 429s). `on_deck` is called
    with each deck as it arrives, so a rate limit halfway keeps what came in.
    Returns (fetched decks, unchanged count).
    """
    user = username(user)
    if not user or "/" in user:
        raise CollectionError("Enter an Archidekt username (or your profile link).")
    known = known or {}
    listed, url, pages = [], f"https://archidekt.com/api/decks/cards/?owner={user}&ownerexact=true&pageSize=50", 0
    while url and pages < 20:
        body = await _get(url, "user")
        listed += body.get("results") or []
        url, pages = body.get("next"), pages + 1
    if not listed:
        raise CollectionError(f"Archidekt has no public decks for {user}.")
    decks, unchanged = [], 0
    todo = [d for d in listed if d.get("id") is not None]
    for d in todo:
        deck_id, updated = d["id"], d.get("updatedAt") or ""
        if updated and known.get(f"archidekt-{deck_id}") == updated:
            unchanged += 1
            continue
        try:
            data = await _get(f"https://archidekt.com/api/decks/{deck_id}/", "deck")
        except RateLimited:
            left = len(todo) - len(decks) - unchanged
            raise RateLimited(f"Archidekt asked us to slow down with {left} deck{'s' if left != 1 else ''} to go. "
                              f"The {len(decks)} new or changed ones so far are saved; press Import decks again in a minute for the rest.")
        name, commanders, cards = importer.parse_archidekt(data)
        if not cards and not commanders:
            continue
        deck = {
            "id": f"archidekt-{deck_id}",
            "name": name or d.get("name") or f"Deck {deck_id}",
            "url": f"https://archidekt.com/decks/{deck_id}",
            "commanders": [n for _, n in commanders],
            "decklist": importer.to_text(name, commanders, cards),
            "archidekt_updated": updated,
        }
        decks.append(deck)
        if on_deck:
            on_deck(deck)
    return decks, unchanged


def archidekt_versions() -> Dict[str, str]:
    return {d["id"]: d.get("archidekt_updated", "") for d in load()["decks"] if d.get("archidekt_updated")}


def upsert_decks(decks: List[dict], default_status: str = "built", keep_status: bool = True) -> dict:
    """Add or refresh decks. With keep_status, a deck already in the library keeps its
    Built/Brewing status (re-importing doesn't undo your choices)."""
    with _lock:
        data = load()
        by_id = {d["id"]: d for d in data["decks"]}
        for d in decks:
            old = by_id.get(d["id"])
            entry = {**(old or {}), **d, "updated_at": _now()}
            kept = (old or {}).get("status") if keep_status else None
            entry["status"] = kept or d.get("status") or default_status
            if old:
                data["decks"][data["decks"].index(old)] = entry
            else:
                data["decks"].append(entry)
            by_id[d["id"]] = entry
        save(data)
    return summary()


def new_deck(name: str, decklist: str, commanders: List[str], status: str, url: str = "") -> dict:
    deck = parse_decklist(decklist)
    if not deck.cards:
        raise CollectionError("No cards found in that list.")
    commanders = [c for c in commanders if c.strip()] or deck.commanders
    return {"id": uuid.uuid4().hex[:12], "name": name.strip() or " + ".join(commanders) or "Untitled deck",
            "url": url, "commanders": commanders, "decklist": decklist,
            "status": status if status in ("built", "brewing") else "built"}


def update_deck(deck_id: str, status: Optional[str] = None, name: Optional[str] = None) -> dict:
    with _lock:
        data = load()
        deck = next((d for d in data["decks"] if d["id"] == deck_id), None)
        if not deck:
            raise CollectionError("That deck isn't in your library.")
        if status in ("built", "brewing"):
            deck["status"] = status
        if name and name.strip():
            deck["name"] = name.strip()
        save(data)
    return summary()


def delete_deck(deck_id: str) -> dict:
    with _lock:
        data = load()
        data["decks"] = [d for d in data["decks"] if d["id"] != deck_id]
        save(data)
    return summary()


# ---------------------------------------------------------------------------
# Who's using what
# ---------------------------------------------------------------------------

def _deck_cards(deck: dict) -> Dict[str, Tuple[str, int]]:
    out: Dict[str, Tuple[str, int]] = {}
    parsed = parse_decklist(deck.get("decklist", ""))
    names = [(c.name, c.qty) for c in parsed.cards]
    have = {normalize_name(n) for n, _ in names}
    names += [(c, 1) for c in deck.get("commanders") or [] if normalize_name(c) not in have]
    for name, qty in names:
        key = normalize_name(name)
        prev = out.get(key, (name, 0))
        out[key] = (prev[0], prev[1] + qty)
    return out


def _same_commanders(a: List[str], b: List[str]) -> bool:
    sa, sb = {normalize_name(x) for x in a if x.strip()}, {normalize_name(x) for x in b if x.strip()}
    return bool(sa) and sa == sb


def _built_usage(decks: List[dict]) -> Dict[str, List[dict]]:
    usage: Dict[str, List[dict]] = {}
    for d in decks:
        if d.get("status") != "built":
            continue
        for key, (name, qty) in _deck_cards(d).items():
            usage.setdefault(key, []).append({"deck": d["name"], "deck_id": d["id"], "name": name, "qty": qty})
    return usage


def check_deck(decklist: str, commanders: List[str], deck_id: str = "") -> dict:
    """Per card: do you have a free copy, or are your copies all in other Built decks?"""
    data = load()
    owned = data["collection"]["cards"]
    this = next((d for d in data["decks"] if d["id"] == deck_id), None) if deck_id else None
    if this is None:
        this = next((d for d in data["decks"] if _same_commanders(d.get("commanders") or [], commanders)), None)
    others = [d for d in data["decks"] if this is None or d["id"] != this["id"]]
    usage = _built_usage(others)

    deck = {"decklist": decklist, "commanders": commanders}
    rows, skipped = [], 0
    for key, (name, qty) in _deck_cards(deck).items():
        if is_basic(name):
            skipped += 1
            continue
        have = (owned.get(key) or {}).get("qty", 0)
        used_in = usage.get(key, [])
        used = sum(u["qty"] for u in used_in)
        free = max(0, have - used)
        need = max(0, qty - free)
        state = "have" if need == 0 else ("in_use" if have else "missing")
        rows.append({"name": name, "qty": qty, "owned": have, "used_elsewhere": used,
                     "free": free, "need": need, "state": state,
                     "used_in": [{"deck": u["deck"], "qty": u["qty"]} for u in used_in]})
    order = {"in_use": 0, "missing": 1, "have": 2}
    rows.sort(key=lambda r: (order[r["state"]], r["name"].lower()))
    count = lambda s: sum(1 for r in rows if r["state"] == s)
    return {
        "rows": rows,
        "matched_deck": {"id": this["id"], "name": this["name"]} if this else None,
        "have": count("have"), "in_use": count("in_use"), "missing": count("missing"),
        "to_buy": sum(r["need"] for r in rows),
        "skipped_basics": skipped,
        "has_collection": bool(owned),
        "built_decks": sum(1 for d in others if d.get("status") == "built"),
    }


def conflicts(data: Optional[dict] = None) -> List[dict]:
    """Cards your Built decks need more copies of, together, than you own."""
    data = data or load()
    owned = data["collection"]["cards"]
    if not owned:
        return []
    out = []
    for key, used_in in _built_usage(data["decks"]).items():
        used = sum(u["qty"] for u in used_in)
        have = (owned.get(key) or {}).get("qty", 0)
        if len(used_in) > 1 and used > have:
            name = (owned.get(key) or {}).get("name") or used_in[0]["name"]
            if is_basic(name):
                continue
            out.append({"name": name, "owned": have, "needed": used, "short": used - have,
                        "used_in": [{"deck": u["deck"], "qty": u["qty"]} for u in used_in]})
    out.sort(key=lambda c: (-c["short"], c["name"].lower()))
    return out


def summary() -> dict:
    data = load()
    col = data["collection"]
    decks = []
    for d in data["decks"]:
        cards = _deck_cards(d)
        decks.append({**d, "count": sum(q for _, q in cards.values())})
    return {
        "collection": {"source": col.get("source", ""), "imported_at": col.get("imported_at"),
                       "unique": len(col["cards"]), "total": sum(c["qty"] for c in col["cards"].values())},
        "decks": decks,
        "conflicts": conflicts(data),
    }
