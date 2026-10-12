"""End-to-end through the FastAPI app with every outbound site mocked."""

import json
import time

import httpx
from fastapi.testclient import TestClient

from backend import http
from backend.main import app

SCRY = {
    "sol ring": {"name": "Sol Ring", "oracle_id": "o-sol", "type_line": "Artifact"},
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
        {"name": "Mana Crypt", "url": "/cards/mana-crypt", "synergy": 0.1, "num_decks": 5, "potential_decks": 10}]}]}}}

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
        oid = req.url.params["q"].split()[0].split(":")[1]
        return httpx.Response(200, json={"data": PRINTS.get(oid, []), "has_more": False})
    if host == "api.cardkingdom.com":
        return httpx.Response(200, json=CK)
    if host == "json.edhrec.com" and path == "/pages/commanders/sol-ring-guy.json":
        return httpx.Response(200, json=EDH)
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
    names = [c["name"] for l in r.json()["lists"] for c in l["cards"]]
    assert names == ["Mana Crypt"]
    assert client.post("/api/edhrec", json={"commanders": ["Nobody Here"]}).status_code == 404


def test_settings_roundtrip_and_index():
    s = client.post("/api/settings", json={"cache_hours": 6, "skip_basic_lands": False,
                                           "tie_goes_to": "tcgplayer", "min_inclusion_pct": 5}).json()
    assert s["pricing"]["cache_hours"] == 6 and s["edhrec"]["min_inclusion_pct"] == 5
    assert client.get("/api/settings").json()["pricing"]["tie_goes_to"] == "tcgplayer"
    assert "MTG Toolkit" in client.get("/").text
