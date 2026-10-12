from backend import collection


def setup_function():
    collection._path().unlink(missing_ok=True)


def test_parse_archidekt_csv_export():
    text = ('Quantity,Name,Finish,Condition,Edition Name\n'
            '2,Sol Ring,Normal,NM,Commander Legends\n'
            '1,"Lathril, Blade of the Elves",Foil,NM,Kaldheim Commander\n'
            '1,Sol Ring,Foil,LP,Commander Masters\n')
    cards = collection.parse_collection_text(text)
    assert cards["sol ring"] == {"name": "Sol Ring", "qty": 3}
    assert cards["lathril blade of the elves"]["qty"] == 1


def test_parse_plain_list_and_moxfield_csv():
    assert collection.parse_collection_text("2 Sol Ring\nArcane Signet")["arcane signet"]["qty"] == 1
    mox = '"Count","Tradelist Count","Name","Edition"\n"4","0","Llanowar Elves","m19"\n'
    assert collection.parse_collection_text(mox)["llanowar elves"]["qty"] == 4


def test_parse_archidekt_collection_page():
    page = {"count": 2, "next": None, "results": [
        {"quantity": 2, "card": {"oracleCard": {"name": "Sol Ring"}}},
        {"quantity": 1, "card": {"name": "Arcane Signet"}}]}
    rows, nxt, count = collection.parse_archidekt_collection(page)
    assert rows == [(2, "Sol Ring"), (1, "Arcane Signet")] and nxt is None and count == 2


def test_refs():
    assert collection.collection_id("https://archidekt.com/collection/v2/12345") == "12345"
    assert collection.collection_id("777") == "777"
    assert collection.collection_id("https://example.com/x") is None
    assert collection.username("https://archidekt.com/u/wmhunter96") == "wmhunter96"
    assert collection.username("@wmhunter96") == "wmhunter96"


def _library():
    collection.import_collection(collection.parse_collection_text(
        "1 Sol Ring\n2 Arcane Signet\n1 Llanowar Elves\n1 Swords to Plowshares"), "test")
    collection.upsert_decks([
        {"id": "a", "name": "Valgavoth", "commanders": ["Valgavoth, Harrower of Souls"],
         "decklist": "1 Valgavoth, Harrower of Souls *CMDR*\n1 Sol Ring\n1 Arcane Signet"},
        {"id": "b", "name": "Elves", "commanders": ["Lathril, Blade of the Elves"],
         "decklist": "1 Lathril, Blade of the Elves *CMDR*\n1 Sol Ring\n1 Llanowar Elves\n30 Forest"},
        {"id": "c", "name": "Someday", "commanders": ["Atraxa, Praetors' Voice"], "status": "brewing",
         "decklist": "1 Swords to Plowshares"},
    ])


def test_check_flags_cards_used_in_other_built_decks():
    _library()
    deck = "1 Kenrith, the Returned King *CMDR*\n1 Sol Ring\n1 Arcane Signet\n1 Swords to Plowshares\n1 Mana Crypt\n5 Plains"
    r = collection.check_deck(deck, [])
    rows = {x["name"]: x for x in r["rows"]}
    # Your one Sol Ring is in both Built decks: buy one.
    assert rows["Sol Ring"]["state"] == "in_use" and rows["Sol Ring"]["need"] == 1
    assert [u["deck"] for u in rows["Sol Ring"]["used_in"]] == ["Valgavoth", "Elves"]
    # Two Signets, one in Valgavoth: one is free.
    assert rows["Arcane Signet"]["state"] == "have" and rows["Arcane Signet"]["free"] == 1
    # Brewing decks don't hold cards.
    assert rows["Swords to Plowshares"]["state"] == "have"
    assert rows["Mana Crypt"]["state"] == "missing"
    assert rows["Kenrith, the Returned King"]["state"] == "missing"
    assert "Plains" not in rows and r["skipped_basics"] == 1
    assert r["in_use"] == 1 and r["to_buy"] == 3 and r["built_decks"] == 2
    assert r["rows"][0]["name"] == "Sol Ring"   # in-use cards first


def test_check_ignores_the_deck_itself():
    _library()
    r = collection.check_deck("1 Sol Ring\n1 Llanowar Elves", ["Lathril, Blade of the Elves"])
    rows = {x["name"]: x for x in r["rows"]}
    assert r["matched_deck"]["name"] == "Elves"
    assert rows["Llanowar Elves"]["state"] == "have"
    assert [u["deck"] for u in rows["Sol Ring"]["used_in"]] == ["Valgavoth"]


def test_status_kept_on_reimport_and_conflicts():
    _library()
    collection.update_deck("b", status="brewing")
    collection.upsert_decks([{"id": "b", "name": "Elves v2", "commanders": [], "decklist": "1 Sol Ring"}])
    s = collection.summary()
    elves = next(d for d in s["decks"] if d["id"] == "b")
    assert elves["status"] == "brewing" and elves["name"] == "Elves v2"
    assert s["conflicts"] == []   # Elves is Brewing now, so nobody fights over Sol Ring
    collection.update_deck("b", status="built")
    c = collection.summary()["conflicts"]
    assert [(x["name"], x["owned"], x["needed"]) for x in c] == [("Sol Ring", 1, 2)]
