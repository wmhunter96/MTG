from backend.decklist import parse_decklist
from backend.importer import parse_archidekt, parse_moxfield, to_text


def test_moxfield_v3():
    data = {"name": "Elves", "boards": {
        "commanders": {"cards": {"x": {"quantity": 1, "card": {"name": "Lathril, Blade of the Elves"}}}},
        "mainboard": {"cards": {"a": {"quantity": 1, "card": {"name": "Llanowar Elves"}},
                                "b": {"quantity": 30, "card": {"name": "Forest"}}}},
        "maybeboard": {"cards": {"m": {"quantity": 1, "card": {"name": "Craterhoof Behemoth"}}}},
    }}
    name, cmdrs, cards = parse_moxfield(data)
    assert name == "Elves" and cmdrs == [(1, "Lathril, Blade of the Elves")]
    assert (30, "Forest") in cards and all(n != "Craterhoof Behemoth" for _, n in cards)
    deck = parse_decklist(to_text(name, cmdrs, cards))
    assert deck.commanders == ["Lathril, Blade of the Elves"]
    assert sum(c.qty for c in deck.cards) == 32


def test_moxfield_v2():
    data = {"name": "Old", "commanders": {"Atraxa, Praetors' Voice": {"quantity": 1, "card": {"name": "Atraxa, Praetors' Voice"}}},
            "mainboard": {"Sol Ring": {"quantity": 1}}}
    _, cmdrs, cards = parse_moxfield(data)
    assert cmdrs == [(1, "Atraxa, Praetors' Voice")] and cards == [(1, "Sol Ring")]


def test_archidekt():
    data = {"name": "Rakdos", "categories": [{"name": "Maybeboard", "includedInDeck": False},
                                             {"name": "Ramp", "includedInDeck": True}],
            "cards": [
                {"quantity": 1, "categories": ["Commander"], "card": {"oracleCard": {"name": "Prosper, Tome-Bound"}}},
                {"quantity": 1, "categories": ["Ramp"], "card": {"oracleCard": {"name": "Sol Ring"}}},
                {"quantity": 1, "categories": ["Maybeboard"], "card": {"oracleCard": {"name": "Dark Ritual"}}},
                {"quantity": 2, "categories": [], "card": {"oracleCard": {"name": "Swamp"}}},
            ]}
    name, cmdrs, cards = parse_archidekt(data)
    assert cmdrs == [(1, "Prosper, Tome-Bound")]
    assert cards == [(1, "Sol Ring"), (2, "Swamp")]
