"""
importer.py — pull a decklist from a Moxfield or Archidekt link.

Both sites expose a public deck JSON endpoint; the result is turned back into
plain decklist text (with a Commander section) so it feeds the same parser
as a pasted list.
"""

import re
from typing import Dict, List, Tuple

from backend.http import Throttle, get_patiently

# Archidekt answers 429 when hit quickly, so every call to it shares one slow lane.
archidekt_throttle = Throttle(1.0)


class ImportError_(Exception):
    pass


_MOXFIELD_RE = re.compile(r"moxfield\.com/decks/([A-Za-z0-9_-]+)")
_ARCHIDEKT_RE = re.compile(r"archidekt\.com/(?:api/)?decks/(\d+)")

# Boards / categories that aren't part of the deck itself.
_SKIP_BOARDS = {"maybeboard", "considering", "tokens", "attractions", "stickers", "contraptions"}


def to_text(name: str, commanders: List[Tuple[int, str]], cards: List[Tuple[int, str]]) -> str:
    lines = []
    if commanders:
        lines.append("Commander")
        lines += [f"{q} {n}" for q, n in commanders]
        lines.append("")
        lines.append("Deck")
    lines += [f"{q} {n}" for q, n in cards]
    return "\n".join(lines)


def parse_moxfield(data: dict) -> Tuple[str, List[Tuple[int, str]], List[Tuple[int, str]]]:
    commanders, cards = [], []
    # v3 shape: {"boards": {"mainboard": {"cards": {id: {"quantity", "card": {"name"}}}}, ...}}
    boards: Dict[str, dict] = {}
    if isinstance(data.get("boards"), dict):
        for board, body in data["boards"].items():
            boards[board.lower()] = (body or {}).get("cards") or {}
    else:
        # v2 shape: {"mainboard": {"Card Name": {"quantity", "card": {...}}}, "commanders": {...}}
        for board in ("commanders", "companions", "mainboard", "sideboard", "maybeboard"):
            if isinstance(data.get(board), dict):
                boards[board] = data[board]
    for board, entries in boards.items():
        if board in _SKIP_BOARDS:
            continue
        for key, entry in entries.items():
            name = ((entry or {}).get("card") or {}).get("name") or key
            qty = int((entry or {}).get("quantity") or 1)
            (commanders if board == "commanders" else cards).append((qty, name))
    return data.get("name", ""), commanders, cards


def parse_archidekt(data: dict) -> Tuple[str, List[Tuple[int, str]], List[Tuple[int, str]]]:
    excluded = {
        (c.get("name") or "").lower()
        for c in data.get("categories") or []
        if c.get("includedInDeck") is False
    } | _SKIP_BOARDS
    commanders, cards = [], []
    for entry in data.get("cards") or []:
        if entry.get("deletedAt"):   # removed from the deck but still in the payload
            continue
        card = entry.get("card") or {}
        name = (card.get("oracleCard") or {}).get("name") or card.get("name")
        if not name:
            continue
        cats = {c.lower() for c in entry.get("categories") or []}
        if cats and cats <= excluded:
            continue
        qty = int(entry.get("quantity") or 1)
        (commanders if "commander" in cats else cards).append((qty, name))
    return data.get("name", ""), commanders, cards


async def _get_json(url: str, site: str) -> dict:
    r = await get_patiently(url, archidekt_throttle if site == "Archidekt" else None)
    if r.status_code == 404:
        raise ImportError_(f"{site} couldn't find that deck. Is it public?")
    if r.status_code == 429:
        raise ImportError_(f"{site} is asking us to slow down. Give it a minute and press Fetch again.")
    if r.status_code >= 400:
        raise ImportError_(
            f"{site} refused the request ({r.status_code}). Export the deck as text and paste it instead."
        )
    try:
        return r.json()
    except ValueError:
        raise ImportError_(f"{site} didn't send deck data back. Export the deck as text and paste it instead.")


async def import_deck(url: str) -> dict:
    url = url.strip()
    if m := _MOXFIELD_RE.search(url):
        deck_id = m.group(1)
        try:
            data = await _get_json(f"https://api2.moxfield.com/v3/decks/all/{deck_id}", "Moxfield")
        except ImportError_:
            data = await _get_json(f"https://api2.moxfield.com/v2/decks/all/{deck_id}", "Moxfield")
        name, commanders, cards = parse_moxfield(data)
    elif m := _ARCHIDEKT_RE.search(url):
        data = await _get_json(f"https://archidekt.com/api/decks/{m.group(1)}/", "Archidekt")
        name, commanders, cards = parse_archidekt(data)
    else:
        raise ImportError_("That doesn't look like a Moxfield or Archidekt deck link.")
    if not cards and not commanders:
        raise ImportError_("That deck came back empty.")
    return {
        "name": name,
        "commanders": [n for _, n in commanders],
        "decklist": to_text(name, commanders, cards),
    }
