"""End-to-end through the FastAPI app with every outbound site mocked."""

import json
import time

import httpx
from fastapi.testclient import TestClient

from backend import http, importer
from backend.main import app

SCRY = {
    "sol ring": {"name": "Sol Ring", "oracle_id": "o-sol", "type_line": "Artifact"},
    "mana crypt": {"name": "Mana Crypt", "oracle_id": "o-crypt", "type_line": "Artifact", "prices": {"usd": "150.00"},
                   "cmc": 0, "oracle_text": "{T}: Add {C}{C}."},
    "mind stone": {"name": "Mind Stone", "oracle_id": "o-stone", "type_line": "Artifact", "prices": {"usd": "0.50"},
                   "cmc": 2, "oracle_text": "{T}: Add {C}.\n{1}, {T}, Sacrifice Mind Stone: Draw a card."},
    "pricey bolt": {"name": "Pricey Bolt", "oracle_id": "o-bolt", "type_line": "Instant", "prices": {"usd": "40.00"},
                    "cmc": 1, "oracle_text": "Pricey Bolt deals 3 damage to any target."},
    "swap guy": {"name": "Swap Guy", "oracle_id": "o-swap", "type_line": "Legendary Creature", "color_identity": ["R"]},
    "cheap trick": {"name": "Cheap Trick", "oracle_id": "o-trick", "type_line": "Instant", "prices": {"usd": "0.25"}},
    "sol ring guy": {"name": "Sol Ring Guy", "oracle_id": "o-guy", "type_line": "Legendary Creature", "color_identity": ["G"]},
    "forest": {"name": "Forest", "oracle_id": "o-forest", "type_line": "Basic Land — Forest"},
    "delver of secrets": {"name": "Delver of Secrets // Insectile Aberration", "oracle_id": None,
                          "type_line": "", "card_faces": [
                              {"name": "Delver of Secrets", "oracle_id": "o-delver", "type_line": "Creature"},
                              {"name": "Insectile Aberration", "type_line": "Creature"}]},
}
PRINTS = {
    "o-sol": [{"id": "s1", "set": "cmr", "set_name": "Commander Legends", "collector_number": "472",
               "prices": {"usd": "1.80"}, "purchase_uris": {"tcgplayer": "https://tcg/s1"},
               "image_uris": {"small": "img"}}],
    "o-delver": [{"id": "d1", "set": "isd", "set_name": "Innistrad", "collector_number": "51",
                  "prices": {"usd": "0.40"}, "purchase_uris": {"tcgplayer": "https://tcg/d1"},
                  "card_faces": [{"image_uris": {"small": "img"}}]}],
}
CK = {"data": [
    {"scryfall_id": "s1", "name": "Sol Ring", "edition": "Commander Legends", "variation": "",
     "is_foil": "false", "price_retail": "1.49", "qty_retail": 12, "url": "mtg/cmr/sol-ring"},
    {"scryfall_id": "d1", "name": "Delver of Secrets", "edition": "Innistrad", "variation": "",
     "is_foil": "false", "price_retail": "0.79", "qty_retail": 3, "url": "mtg/isd/delver"},
]}
EDH = {"header": "Sol Ring Guy", "container": {"json_dict": {"cardlists": [
    {"header": "Top Cards", "tag": "topcards", "cardviews": [
        {"name": "Sol Ring", "url": "/cards/sol-ring", "synergy": 0, "num_decks": 9, "potential_decks": 10},
        {"name": "Mana Crypt", "url": "/cards/mana-crypt", "synergy": 0.1, "num_decks": 5, "potential_decks": 10},
        {"name": "Cheap Trick", "url": "/cards/cheap-trick", "synergy": 0.05, "num_decks": 2, "potential_decks": 10}]}]}}}

EDH_SWAP = {"header": "Swap Guy", "container": {"json_dict": {"cardlists": [
    {"header": "Top Cards", "tag": "topcards", "cardviews": [
        {"name": "Mana Crypt", "url": "/cards/mana-crypt", "synergy": 0.0, "num_decks": 60, "potential_decks": 100},
        {"name": "Mind Stone", "url": "/cards/mind-stone", "synergy": 0.05, "num_decks": 45, "potential_decks": 100},
        {"name": "Cheap Trick", "url": "/cards/cheap-trick", "synergy": 0.3, "num_decks": 35, "potential_decks": 100},
        {"name": "Sol Ring", "url": "/cards/sol-ring", "synergy": 0.0, "num_decks": 90, "potential_decks": 100}]}]}}}

SETS = [
    {"code": "new", "name": "Newest Set", "released_at": "2026-09-01", "set_type": "expansion", "card_count": 3},
    {"code": "fut", "name": "Future Set", "released_at": "2099-01-01", "set_type": "expansion", "card_count": 3},
    {"code": "tok", "name": "Tokens", "released_at": "2026-09-01", "set_type": "token", "card_count": 3},
]
NEW_SET = [
    {"id": "n1", "name": "Mana Crypt", "color_identity": [], "rarity": "mythic", "type_line": "Artifact",
     "prices": {"usd": "150.00"}, "image_uris": {"small": "img"}},
    {"id": "n2", "name": "Red Card", "color_identity": ["R"], "rarity": "rare", "type_line": "Instant",
     "prices": {"usd": "1.00"}, "image_uris": {"small": "img"}},
]
EDH_SET = {"container": {"json_dict": {"cardlists": [{"header": "Cards (NEW)", "cardviews": [
    {"name": "Red Card", "num_decks": 10, "potential_decks": 100}]}]}}}
ARCHIDEKT = {"name": "Imported", "categories": [], "cards": [
    {"quantity": 1, "categories": ["Commander"], "card": {"oracleCard": {"name": "Sol Ring Guy"}}},
    {"quantity": 1, "categories": ["Ramp"], "card": {"oracleCard": {"name": "Sol Ring"}}},
    {"quantity": 1, "categories": ["Ramp"], "deletedAt": "2026-10-01T00:00:00Z", "card": {"oracleCard": {"name": "Mana Crypt"}}}]}

ARCH_COLLECTION = {
    1: {"count": 3, "next": "https://archidekt.com/api/collection/99/?page=2&pageSize=100", "results": [
        {"quantity": 1, "card": {"oracleCard": {"name": "Sol Ring"}}},
        {"quantity": 1, "card": {"oracleCard": {"name": "Mana Crypt"}}}]},
    2: {"count": 3, "next": None, "results": [{"quantity": 2, "card": {"oracleCard": {"name": "Mind Stone"}}}]},
}
ARCH_USER = {"count": 1, "next": None, "results": [{"id": 42, "name": "Imported", "updatedAt": "2026-10-01T00:00:00Z",
                                                     "owner": {"id": 1, "username": "wmhunter96"}}]}

calls = []
flaky = {"collection": 1, "deck": 0}   # 429s to hand out before answering


def handler(req: httpx.Request) -> httpx.Response:
    calls.append(str(req.url))
    host, path = req.url.host, req.url.path
    if host == "archidekt.com" and path == "/api/collection/99/" and flaky["collection"] > 0:
        flaky["collection"] -= 1
        return httpx.Response(429, headers={"Retry-After": "3"})
    if host == "archidekt.com" and path == "/api/decks/42/" and flaky["deck"] > 0:
        flaky["deck"] -= 1
        return httpx.Response(429)
    if host == "api.scryfall.com" and path == "/cards/collection":
        ids = json.loads(req.content)["identifiers"]
        data = [SCRY[i["name"].lower()] for i in ids if i["name"].lower() in SCRY]
        return httpx.Response(200, json={"data": data, "not_found": []})
    if host == "api.scryfall.com" and path == "/cards/named":
        return httpx.Response(404, json={})
    if host == "api.scryfall.com" and path == "/cards/search":
        q = req.url.params["q"]
        if q.startswith("e:new"):
            return httpx.Response(200, json={"data": NEW_SET, "has_more": False})
        oid = q.split()[0].split(":")[1]
        return httpx.Response(200, json={"data": PRINTS.get(oid, []), "has_more": False})
    if host == "api.cardkingdom.com":
        return httpx.Response(200, json=CK)
    if host == "json.edhrec.com" and path == "/pages/commanders/sol-ring-guy.json":
        return httpx.Response(200, json=EDH)
    if host == "json.edhrec.com" and path == "/pages/commanders/swap-guy.json":
        return httpx.Response(200, json=EDH_SWAP)
    if host == "json.edhrec.com" and path == "/pages/sets/new.json":
        return httpx.Response(200, json=EDH_SET)
    if host == "api.scryfall.com" and path == "/sets":
        return httpx.Response(200, json={"data": SETS})
    if host == "archidekt.com" and path == "/api/decks/42/":
        return httpx.Response(200, json=ARCHIDEKT)
    if host == "archidekt.com" and path == "/api/collection/99/":
        return httpx.Response(200, json=ARCH_COLLECTION[int(req.url.params.get("page", 1))])
    if host == "archidekt.com" and path == "/api/collection/13/":
        return httpx.Response(403, json={})
    if host == "archidekt.com" and path == "/api/decks/v3/":
        if req.url.params.get("ownerUsername") == "wmhunter96":
            return httpx.Response(200, json=ARCH_USER)
        return httpx.Response(200, json={"count": 0, "next": None, "results": []})
    if host == "archidekt.com" and path == "/api/decks/cards/" and req.url.params.get("owner") == "oldapi":
        return httpx.Response(200, json={"count": 1, "next": None, "results": [
            {k: v for k, v in d.items() if k != "owner"} for d in ARCH_USER["results"]]})
    if host == "archidekt.com" and path == "/api/decks/cards/":
        if req.url.params.get("owner") == "wmhunter96":
            return httpx.Response(200, json=ARCH_USER)
        return httpx.Response(200, json={"count": 0, "next": None, "results": []})
    return httpx.Response(404)


http._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
importer.archidekt_throttle.interval = 0
slept = []


async def _no_sleep(seconds):
    slept.append(seconds)


http._sleep = _no_sleep
client = TestClient(app)
client.__enter__()   # one event loop for the whole module, so background jobs keep running


def test_price_job_end_to_end():
    deck = "1 Sol Ring\n10 Forest\n1 Delver of Secrets\n1 Notacard Atall"
    job_id = client.post("/api/prices/jobs", json={"decklist": deck}).json()["id"]
    for _ in range(100):
        job = client.get(f"/api/prices/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    rows = {r["name"]: r for r in job["result"]["rows"]}
    assert rows["Sol Ring"]["best"] == "cardkingdom" and rows["Sol Ring"]["best_price"] == 1.49
    assert rows["Delver of Secrets // Insectile Aberration"]["best"] == "tcgplayer"
    assert rows["Forest"]["status"] == "skipped"
    assert rows["Notacard Atall"]["status"] == "not_found"
    assert job["result"]["totals"]["best_split"] == 1.89


def test_edhrec_endpoint():
    r = client.post("/api/edhrec", json={"decklist": "1 Sol Ring Guy *CMDR*\n1 Sol Ring"})
    assert r.status_code == 200, r.text
    names = [c["name"] for l in r.json()["lists"] for c in l["cards"] if not c["in_deck"]]
    assert names == ["Mana Crypt", "Cheap Trick"]
    assert client.post("/api/edhrec", json={"commanders": ["Nobody Here"]}).status_code == 404


def test_settings_roundtrip_and_index():
    s = client.post("/api/settings", json={"cache_hours": 6, "skip_basic_lands": False,
                                           "tie_goes_to": "tcgplayer", "min_inclusion_pct": 5}).json()
    assert s["pricing"]["cache_hours"] == 6 and s["edhrec"]["min_inclusion_pct"] == 5
    assert client.get("/api/settings").json()["pricing"]["tie_goes_to"] == "tcgplayer"
    assert "MTG Brewmaster" in client.get("/").text


def test_import_sets_and_setpicks():
    imp = client.post("/api/import", json={"url": "https://archidekt.com/decks/42/imported"}).json()
    assert imp["commanders"] == ["Sol Ring Guy"]
    assert client.post("/api/import", json={"url": "https://example.com/deck"}).status_code == 400

    sets = client.get("/api/sets").json()
    assert [s["code"] for s in sets] == ["new"]   # future + token sets filtered out

    r = client.post("/api/setpicks", json={"set": "new", "decklist": imp["decklist"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["colors"] == ["G"]
    # Red Card is off-color; Mana Crypt is on Sol Ring Guy's EDHREC page.
    assert [p["name"] for p in body["picks"]] == ["Mana Crypt"]
    assert body["picks"][0]["source"] == "commander" and not body["picks"][0]["in_deck"]


def test_brewing_budget_and_built_recent_picks():
    deck = "1 Sol Ring Guy *CMDR*\n1 Sol Ring"
    # Brewing: $5 cap (default) drops the $150 Mana Crypt but keeps the in-deck Sol Ring.
    r = client.post("/api/edhrec", json={"decklist": deck, "status": "brewing"}).json()
    cards = {c["name"]: c for l in r["lists"] for c in l["cards"]}
    assert r["budget_max_usd"] == 5.0
    assert "Mana Crypt" not in cards and cards["Cheap Trick"]["budget_price"] == 0.25
    assert cards["Sol Ring"]["in_deck"]
    assert r["missing_count"] == 1

    # Built: picks pulled from the newest sets, no price cap.
    built = client.post("/api/recentpicks", json={"decklist": deck, "status": "built"}).json()
    assert [s["code"] for s in built["sets"]] == ["NEW"]
    assert [p["name"] for p in built["picks"]] == ["Mana Crypt"] and built["picks"][0]["set"] == "NEW"

    # Brewing on a single set applies the same cap.
    brewing_set = client.post("/api/setpicks", json={"set": "new", "decklist": deck, "status": "brewing"}).json()
    assert brewing_set["picks"] == []


def test_missing_staples():
    deck = "1 Swap Guy *CMDR*\n1 Sol Ring"
    r = client.post("/api/staples", json={"decklist": deck, "min_pct": 40})
    assert r.status_code == 200, r.text
    body = r.json()
    # Sol Ring is in the deck, Cheap Trick is under 40%; Mind Stone has the higher synergy.
    assert [c["name"] for c in body["cards"]] == ["Mind Stone", "Mana Crypt"]
    assert body["budget_max_usd"] is None and not body["cards"][1]["over_budget"]

    # Default threshold (30%) and Brewing flags pricey staples instead of hiding them.
    body = client.post("/api/staples", json={"decklist": deck, "status": "brewing"}).json()
    assert body["min_inclusion_pct"] == 30
    flags = {c["name"]: c["over_budget"] for c in body["cards"]}
    assert flags == {"Cheap Trick": False, "Mind Stone": False, "Mana Crypt": True}
    assert client.post("/api/staples", json={"decklist": "1 Sol Ring"}).status_code == 400


def test_budget_swaps():
    deck = "1 Swap Guy *CMDR*\n1 Mana Crypt\n1 Pricey Bolt\n1 Sol Ring"
    r = client.post("/api/swaps", json={"decklist": deck})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["budget_max_usd"] == 5.0
    cards = {c["name"]: c for c in body["cards"]}
    assert list(cards) == ["Mana Crypt", "Pricey Bolt"]   # Sol Ring ($1.49) is under the cap
    crypt = cards["Mana Crypt"]
    assert crypt["roles"] == ["ramp"]
    assert [s["name"] for s in crypt["swaps"]] == ["Mind Stone"]   # same job; Cheap Trick isn't ramp
    assert crypt["saves"] == 149.5
    assert cards["Pricey Bolt"]["swaps"] == []   # nothing cheap on the page does removal
    assert body["potential_savings"] == 149.5 and body["over_cap_total"] == 190.0


def job(path, body):
    """Start a background job and wait for it, like the UI does."""
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    for _ in range(200):
        j = client.get(f"/api/jobs/{r.json()['id']}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.02)
    raise AssertionError("job never finished")


def test_collection_import_and_need_to_buy():
    from backend import collection
    collection._path().unlink(missing_ok=True)
    j = job("/api/collection/import", {"url": "https://archidekt.com/collection/v2/99"})
    assert j["status"] == "done", j
    col = j["result"]["collection"]
    assert (col["source"], col["unique"], col["total"]) == ("https://archidekt.com/collection/v2/99", 3, 4)
    assert j["done"] == 3 and j["total"] == 3
    assert slept[-1] == 3.0   # first page got a 429; waited the Retry-After and carried on
    err = job("/api/collection/import", {"url": "https://archidekt.com/collection/v2/13"})
    assert err["status"] == "error" and "private" in err["error"]
    assert client.post("/api/collection/import", json={"url": "https://example.com/x"}).status_code == 400

    # Username import pulls deck 42 (Sol Ring Guy + Sol Ring) in as Built.
    lib = job("/api/collection/decks/import", {"username": "https://archidekt.com/u/wmhunter96"})["result"]
    assert lib["imported"] == 1
    assert [(d["id"], d["status"], d["commanders"]) for d in lib["decks"]] == [("archidekt-42", "built", ["Sol Ring Guy"])]
    assert job("/api/collection/decks/import", {"username": "nobody"})["status"] == "error"
    # The older search endpoint is still tried when v3 finds nothing.
    assert job("/api/collection/decks/import", {"username": "oldapi"})["result"]["unchanged"] == 1
    # Unchanged on Archidekt, so a re-import doesn't fetch it again.
    again = job("/api/collection/decks/import", {"username": "wmhunter96"})["result"]
    assert again["imported"] == 0 and again["unchanged"] == 1

    check = client.post("/api/collection/check", json={"decklist": "1 Swap Guy *CMDR*\n1 Sol Ring\n1 Mind Stone"}).json()
    rows = {x["name"]: x for x in check["rows"]}
    assert rows["Sol Ring"]["state"] == "in_use" and rows["Sol Ring"]["used_in"] == [{"deck": "Imported", "qty": 1}]
    assert rows["Mind Stone"]["state"] == "have" and rows["Swap Guy"]["state"] == "missing"

    # Flip the deck to Brewing and the Sol Ring is free again.
    client.post("/api/collection/decks/archidekt-42", json={"status": "brewing"})
    check = client.post("/api/collection/check", json={"decklist": "1 Swap Guy *CMDR*\n1 Sol Ring"}).json()
    assert {x["name"]: x["state"] for x in check["rows"]}["Sol Ring"] == "have"

    # Saving the pasted deck, then a CSV import replaces the collection.
    saved = client.post("/api/collection/decks", json={"decklist": "1 Swap Guy *CMDR*\n1 Sol Ring", "status": "built"}).json()
    assert any(d["name"] == "Swap Guy" and d["status"] == "built" for d in saved["decks"])
    csv = client.post("/api/collection/import", json={"text": "Quantity,Name\n3,Sol Ring\n"}).json()
    assert csv["collection"]["total"] == 3
    assert client.delete(f"/api/collection/decks/{saved['saved']}").json()["decks"][0]["id"] == "archidekt-42"


def test_archidekt_rate_limit_gives_up_politely():
    from backend import collection
    collection._path().unlink(missing_ok=True)
    flaky["deck"] = 99   # every deck fetch is refused
    try:
        j = job("/api/collection/decks/import", {"username": "wmhunter96"})
        assert j["status"] == "error" and "press Import decks again" in j["error"]
        r = client.post("/api/import", json={"url": "https://archidekt.com/decks/42/x"})
        assert r.status_code == 400 and "slow down" in r.json()["detail"]
        assert slept[-4:] == [2.0, 4.0, 8.0, 16.0]   # backed off before giving up
    finally:
        flaky["deck"] = 0
    assert job("/api/collection/decks/import", {"username": "wmhunter96"})["result"]["imported"] == 1
