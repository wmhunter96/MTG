from backend.cardkingdom import parse_pricelist
from backend.pricing import pick_best, totals


def _print(sid, usd, set_code="CMR"):
    return {"scryfall_id": sid, "set": set_code, "set_name": set_code + " set", "collector_number": "1",
            "usd": usd, "tcgplayer_url": f"https://tcg/{sid}", "scryfall_url": None, "image": None}


PRICELIST = {"meta": {}, "data": [
    {"scryfall_id": "a", "name": "Sol Ring", "edition": "Commander Legends", "variation": "",
     "is_foil": "false", "price_retail": "1.49", "qty_retail": 20, "url": "mtg/commander-legends/sol-ring"},
    {"scryfall_id": "b", "name": "Sol Ring", "edition": "Promo", "variation": "",
     "is_foil": "false", "price_retail": "0.99", "qty_retail": 0, "url": "mtg/promo/sol-ring"},
    {"scryfall_id": "a", "name": "Sol Ring", "edition": "Commander Legends", "variation": "",
     "is_foil": "true", "price_retail": "0.50", "qty_retail": 5, "url": "mtg/commander-legends/sol-ring-foil"},
    {"scryfall_id": None, "name": "Sol Ring", "edition": "Collectors Ed", "variation": "",
     "is_foil": "false", "price_retail": "0.10", "qty_retail": 5, "url": "mtg/ce/sol-ring"},
    {"scryfall_id": "zzz", "name": "Sol Ring", "edition": "Gold Border", "variation": "",
     "is_foil": "false", "price_retail": "0.05", "qty_retail": 5, "url": "mtg/wc/sol-ring"},
]}


def test_ck_ignores_foils_out_of_stock_and_memorabilia():
    pl = parse_pricelist(PRICELIST, 0)
    prints = [_print("a", 1.80), _print("b", 2.10, "PRM")]
    best = pick_best(prints, pl.offers("Sol Ring", ["a", "b"]))
    assert best["cardkingdom"]["price"] == 1.49
    assert best["cardkingdom"]["url"] == "https://www.cardkingdom.com/mtg/commander-legends/sol-ring"
    assert best["tcgplayer"]["price"] == 1.80
    assert best["best"] == "cardkingdom"
    assert best["savings"] == 0.31


def test_tcg_wins_when_cheaper_and_tie_rule():
    pl = parse_pricelist(PRICELIST, 0)
    offers = pl.offers("Sol Ring", ["a"])
    assert pick_best([_print("a", 0.75)], offers)["best"] == "tcgplayer"
    assert pick_best([_print("a", 1.49)], offers, "tcgplayer")["best"] == "tcgplayer"
    assert pick_best([_print("a", 1.49)], offers, "cardkingdom")["best"] == "cardkingdom"


def test_only_out_of_stock_ck_never_wins():
    pl = parse_pricelist(PRICELIST, 0)
    offers = [o for o in pl.offers("Sol Ring", ["b"]) if o["scryfall_id"] == "b"]
    best = pick_best([_print("b", 5.00)], offers)
    assert best["best"] == "tcgplayer"
    assert best["ck_out_of_stock"] is True


def test_totals():
    rows = [
        {"status": "ok", "qty": 2, "best": "cardkingdom", "best_price": 1.0,
         "cardkingdom": {"price": 1.0}, "tcgplayer": {"price": 1.5}},
        {"status": "ok", "qty": 1, "best": "tcgplayer", "best_price": 3.0,
         "cardkingdom": None, "tcgplayer": {"price": 3.0}},
        {"status": "skipped", "qty": 10},
    ]
    t = totals(rows)
    assert t["best_split"] == 5.0
    assert t["cardkingdom_only"] == 2.0 and t["cardkingdom_missing"] == 1
    assert t["tcgplayer_only"] == 6.0
    assert t["by_store"]["cardkingdom"] == {"cards": 2, "total": 2.0}
