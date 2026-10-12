"""End-to-end through the FastAPI app with every outbound site mocked."""

import json
import time

import httpx
from fastapi.testclient import TestClient

from backend import http
from backend.main import app

SCRY = {
    "sol ring": {"name": "Sol Ring", "oracle_id": "o-sol", "type_line": "Artifact"},
    "mana crypt": {"name": "Mana Crypt", "oracle_id": "o-crypt", "type_line": "Artifact", "prices": {"usd": "150.00"}},
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
    {"quantity": 1, "categories": ["Ramp"], "card": {"oracleCard": {"name": "Sol Ring"}}}]}

calls = []


def handler(req: httpx.Request) -> httpx.Response:
    calls.append(str(req.url))
    host, path = req.url.host, req.url.path
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
    if host == "json.edhrec.com" and path == "/pages/sets/new.json":
        return httpx.Response(200, json=EDH_SET)
    if host == "api.scryfall.com" and path == "/sets":
        return httpx.Response(200, json={"data": SETS})
    if host == "archidekt.com" and path == "/api/decks/42/":
        return httpx.Response(200, json=ARCHIDEKT)
    return httpx.Response(404)


http._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
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
