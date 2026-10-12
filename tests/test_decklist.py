from backend.decklist import normalize_name, parse_decklist


def test_formats_and_sections():
    deck = parse_decklist("""
Commander
1 Atraxa, Praetors' Voice

Deck
1 Sol Ring
1x Arcane Signet (CMR) 297
2 Swords to Plowshares (STA) 10 *F*
1 Cultivate [Ramp]
1 Rampant Growth #ramp
Command Tower
// Lands
10 Forest

Maybeboard
1 Doubling Season
""")
    names = {c.name: c for c in deck.cards}
    assert deck.commanders == ["Atraxa, Praetors' Voice"]
    assert names["Arcane Signet"].qty == 1
    assert names["Swords to Plowshares"].qty == 2
    assert "Cultivate" in names and "Rampant Growth" in names
    assert names["Command Tower"].qty == 1
    assert names["Forest"].qty == 10
    assert "Doubling Season" not in names
    assert not names["Sol Ring"].commander


def test_cmdr_marker_and_merging():
    deck = parse_decklist("1 Kraum, Ludevic's Opus *CMDR*\n1 Tymna the Weaver *CMDR*\n1 Sol Ring\n1 sol ring")
    assert deck.commanders == ["Kraum, Ludevic's Opus", "Tymna the Weaver"]
    assert [c.qty for c in deck.cards if c.name == "Sol Ring"] == [2]


def test_normalize_name_uses_front_face():
    assert normalize_name("Delver of Secrets // Insectile Aberration") == normalize_name("delver of secrets")
    assert normalize_name("Atraxa, Praetors' Voice") == "atraxa praetors voice"
