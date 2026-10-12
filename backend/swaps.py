"""
swaps.py — "this card is pricey, what else does the same job?" for Brewing decks.

Every deck card over the Brewing price cap gets a few cheaper replacements:
  * candidates come from the commander's EDHREC page (plus its Budget page),
    minus anything already in the deck, at or under the cap;
  * each card is tagged with the jobs it does (ramp, draw, removal, ...) from
    its rules text, and candidates that share the pricey card's jobs win;
  * ties go to the same card type and mana value, then to how often the
    commander's decks run the candidate.
"""

import re
from typing import Dict, List, Optional

from backend import budget, edhrec, scryfall
from backend.decklist import normalize_name

SWAPS_PER_CARD = 3

# Each role is a list of patterns over lower-cased rules text, with the card's
# own name replaced by "~". Deliberately rough: it only needs to tell a Sol Ring
# from a Swords to Plowshares, not judge card quality.
ROLES: Dict[str, List[str]] = {
    "ramp": [r"\badd \{", r"\badd (one|two|three) mana", r"search your library for (a|an|up to \w+) .*?\bland",
             r"put (a|an|up to \w+) .*?land cards? .*?onto the battlefield", r"treasure token"],
    "draw": [r"\bdraws? (a|an|one|two|three|four|x|that many) .*?cards?", r"\bdraw cards\b"],
    "removal": [r"\bdestroy target", r"\bexile target (?!card)", r"\bdeals? (\d+|x) damage to (any target|target)",
                r"\btarget (player|opponent) sacrifices", r"\breturn target [^.]*?(creature|permanent|artifact|enchantment)[^.]* to (its|their) owner'?s'? hand",
                r"\bfights? (target|another|up to)"],
    "wipe": [r"\b(destroy|exile) all\b", r"\b(destroy|exile) each\b", r"\ball creatures get -", r"\beach creature gets -",
             r"\bdeals? (\d+|x) damage to each creature"],
    "counter": [r"\bcounter target"],
    "tutor": [r"search your library for (a|an|up to \w+) (?!.*\bland\b)[^.]*card"],
    "recursion": [r"\breturn [^.]*from (your|a) graveyard", r"\bcast [^.]*from your graveyard", r"\bplay [^.]*from your graveyard"],
    "protection": [r"\b(gain|gains|have|has) (hexproof|indestructible|shroud|protection)", r"\bphase out\b"],
    "tokens": [r"\bcreate [^.]*tokens?\b"],
}
_ROLE_RE = {role: [re.compile(p) for p in pats] for role, pats in ROLES.items()}

ROLE_LABELS = {
    "ramp": "ramp", "draw": "card draw", "removal": "removal", "wipe": "a board wipe", "counter": "a counterspell",
    "tutor": "a tutor", "recursion": "recursion", "protection": "protection", "tokens": "makes tokens", "land": "a land",
}

_TYPES = ["Land", "Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Artifact", "Enchantment"]


def card_type(type_line: str) -> str:
    """Main card type; a creature that's also an artifact counts as a creature."""
    front = (type_line or "").split("//")[0]
    for t in _TYPES:
        if t in front:
            return t
    return ""


def roles(name: str, type_line: str, oracle_text: str) -> List[str]:
    if card_type(type_line) == "Land":
        return ["land"]
    text = (oracle_text or "").lower()
    for part in {name, name.split("//")[0].strip(), name.split(",")[0].strip()}:
        if part:
            text = text.replace(part.lower(), "~")
    # Reminder text describes keywords, not what the card does.
    text = re.sub(r"\([^)]*\)", "", text)
    return [role for role, pats in _ROLE_RE.items() if any(p.search(text) for p in pats)]


def rank(target: dict, candidates: List[dict], count: int = SWAPS_PER_CARD) -> List[dict]:
    """Best `count` stand-ins for `target` among `candidates` (each has roles/type/cmc/score)."""
    want = set(target["roles"])
    scored = []
    for c in candidates:
        shared = want & set(c["roles"])
        same_type = bool(target["type"]) and c["type"] == target["type"]
        if want and not shared:
            continue
        if not want and not same_type:
            continue
        if "land" in want and c["type"] != "Land" or c["type"] == "Land" and "land" not in want:
            continue   # lands only swap for lands
        cmc_gap = abs((c.get("cmc") or 0) - (target.get("cmc") or 0))
        key = (len(shared), same_type, -min(cmc_gap, 3), c["score"])
        scored.append((key, c, sorted(shared)))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for _, c, shared in scored[:count]:
        bits = []
        if shared:
            bits.append("also " + ", ".join(ROLE_LABELS.get(r, r) for r in shared))
        if c["inclusion_pct"] is not None:
            bits.append(f"in {c['inclusion_pct']:g}% of this commander's decks")
        out.append({k: c[k] for k in ("name", "price", "inclusion_pct", "synergy_pct", "url", "type", "roles")}
                   | {"why": "; ".join(bits)})
    return out


async def budget_swaps(deck_names: List[str], commanders: List[str], settings: dict,
                       max_price: float) -> dict:
    page = await edhrec.commander_page(commanders, "")
    pages = [page]
    try:
        pages.append(await edhrec.commander_page(commanders, "budget"))
    except edhrec.EdhrecError:
        pass   # not every commander has a budget page

    have = {normalize_name(n) for n in deck_names} | {normalize_name(c) for c in commanders}
    cmdr_keys = {normalize_name(c) for c in commanders}
    playable = [n for n in dict.fromkeys(deck_names) if normalize_name(n) not in cmdr_keys]

    # EDHREC cards the deck doesn't run, best stats wins when a card shows up twice.
    views: Dict[str, dict] = {}
    for p in pages:
        for v in edhrec.cardviews(p["data"]):
            name = v.get("name")
            if not name or normalize_name(name) in have:
                continue
            inc = edhrec._pct(v.get("num_decks", v.get("inclusion")), v.get("potential_decks"))
            syn = round(100 * v["synergy"]) if isinstance(v.get("synergy"), (int, float)) else None
            prev = views.get(normalize_name(name))
            if prev is None or (inc or 0) > (prev["inclusion_pct"] or 0):
                views[normalize_name(name)] = {
                    "name": name, "inclusion_pct": inc, "synergy_pct": syn,
                    "url": f"{edhrec.SITE}{v['url']}" if v.get("url") else f"{edhrec.SITE}/cards/{edhrec.slugify(name)}",
                }

    prices = await budget.budget_prices(playable + [v["name"] for v in views.values()], settings)
    pricey = [n for n in playable if prices.get(n) is not None and not budget.within_budget(prices[n], max_price)]
    cheap = [v for v in views.values() if budget.within_budget(prices.get(v["name"]), max_price)]

    idents = await scryfall.resolve_names(pricey + [v["name"] for v in cheap]) if pricey else {}

    def describe(name: str) -> Optional[dict]:
        ident = idents.get(name)
        if not ident:
            return None
        if "Basic" in ident["type_line"] and "Land" in ident["type_line"]:
            return None
        return {"type": card_type(ident["type_line"]), "cmc": ident.get("cmc"),
                "roles": roles(ident["name"], ident["type_line"], ident.get("oracle_text", ""))}

    candidates = []
    for v in cheap:
        d = describe(v["name"])
        if d:
            candidates.append({**v, **d, "price": prices[v["name"]],
                               "score": (v["inclusion_pct"] or 0) + max(v["synergy_pct"] or 0, 0)})

    rows = []
    for n in pricey:
        d = describe(n)
        if not d:
            continue
        target = {"name": idents[n]["name"], "price": prices[n], **d}
        swaps = rank(target, candidates)
        target["swaps"] = swaps
        target["saves"] = round(prices[n] - min(s["price"] for s in swaps), 2) if swaps else None
        rows.append(target)
    rows.sort(key=lambda r: r["price"], reverse=True)

    return {
        "commander": page["data"].get("header", ""),
        "url": f"{edhrec.SITE}/{page['path']}",
        "budget_max_usd": max_price,
        "cards": rows,
        "over_cap_total": round(sum(r["price"] for r in rows), 2),
        "potential_savings": round(sum(r["saves"] or 0 for r in rows), 2),
    }
