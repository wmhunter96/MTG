"""
budget.py — "what would this card cost me?" for long suggestion lists.

A card's budget price is the cheaper of Card Kingdom's lowest in-stock NM
price (any printing) and TCGplayer's market price for its default printing.
It's a quick estimate for filtering; the Bargains tab does the exhaustive
every-printing search.
"""

from typing import Dict, List, Optional

from backend import cardkingdom, scryfall


async def budget_prices(names: List[str], settings: dict) -> Dict[str, Optional[float]]:
    hours = float(settings["pricing"].get("cache_hours", 12))
    names = list(dict.fromkeys(names))
    tcg = await scryfall.quick_prices(names, hours)
    try:
        pricelist = await cardkingdom.get_pricelist(hours)
    except cardkingdom.CardKingdomError:
        pricelist = None
    out = {}
    for n in names:
        options = [p for p in (tcg.get(n), pricelist.cheapest_in_stock(n) if pricelist else None) if p is not None]
        out[n] = min(options) if options else None
    return out


def within_budget(price: Optional[float], max_usd: float) -> bool:
    # Unknown price = can't promise it's cheap, so it's left out.
    return price is not None and price <= max_usd + 1e-9
