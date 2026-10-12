"""
pricing.py — best price per card across Card Kingdom and TCGplayer.

Rule (same as the manual price checks this app replaces):
  * cheapest Near Mint, non-foil copy of ANY paper printing wins;
  * an out-of-stock Card Kingdom listing never wins;
  * TCGplayer price = TCGplayer market price for that printing (via Scryfall).
"""

from typing import Callable, List, Optional

from backend import cardkingdom, scryfall
from backend.decklist import DeckCard

STORES = ("cardkingdom", "tcgplayer")


def pick_best(prints: List[dict], ck_offers: List[dict], tie_goes_to: str = "cardkingdom") -> dict:
    by_id = {p["scryfall_id"]: p for p in prints}

    priced = [p for p in prints if p["usd"] is not None]
    tcg = min(priced, key=lambda p: p["usd"]) if priced else None

    in_stock = [o for o in ck_offers if o["qty"] > 0]
    ck = min(in_stock, key=lambda o: o["price"]) if in_stock else None

    out = {
        "tcgplayer": None,
        "cardkingdom": None,
        "ck_out_of_stock": bool(ck_offers) and not in_stock,
        "image": (tcg or prints[0])["image"] if prints else None,
    }
    if tcg:
        out["tcgplayer"] = {
            "price": tcg["usd"],
            "set": tcg["set"],
            "set_name": tcg["set_name"],
            "collector_number": tcg["collector_number"],
            "url": tcg["tcgplayer_url"] or tcg["scryfall_url"],
        }
    if ck:
        p = by_id.get(ck["scryfall_id"] or "")
        out["cardkingdom"] = {
            "price": ck["price"],
            "set": p["set"] if p else "",
            "set_name": ck["edition"],
            "variation": ck["variation"],
            "stock": ck["qty"],
            "url": ck["url"],
        }

    best = None
    if tcg and ck:
        diff = ck["price"] - tcg["usd"]
        if abs(diff) < 0.005:
            best = tie_goes_to if tie_goes_to in STORES else "cardkingdom"
        else:
            best = "cardkingdom" if diff < 0 else "tcgplayer"
    elif tcg:
        best = "tcgplayer"
    elif ck:
        best = "cardkingdom"
    out["best"] = best
    out["best_price"] = out[best]["price"] if best else None
    if tcg and ck:
        out["savings"] = round(abs(ck["price"] - tcg["usd"]), 2)
    else:
        out["savings"] = None
    return out


async def price_cards(
    cards: List[DeckCard],
    settings: dict,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    cfg = settings["pricing"]
    hours = float(cfg.get("cache_hours", 12))
    tie = cfg.get("tie_goes_to", "cardkingdom")

    pricelist = await cardkingdom.get_pricelist(hours)
    idents = await scryfall.resolve_names([c.name for c in cards])

    rows = []
    for i, card in enumerate(cards):
        if progress:
            progress(i, len(cards), card.name)
        ident = idents.get(card.name)
        row = {"name": card.name, "qty": card.qty, "commander": card.commander}
        if not ident or not ident.get("oracle_id"):
            row["status"] = "not_found"
        elif cfg.get("skip_basic_lands", True) and "Basic" in ident["type_line"] and "Land" in ident["type_line"]:
            row.update(name=ident["name"], status="skipped")
        else:
            prints = await scryfall.printings(ident["oracle_id"], hours)
            offers = pricelist.offers(ident["name"], [p["scryfall_id"] for p in prints])
            row.update(pick_best(prints, offers, tie))
            row["name"] = ident["name"]
            row["status"] = "ok" if row["best"] else "no_price"
        rows.append(row)
    if progress:
        progress(len(cards), len(cards), "")

    return {"rows": rows, "totals": totals(rows), "ck_pricelist_at": pricelist.fetched_at}


def totals(rows: List[dict]) -> dict:
    t = {
        "best_split": 0.0,
        "cardkingdom_only": 0.0, "cardkingdom_missing": 0,
        "tcgplayer_only": 0.0, "tcgplayer_missing": 0,
        "by_store": {s: {"cards": 0, "total": 0.0} for s in STORES},
        "unpriced": 0,
    }
    for r in rows:
        if r.get("status") != "ok" and r.get("status") != "no_price":
            continue
        q = r["qty"]
        if r["best"]:
            t["best_split"] += q * r["best_price"]
            t["by_store"][r["best"]]["cards"] += q
            t["by_store"][r["best"]]["total"] += q * r["best_price"]
        else:
            t["unpriced"] += q
        for s, key in (("cardkingdom", "cardkingdom_only"), ("tcgplayer", "tcgplayer_only")):
            if r.get(s):
                t[key] += q * r[s]["price"]
            else:
                t[f"{s}_missing"] += q
    for k in ("best_split", "cardkingdom_only", "tcgplayer_only"):
        t[k] = round(t[k], 2)
    for s in STORES:
        t["by_store"][s]["total"] = round(t["by_store"][s]["total"], 2)
    return t
