"""
setpicks.py — "what from this set should I add?"

For a chosen set, every card in the deck's colors is scored for impact:
  * cards EDHREC already lists on the commander's page score by how many of
    that commander's decks run them plus their synergy — the strongest signal;
  * everything else falls back to how widely the card is played across all
    EDHREC decks that could run it (from EDHREC's set page), weighted lower.
Cards already in the deck are flagged so the UI can hide them.
"""

from typing import List, Optional

from backend import budget, edhrec, scryfall
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


async def set_picks(set_code: str, commanders: List[str], deck_names: List[str], settings: dict,
                    max_price: Optional[float] = None) -> dict:
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
    if max_price is not None:
        picks = await apply_budget(picks, settings, max_price)
    return {
        "set": set_code.upper(),
        "commander": commander_name,
        "colors": sorted(colors) if colors is not None else None,
        "picks": picks,
        "edhrec_set_found": set_data is not None,
        "budget_max_usd": max_price,
    }


async def apply_budget(rows: List[dict], settings: dict, max_price: float) -> List[dict]:
    """Keep cards the deck already has, plus new ones at or under max_price (adds `budget_price`)."""
    prices = await budget.budget_prices([r["name"] for r in rows if not r.get("in_deck")], settings)
    kept = []
    for r in rows:
        if r.get("in_deck"):
            kept.append(r)
            continue
        r["budget_price"] = prices.get(r["name"])
        if budget.within_budget(r["budget_price"], max_price):
            kept.append(r)
    return kept


# Set types that bring new cards to Commander (skips masters/reprint sets).
_NEW_CARD_SET_TYPES = {"expansion", "core", "commander", "draft_innovation"}


async def recent_picks(commanders: List[str], deck_names: List[str], settings: dict,
                       max_price: Optional[float] = None) -> dict:
    """High-impact picks across the newest few sets, for decks that are already built."""
    n = int(settings["brewing"].get("recent_sets", 3))
    sets = [s for s in await scryfall.list_sets() if s["set_type"] in _NEW_CARD_SET_TYPES][:max(1, n)]
    merged: dict = {}
    commander_name, colors = "", None
    for s in sets:
        try:
            res = await set_picks(s["code"], commanders, deck_names, settings, max_price)
        except edhrec.EdhrecError:
            continue
        commander_name = commander_name or res["commander"]
        colors = res["colors"] if colors is None else colors
        for p in res["picks"]:
            key = normalize_name(p["name"])
            if key not in merged or p["impact"] > merged[key]["impact"]:
                merged[key] = {**p, "set": s["code"].upper(), "set_name": s["name"]}
    picks = sorted(merged.values(), key=lambda r: r["impact"], reverse=True)
    return {
        "sets": [{"code": s["code"].upper(), "name": s["name"]} for s in sets],
        "commander": commander_name,
        "colors": colors,
        "picks": picks,
        "budget_max_usd": max_price,
    }
