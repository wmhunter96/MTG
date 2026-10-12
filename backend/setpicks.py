"""
setpicks.py — "what from this set should I add?"

For a chosen set, every card in the deck's colors is scored for impact:
  * cards EDHREC already lists on the commander's page score by how many of
    that commander's decks run them plus their synergy — the strongest signal;
  * everything else falls back to how widely the card is played across all
    EDHREC decks that could run it (from EDHREC's set page), weighted lower.
Cards already in the deck are flagged so the UI can hide them.
"""

from typing import List

from backend import edhrec, scryfall
from backend.decklist import normalize_name

# A commander-page hit outranks raw popularity: inclusion% + synergy%.
# Popularity-only cards get their overall inclusion% times this weight.
POPULARITY_WEIGHT = 0.5


def score(
    cards: List[dict],
    commander_views: List[dict],
    set_views: List[dict],
    colors: set | None,
    deck_names: List[str],
) -> List[dict]:
    have = {normalize_name(n) for n in deck_names}
    cmdr = {normalize_name(v["name"]): v for v in commander_views if v.get("name")}
    pop = {normalize_name(v["name"]): v for v in set_views if v.get("name")}

    out = []
    for c in cards:
        if colors is not None and not set(c["color_identity"]) <= colors:
            continue
        key = normalize_name(c["name"])
        row = {**c, "in_deck": key in have, "why": "", "impact": 0.0,
               "inclusion_pct": None, "synergy_pct": None, "source": None}
        if key in cmdr:
            v = cmdr[key]
            inc = edhrec._pct(v.get("num_decks"), v.get("potential_decks")) or 0.0
            syn = round(100 * v["synergy"]) if isinstance(v.get("synergy"), (int, float)) else 0
            row.update(source="commander", inclusion_pct=inc, synergy_pct=syn, impact=round(inc + max(syn, 0), 1),
                       why=f"In {inc:g}% of this commander's decks" + (f", {syn:+d}% synergy" if syn else ""))
        elif key in pop:
            v = pop[key]
            inc = edhrec._pct(v.get("num_decks"), v.get("potential_decks")) or 0.0
            row.update(source="popular", inclusion_pct=inc, impact=round(inc * POPULARITY_WEIGHT, 2),
                       why=f"In {inc:g}% of all decks that could play it")
        else:
            continue   # nobody's playing it yet — not "high impact"
        out.append(row)
    out.sort(key=lambda r: r["impact"], reverse=True)
    return out


async def set_picks(set_code: str, commanders: List[str], deck_names: List[str], settings: dict) -> dict:
    hours = float(settings["pricing"].get("cache_hours", 12))
    cards = await scryfall.set_cards(set_code, hours)
    if not cards:
        raise edhrec.EdhrecError(f"Scryfall has no cards for set '{set_code.upper()}'")

    colors = None
    commander_views: List[dict] = []
    commander_name = ""
    if commanders:
        idents = await scryfall.resolve_names(commanders)
        colors = set()
        for n in commanders:
            ident = idents.get(n)
            if ident:
                colors |= set(ident.get("color_identity") or [])
        try:
            page = await edhrec.commander_page(commanders, "")
            commander_views = list(edhrec.cardviews(page["data"]))
            commander_name = page["data"].get("header", "")
        except edhrec.EdhrecError:
            pass   # brand-new commander: fall back to set-wide popularity

    set_data = await edhrec.set_page(set_code)
    set_views = list(edhrec.cardviews(set_data)) if set_data else []

    picks = score(cards, commander_views, set_views, colors, deck_names)
    return {
        "set": set_code.upper(),
        "commander": commander_name,
        "colors": sorted(colors) if colors is not None else None,
        "picks": picks,
        "edhrec_set_found": set_data is not None,
    }
