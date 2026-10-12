"""
decklist.py — parse pasted decklists.

Handles the common export formats:
  1 Sol Ring
  1x Sol Ring
  1 Sol Ring (CMR) 472
  1 Sol Ring (CMR) 472 *F*
  1 Atraxa, Praetors' Voice *CMDR*      (Archidekt / Moxfield)
  1 Sol Ring [Ramp]                      (Archidekt categories)
  1 Sol Ring #ramp                       (Moxfield tags)
  Sol Ring                               (no quantity = 1)

Section headers ("Commander", "Deck", "Sideboard:", "// Lands", ...) are
recognised. Cards under a Commander header (or marked *CMDR*) are returned
as commanders; Maybeboard / Considering sections are ignored.
"""

import re
from dataclasses import dataclass, field
from typing import List

_SECTION_WORDS = {
    "commander", "commanders", "deck", "main", "mainboard", "main deck",
    "sideboard", "companion", "maybeboard", "maybe", "considering", "tokens",
    "lands", "creatures", "instants", "sorceries", "artifacts", "enchantments",
    "planeswalkers", "battles", "other", "spells",
}
_SKIP_SECTIONS = {"maybeboard", "maybe", "considering", "tokens"}

_LINE_RE = re.compile(r"^(?:(\d+)\s*[xX]?\s+)?(.+)$")
_SET_RE = re.compile(r"\s+\(([A-Za-z0-9]{2,6})\)(?:\s+[^\s*#\[]+)?")
_MARKER_RE = re.compile(r"\s*\*([A-Za-z]+)\*")
_CATEGORY_RE = re.compile(r"\s*\[[^\]]*\]")
_TAG_RE = re.compile(r"\s+#\S+")


@dataclass
class DeckCard:
    name: str
    qty: int = 1
    commander: bool = False


@dataclass
class Deck:
    cards: List[DeckCard] = field(default_factory=list)

    @property
    def commanders(self) -> List[str]:
        return [c.name for c in self.cards if c.commander]


def normalize_name(name: str) -> str:
    """Matching key for a card name: front face only, case/punctuation-insensitive."""
    front = name.split("//")[0]
    return re.sub(r"[^a-z0-9]+", " ", front.lower()).strip()


def _section_name(line: str) -> str | None:
    s = line.strip().lstrip("/#").strip().rstrip(":").strip()
    # "Commander (1)" / "Lands (36)" style headers
    s = re.sub(r"\s*\(\d+\)$", "", s)
    return s.lower() if s.lower() in _SECTION_WORDS else None


def parse_decklist(text: str) -> Deck:
    merged: dict[str, DeckCard] = {}
    section = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        sec = _section_name(line)
        if sec is not None:
            section = sec
            continue
        if line.startswith("//") or line.startswith("#"):
            continue
        if section in _SKIP_SECTIONS:
            continue

        m = _LINE_RE.match(line)
        if not m:
            continue
        qty = int(m.group(1)) if m.group(1) else 1
        rest = m.group(2)

        markers = {mk.upper() for mk in _MARKER_RE.findall(rest)}
        rest = _MARKER_RE.sub("", rest)
        rest = _CATEGORY_RE.sub("", rest)
        rest = _TAG_RE.sub("", rest)
        rest = _SET_RE.sub("", rest)
        name = rest.strip()
        if not name or qty <= 0:
            continue

        is_cmdr = "CMDR" in markers or section in ("commander", "commanders")
        key = normalize_name(name)
        if key in merged:
            merged[key].qty += qty
            merged[key].commander = merged[key].commander or is_cmdr
        else:
            merged[key] = DeckCard(name=name, qty=qty, commander=is_cmdr)

    return Deck(cards=list(merged.values()))
