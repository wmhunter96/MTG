from backend.setpicks import score

CARDS = [
    {"name": "Green Bomb", "color_identity": ["G"], "rarity": "mythic", "type_line": "Creature", "usd": 5.0, "image": None, "scryfall_url": None},
    {"name": "Blue Thing", "color_identity": ["U"], "rarity": "rare", "type_line": "Instant", "usd": 1.0, "image": None, "scryfall_url": None},
    {"name": "Colorless Rock", "color_identity": [], "rarity": "uncommon", "type_line": "Artifact", "usd": 0.5, "image": None, "scryfall_url": None},
    {"name": "Owned Elf", "color_identity": ["G"], "rarity": "common", "type_line": "Creature", "usd": 0.1, "image": None, "scryfall_url": None},
    {"name": "Unplayed", "color_identity": ["G"], "rarity": "common", "type_line": "Creature", "usd": 0.1, "image": None, "scryfall_url": None},
]
CMDR = [{"name": "Green Bomb", "num_decks": 300, "potential_decks": 1000, "synergy": 0.25},
        {"name": "Owned Elf", "num_decks": 500, "potential_decks": 1000, "synergy": 0.4},
        {"name": "Not In Set", "num_decks": 900, "potential_decks": 1000, "synergy": 0.5}]
SETV = [{"name": "Colorless Rock", "num_decks": 50000, "potential_decks": 1000000},
        {"name": "Blue Thing", "num_decks": 90000, "potential_decks": 1000000}]


def test_commander_hits_rank_first_and_colors_filter():
    picks = score(CARDS, CMDR, SETV, {"G", "B"}, ["Owned Elf"])
    names = [p["name"] for p in picks]
    assert names == ["Owned Elf", "Green Bomb", "Colorless Rock"]   # Blue filtered, Unplayed dropped
    owned = picks[0]
    assert owned["in_deck"] and owned["source"] == "commander" and owned["impact"] == 90.0
    assert picks[1]["why"] == "In 30% of this commander's decks, +25% synergy"
    assert picks[2]["source"] == "popular" and picks[2]["impact"] == 2.5


def test_no_commander_uses_popularity_only():
    picks = score(CARDS, [], SETV, None, [])
    assert [p["name"] for p in picks] == ["Blue Thing", "Colorless Rock"]
