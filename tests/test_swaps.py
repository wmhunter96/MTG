from backend.edhrec import staples
from backend.swaps import card_type, rank, roles


def test_roles_from_rules_text():
    assert roles("Mana Crypt", "Artifact", "At the beginning of your upkeep, flip a coin.\n{T}: Add {C}{C}.") == ["ramp"]
    assert roles("Rhystic Study", "Enchantment",
                 "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.") == ["draw"]
    assert roles("Swords to Plowshares", "Instant",
                 "Exile target creature. Its controller gains life equal to its power.") == ["removal"]
    assert roles("Cyclonic Rift", "Instant", "Return target nonland permanent you don't control to its owner's hand.") == ["removal"]
    assert roles("Damnation", "Sorcery", "Destroy all creatures. They can't be regenerated.") == ["wipe"]
    assert roles("Demonic Tutor", "Sorcery", "Search your library for a card, put that card into your hand, then shuffle.") == ["tutor"]
    assert roles("Cultivate", "Sorcery", "Search your library for up to two basic land cards, reveal those cards, "
                 "put one onto the battlefield tapped and the other into your hand, then shuffle.") == ["ramp"]
    assert roles("Watery Grave", "Land — Island Swamp", "({T}: Add {U} or {B}.)") == ["land"]
    # Reminder text and the card's own name don't count.
    assert roles("Gravecrawler", "Creature — Zombie", "Gravecrawler can't block.\nYou may cast ~ from your graveyard.") == ["recursion"]


def test_card_type_prefers_creature():
    assert card_type("Artifact Creature — Golem") == "Creature"
    assert card_type("Legendary Land") == "Land"
    assert card_type("Instant // Sorcery") == "Instant"


def cand(name, type_, roles_, score, cmc=2, price=1.0):
    return {"name": name, "type": type_, "roles": roles_, "cmc": cmc, "score": score, "price": price,
            "inclusion_pct": score, "synergy_pct": 0, "url": ""}


def test_rank_prefers_same_role_then_type_then_popularity():
    target = {"name": "Mana Crypt", "type": "Artifact", "roles": ["ramp"], "cmc": 0, "price": 150}
    picks = rank(target, [
        cand("Rampant Growth", "Sorcery", ["ramp"], 60),
        cand("Mind Stone", "Artifact", ["ramp"], 40),
        cand("Arcane Signet", "Artifact", ["ramp"], 70),
        cand("Big Draw", "Artifact", ["draw"], 99),
        cand("Command Tower", "Land", ["land"], 99),
    ])
    assert [p["name"] for p in picks] == ["Arcane Signet", "Mind Stone", "Rampant Growth"]
    assert picks[0]["why"].startswith("also ramp")


def test_lands_only_swap_for_lands():
    target = {"name": "Watery Grave", "type": "Land", "roles": ["land"], "cmc": 0, "price": 20}
    picks = rank(target, [cand("Mind Stone", "Artifact", ["ramp"], 50), cand("Dimir Guildgate", "Land", ["land"], 10)])
    assert [p["name"] for p in picks] == ["Dimir Guildgate"]


def test_staples_keeps_missing_cards_above_threshold_sorted_by_synergy():
    page = {"path": "commanders/x", "data": {"header": "X", "container": {"json_dict": {"cardlists": [
        {"header": "Top Cards", "cardviews": [
            {"name": "Sol Ring", "num_decks": 95, "potential_decks": 100, "synergy": 0},
            {"name": "Owned", "num_decks": 80, "potential_decks": 100, "synergy": 0.3},
            {"name": "Rare Pick", "num_decks": 10, "potential_decks": 100, "synergy": 0.6}]},
        {"header": "High Synergy", "cardviews": [
            {"name": "Combo Piece", "num_decks": 40, "potential_decks": 100, "synergy": 0.35},
            {"name": "Sol Ring", "num_decks": 95, "potential_decks": 100, "synergy": 0}]}]}}}}
    out = staples(page, ["Owned"], 30)
    assert [c["name"] for c in out["cards"]] == ["Combo Piece", "Sol Ring"]
    assert out["cards"][0]["list"] == "High Synergy" and out["min_inclusion_pct"] == 30
