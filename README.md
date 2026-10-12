# MTG Toolkit

A small self-hosted web app for Magic: The Gathering, built to run as a Docker container on Unraid (same setup as [DJDownload](https://github.com/wmhunter96/DJDownload)).

---

## Features

### Best price per card (Prices tab)

Paste a decklist and get the cheapest copy of every card across **Card Kingdom** and **TCGplayer**:

- Cheapest **Near Mint, non-foil** copy of **any paper printing** wins
- An **out-of-stock** Card Kingdom listing never wins
- TCGplayer price = **TCGplayer market price** for that printing (via [Scryfall](https://scryfall.com/docs/api))
- Card Kingdom price = CK's own published retail price list (NM price + stock per printing), downloaded once and refreshed every 12 hours by default
- Totals for **best split**, **all Card Kingdom**, and **all TCGplayer**, plus how much each card saves
- **Copy CK list / Copy TCGplayer list** buttons give you `1 Card Name` lines for each store's half of the split, ready to paste into CK's deck builder or TCGplayer's mass entry
- **CSV export**
- Basic lands are skipped (toggle in Settings); collector-only printings (gold-bordered, Collectors' Edition, oversized) are excluded

Accepts Moxfield, Archidekt and Arena exports or plain lists: `1 Sol Ring`, `1x Sol Ring (CMR) 472 *F*`, `Sol Ring`, section headers, `*CMDR*` markers, `[Category]` and `#tag` suffixes. Maybeboard sections are ignored.

### Cards you might be missing (EDHREC tab)

Enter your commander (or let the app pick it up from the list's Commander section / `*CMDR*` marker) and it pulls that commander's [EDHREC](https://edhrec.com) page and shows every recommended card **your deck doesn't already run**:

- Grouped the way EDHREC groups them (High Synergy, Top Cards, Creatures, Ramp, Lands, ...)
- Sort by **synergy** or by **% of decks** that run it
- Switch to EDHREC's **Budget**, **Expensive**, or any **theme** page (`tokens`, `infect`, ...)
- Partner commanders: enter both separated by `+`
- Tick suggestions and hit **Price selected** to send them straight to the price checker
- Hover a card name to see its image

---

## Configuration

Settings tab (saved to `/config/settings.yaml`):

- **Refresh prices every (hours)**: how long Scryfall printings and the CK price list are cached (default 12)
- **When prices tie**: Card Kingdom (default) or TCGplayer
- **Skip basic lands**
- **Hide EDHREC suggestions** below a % of decks

Cached data lives in `/config/cache` and survives container updates. **Clear cached prices** forces a fresh download.

The app needs outbound internet access to `api.scryfall.com`, `api.cardkingdom.com` and `json.edhrec.com`.

---

## Deploying on Unraid

Every push to `main` builds and publishes the image to `ghcr.io/wmhunter96/mtg:latest` via [GitHub Actions](.github/workflows/docker-publish.yml). An [Unraid template](unraid/mtg-toolkit.xml) is included so the container installs and updates through the normal Docker UI.

**One-time setup:**

1. On GitHub, go to the repo's **Packages** tab → `mtg` package → **Package settings** → change visibility to **Public**. (GHCR packages default to private, and a private image needs a login on the Unraid side to pull.)
2. On Unraid: **Docker** tab → **Template Repositories** → add `https://github.com/wmhunter96/MTG` → **Save**.
3. Go to **Docker** → **Add Container** → template dropdown → **MTG-Toolkit**. The web UI defaults to host port **8010** so it doesn't clash with DJDownload on 8000. **Apply**.

**After that:** any new push to `main` refreshes the `latest` tag, and Unraid's normal update check offers the update.

### Running elsewhere

```sh
docker compose up -d --build    # then open http://localhost:8010
```

### Development

```sh
pip install -r requirements-dev.txt
pytest
uvicorn backend.main:app --reload
```
