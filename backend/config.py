import os
import yaml
from pathlib import Path

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/config/settings.yaml")
CACHE_DIR = os.environ.get("CACHE_DIR", str(Path(CONFIG_PATH).parent / "cache"))


def load_settings() -> dict:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return _defaults()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    defaults = _defaults()
    # Deep merge defaults <- file values
    for section, values in defaults.items():
        if section not in data:
            data[section] = values
        elif isinstance(values, dict):
            for k, v in values.items():
                data[section].setdefault(k, v)
    return data


def save_settings(settings: dict) -> None:
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(settings, f, default_flow_style=False)


def _defaults() -> dict:
    return {
        "pricing": {
            # How long Scryfall printings (which carry TCGplayer market prices)
            # and the Card Kingdom price list are cached before re-fetching.
            # Both sources only update about once a day.
            "cache_hours": 12,
            # Basic lands are skipped by default — nobody price-shops Forests.
            "skip_basic_lands": True,
            # When both stores are within a cent, who wins: "cardkingdom" or "tcgplayer".
            "tie_goes_to": "cardkingdom",
        },
        "brewing": {
            # Decks marked "Brewing" only get suggestions at or under this
            # price per card (cheapest of Card Kingdom in stock / TCGplayer market).
            "budget_max_usd": 5.0,
            # Decks marked "Built" get Brew Ideas from this many of the newest sets.
            "recent_sets": 3,
        },
        "edhrec": {
            # Hide EDHREC suggestions that appear in fewer than this % of the
            # commander's decks (0 = show everything).
            "min_inclusion_pct": 0,
            # "Missing staples" lists cards at least this % of the commander's
            # decks run that yours doesn't.
            "staples_min_pct": 30,
        },
    }
