from backend.edhrec import commander_slug, slugify, suggestions


def test_slugs():
    assert slugify("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"
    assert slugify("Lim-Dûl the Necromancer") == "lim-dul-the-necromancer"
    assert slugify("Esika, God of the Tree // The Prismatic Bridge") == "esika-god-of-the-tree"
    assert commander_slug(["Tymna the Weaver", "Kraum, Ludevic's Opus"]) == "kraum-ludevics-opus-tymna-the-weaver"


PAGE = {"path": "commanders/atraxa-praetors-voice", "data": {
    "header": "Atraxa, Praetors' Voice (Commander)",
    "container": {"json_dict": {"cardlists": [
        {"header": "High Synergy Cards", "tag": "highsynergycards", "cardviews": [
            {"name": "Doubling Season", "url": "/cards/doubling-season", "synergy": 0.41, "num_decks": 9000, "potential_decks": 45000},
            {"name": "Sol Ring", "url": "/cards/sol-ring", "synergy": 0.01, "num_decks": 44000, "potential_decks": 45000},
        ]},
        {"header": "Top Cards", "tag": "topcards", "cardviews": [
            {"name": "Rare Thing", "url": "/cards/rare-thing", "synergy": 0.02, "num_decks": 100, "potential_decks": 45000},
        ]},
        {"header": "Lands", "tag": "lands", "cardviews": [
            {"name": "Command Tower", "url": "/cards/command-tower", "synergy": 0, "num_decks": 45000, "potential_decks": 45000},
        ]},
    ]}},
}}


def test_suggestions_skip_owned_cards_and_low_inclusion():
    s = suggestions(PAGE, ["Sol Ring", "command tower"], min_inclusion_pct=1)
    assert s["url"] == "https://edhrec.com/commanders/atraxa-praetors-voice"
    assert [l["header"] for l in s["lists"]] == ["High Synergy Cards"]
    card = s["lists"][0]["cards"][0]
    assert card == {"name": "Doubling Season", "synergy_pct": 41, "inclusion_pct": 20.0,
                    "num_decks": 9000, "url": "https://edhrec.com/cards/doubling-season"}
    assert s["missing_count"] == 1
