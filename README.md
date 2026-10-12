# MTG Brewmaster

A small, whimsical self-hosted web app for Magic: The Gathering Commander players, built to run as a Docker container on Unraid (same setup as [DJDownload](https://github.com/wmhunter96/DJDownload)).

---

## Features

### Bring your deck

Paste a list, or drop in a **Moxfield** or **Archidekt** deck link and press **Fetch** (the deck must be public). The deck and commander are shared by every tab and remembered in your browser. If Moxfield refuses the request (it sometimes blocks servers), use Moxfield's *Export → Text* and paste it instead.

### Built or Brewing

Each deck has a **Built / Brewing** switch (remembered per commander in your browser):

- **🏰 Built** (you own the deck): Brew Ideas shows the **best new cards from the newest few sets** (3 by default) as a card grid, ranked the same way as the New Sets tab. You can switch it to **Missing staples** or every EDHREC suggestion.
- **⚗ Brewing** (still buying): Brew Ideas and New Sets only suggest cards at or under your **max price per card** ($5 by default), using the cheaper of Card Kingdom's lowest in-stock price and TCGplayer's market price. Bargains flags deck cards that cost more than the cap, and Brew Ideas opens on **Cheaper swaps** for them.

Both numbers live in Settings.

### Missing staples (Brew Ideas tab)

Cards that at least **30%** of your commander's EDHREC decks run (change the % right there or in Settings) and yours doesn't, ranked by synergy, with prices. Brewing decks see staples over the price cap too, with the price in red, since a staple is worth knowing about even when it's pricey.

### Cheaper swaps (Brew Ideas tab, Brewing decks)

Every card in the deck over the Brewing price cap gets up to **3 cheaper replacements that do the same job**:

- Candidates come from your commander's EDHREC page and its Budget page, minus cards already in the deck, at or under the cap
- Each card is tagged by what it does (ramp, card draw, removal, board wipe, counterspell, tutor, recursion, protection, tokens, land) from its rules text; swaps must share a job with the card they replace, and lands only swap for lands
- Ties go to the same card type and mana value, then to how many of the commander's decks run it
- Totals show what the over-cap cards cost and how much the cheapest swap for each would save
- Bargains has a **Find cheaper swaps** button when it flags cards over the cap

### What do I need to buy? (Collection tab)

Import your collection and your decks, and the app tells you which cards in the deck you're working on you actually have to buy, including cards you own that are **already sleeved up in another Built deck**:

- **Collection**: paste your Archidekt collection link (it must be public) and press **Import**, or paste / upload a CSV export (Archidekt, Moxfield, Deckbox, anything with quantity and name columns) or a plain `2 Sol Ring` list. Count every copy you own, including the ones in decks. Importing again replaces the old import.
- **Decks**: enter your Archidekt username and press **Import decks** to pull in every public deck as 🏰 Built. Flip any that are still on paper to ⚗ Brewing; re-importing refreshes the lists and keeps your choices. **Save the deck above** adds whatever deck is in the editor. Built decks hold their cards; Brewing decks don't.
- **What do I need to buy?** checks the deck in the editor: cards you have a spare copy of, cards you own but whose copies are all in other Built decks (naming those decks), and cards you don't own. If the deck is one of your saved decks (same commander), its own cards aren't counted against it. Basic lands are skipped.
- **Price the ones I need** sends just the buy list to Bargains.
- **Shared between Built decks** lists cards your Built decks together run more copies of than you own.

The collection and saved decks live in `/config/collection.json`. Archidekt has no official API, so if a link stops importing, use the CSV export.

### Best price per card (Bargains tab)

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

### Cards you might be missing (Brew Ideas tab)

Enter your commander (or let the app pick it up from the list's Commander section / `*CMDR*` marker) and it pulls that commander's [EDHREC](https://edhrec.com) page and shows every recommended card **your deck doesn't already run**:

- Grouped the way EDHREC groups them (High Synergy, Top Cards, Creatures, Ramp, Lands, ...)
- Sort by **synergy** or by **% of decks** that run it
- Switch to EDHREC's **Budget**, **Expensive**, or any **theme** page (`tokens`, `infect`, ...)
- **Only cards I'm missing** toggle (on by default) hides what the deck already runs
- Partner commanders: enter both separated by `+`
- Tick suggestions and hit **Price selected** to send them straight to the price checker
- Hover a card name to see its image

### High-impact cards from a new set (New Sets tab)

Pick a set (newest first) and get its best cards for your deck, as a grid of card images:

- Only cards in your commander's **color identity**
- Ranked first by how often **your commander's** EDHREC decks already run the card (inclusion % + synergy), then by how widely the card is played across **all** EDHREC decks that could run it (from EDHREC's set page)
- **Only cards I'm missing** toggle hides cards already in the deck
- Tick cards and hit **Price picked** to send them to Bargains
- With no commander, it ranks the whole set by EDHREC popularity

---

## Configuration

Settings tab (saved to `/config/settings.yaml`):

- **Refresh prices every (hours)**: how long Scryfall printings and the CK price list are cached (default 12)
- **When prices tie**: Card Kingdom (default) or TCGplayer
- **Skip basic lands**
- **Brewing decks: max price per card** (default $5)
- **Built decks: look at the newest N sets** (default 3)
- **Hide EDHREC suggestions** below a % of decks

Cached data lives in `/config/cache` and survives container updates. **Clear cached prices** forces a fresh download.

The app needs outbound internet access to `api.scryfall.com`, `api.cardkingdom.com`, `json.edhrec.com`, and (for deck links) `api2.moxfield.com` and `archidekt.com`.

---

## Deploying on Unraid

Every push to `main` builds and publishes the image to `ghcr.io/wmhunter96/mtg:latest` via [GitHub Actions](.github/workflows/docker-publish.yml). An [Unraid template](unraid/mtg-brewmaster.xml) is included so the container installs and updates through the normal Docker UI.

**One-time setup:**

1. On GitHub, go to the repo's **Packages** tab → `mtg` package → **Package settings** → change visibility to **Public**. (GHCR packages default to private, and a private image needs a login on the Unraid side to pull.)
2. On Unraid: **Docker** tab → **Template Repositories** → add `https://github.com/wmhunter96/MTG` → **Save**.
3. Go to **Docker** → **Add Container** → template dropdown → **MTG-Brewmaster**. The web UI defaults to host port **8010** so it doesn't clash with DJDownload on 8000. **Apply**.

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
