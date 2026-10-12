"""
main.py — MTG Brewmaster FastAPI server.

Endpoints:
  GET  /                        → serve web UI
  GET  /api/settings            → return current config
  POST /api/settings            → update config
  POST /api/parse               → parse a pasted decklist (cards + detected commanders)
  POST /api/prices/jobs         → start a best-price lookup for a decklist
  GET  /api/prices/jobs/{id}    → progress + results of a price lookup
  POST /api/edhrec              → EDHREC cards the deck is missing for its commander
  POST /api/import              → fetch a decklist from a Moxfield / Archidekt link
  GET  /api/sets                → recent paper sets for the New Sets picker
  POST /api/setpicks            → high-impact cards from one set for this deck
  POST /api/recentpicks         → high-impact cards from the newest few sets (Built decks)
  POST /api/staples             → EDHREC staples (≥ N% of the commander's decks) the deck is missing
  POST /api/swaps               → cheaper same-role replacements for cards over the Brewing cap
  GET  /api/collection          → collection summary, deck library, cards Built decks fight over
  POST /api/collection/import   → replace the collection from an Archidekt link or a CSV / list
  POST /api/collection/decks/import → add an Archidekt user's public decks to the library
  POST /api/collection/decks    → save a deck (link or pasted list) to the library
  POST /api/collection/decks/{id}   → change a saved deck's Built/Brewing status or name
  DELETE /api/collection/decks/{id} → remove a saved deck
  POST /api/collection/check    → which deck cards you own free, own but are in other Built decks, or lack
  POST /api/cache/clear         → drop cached Scryfall/EDHREC data and the CK price list
  GET  /api/status              → health check
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import budget, cache, cardkingdom, collection, edhrec, importer, scryfall, setpicks, swaps
from backend.config import load_settings, save_settings
from backend.decklist import parse_decklist
from backend.pricing import price_cards

app = FastAPI(title="MTG Brewmaster")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# In-memory price-lookup jobs (results are cheap to recompute from the cache).
jobs: Dict[str, dict] = {}
tasks: Dict[str, asyncio.Task] = {}
MAX_JOBS = 50


class DecklistRequest(BaseModel):
    decklist: str


class EdhrecRequest(BaseModel):
    decklist: str = ""
    commanders: List[str] = []
    variant: str = ""   # "", "budget", "expensive", or a theme slug
    status: str = ""    # "brewing" = only suggest cards under the budget cap


class StaplesRequest(BaseModel):
    decklist: str = ""
    commanders: List[str] = []
    variant: str = ""
    status: str = ""
    min_pct: Optional[float] = None   # defaults to edhrec.staples_min_pct


class SwapsRequest(BaseModel):
    decklist: str = ""
    commanders: List[str] = []


class ImportRequest(BaseModel):
    url: str


class SetPicksRequest(BaseModel):
    set: str = ""
    decklist: str = ""
    commanders: List[str] = []
    status: str = ""    # "built" | "brewing"


class CollectionImportRequest(BaseModel):
    url: str = ""    # Archidekt collection link or id
    text: str = ""   # CSV export or "1 Sol Ring" list


class UserDecksRequest(BaseModel):
    username: str
    status: str = "built"


class SaveDeckRequest(BaseModel):
    url: str = ""         # fetched when there's no decklist; otherwise just remembered
    decklist: str = ""
    name: str = ""
    commanders: List[str] = []
    status: str = "built"


class UpdateDeckRequest(BaseModel):
    status: Optional[str] = None
    name: Optional[str] = None


class CheckRequest(BaseModel):
    decklist: str = ""
    commanders: List[str] = []
    deck_id: str = ""


def _budget_cap(status: str, settings: dict) -> Optional[float]:
    """Brewing decks get the configured per-card price cap; built decks don't."""
    return float(settings["brewing"]["budget_max_usd"]) if status == "brewing" else None


class UpdateSettingsRequest(BaseModel):
    cache_hours: float = 12
    skip_basic_lands: bool = True
    tie_goes_to: str = "cardkingdom"
    min_inclusion_pct: float = 0
    staples_min_pct: float = 30
    budget_max_usd: float = 5.0
    recent_sets: int = 3


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def post_settings(req: UpdateSettingsRequest):
    if req.tie_goes_to not in ("cardkingdom", "tcgplayer"):
        raise HTTPException(400, "tie_goes_to must be cardkingdom or tcgplayer")
    settings = load_settings()
    settings["pricing"].update(
        cache_hours=max(1.0, req.cache_hours),
        skip_basic_lands=req.skip_basic_lands,
        tie_goes_to=req.tie_goes_to,
    )
    settings["edhrec"].update(min_inclusion_pct=max(0.0, req.min_inclusion_pct),
                              staples_min_pct=min(100.0, max(0.0, req.staples_min_pct)))
    settings["brewing"].update(budget_max_usd=max(0.0, req.budget_max_usd),
                               recent_sets=min(10, max(1, req.recent_sets)))
    save_settings(settings)
    return settings


# ---------------------------------------------------------------------------
# Decklists + prices
# ---------------------------------------------------------------------------

@app.post("/api/parse")
def parse(req: DecklistRequest):
    deck = parse_decklist(req.decklist)
    return {
        "cards": [c.__dict__ for c in deck.cards],
        "commanders": deck.commanders,
        "count": sum(c.qty for c in deck.cards),
    }


@app.post("/api/prices/jobs")
async def start_price_job(req: DecklistRequest):
    deck = parse_decklist(req.decklist)
    if not deck.cards:
        raise HTTPException(400, "No cards found in that list")

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "running",
        "done": 0,
        "total": len(deck.cards),
        "current": "Loading Card Kingdom price list…",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    jobs[job_id] = job
    for old in list(jobs)[:-MAX_JOBS]:
        jobs.pop(old, None)

    def progress(done: int, total: int, name: str):
        job.update(done=done, total=total, current=name)

    async def run():
        try:
            job["result"] = await price_cards(deck.cards, load_settings(), progress)
            job["status"] = "done"
        except Exception as exc:
            job["status"] = "error"
            job["error"] = str(exc) or exc.__class__.__name__

    # Keep a reference so the task isn't garbage-collected mid-run.
    tasks[job_id] = asyncio.create_task(run())
    tasks[job_id].add_done_callback(lambda _: tasks.pop(job_id, None))
    return {"id": job_id}


@app.get("/api/prices/jobs/{job_id}")
def get_price_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ---------------------------------------------------------------------------
# EDHREC
# ---------------------------------------------------------------------------

@app.post("/api/edhrec")
async def edhrec_suggestions(req: EdhrecRequest):
    deck = parse_decklist(req.decklist)
    commanders = [c for c in req.commanders if c.strip()] or deck.commanders
    if not commanders:
        raise HTTPException(400, "Enter a commander, or mark one in the list (a Commander section or *CMDR*)")
    try:
        page = await edhrec.commander_page(commanders, req.variant)
    except edhrec.EdhrecError as exc:
        raise HTTPException(404, str(exc))
    names = [c.name for c in deck.cards] + commanders
    settings = load_settings()
    min_pct = float(settings["edhrec"].get("min_inclusion_pct", 0))
    result = edhrec.suggestions(page, names, min_pct)
    cap = _budget_cap(req.status, settings)
    result["budget_max_usd"] = cap
    if cap is not None:
        for lst in result["lists"]:
            lst["cards"] = await setpicks.apply_budget(lst["cards"], settings, cap)
        result["lists"] = [l for l in result["lists"] if l["cards"]]
        result["missing_count"] = len({c["name"] for l in result["lists"] for c in l["cards"] if not c["in_deck"]})
    return result


def _deck_and_commanders(decklist: str, given: List[str]):
    deck = parse_decklist(decklist)
    commanders = [c for c in given if c.strip()] or deck.commanders
    if not commanders:
        raise HTTPException(400, "Enter a commander, or mark one in the list (a Commander section or *CMDR*)")
    return deck, commanders


@app.post("/api/staples")
async def staples(req: StaplesRequest):
    deck, commanders = _deck_and_commanders(req.decklist, req.commanders)
    settings = load_settings()
    min_pct = req.min_pct if req.min_pct is not None else float(settings["edhrec"].get("staples_min_pct", 30))
    try:
        page = await edhrec.commander_page(commanders, req.variant)
    except edhrec.EdhrecError as exc:
        raise HTTPException(404, str(exc))
    result = edhrec.staples(page, [c.name for c in deck.cards] + commanders, max(0.0, min(100.0, min_pct)))
    # Staples are worth knowing about even when pricey, so Brewing flags them instead of hiding them.
    cap = _budget_cap(req.status, settings)
    result["budget_max_usd"] = cap
    prices = await budget.budget_prices([c["name"] for c in result["cards"]], settings)
    for c in result["cards"]:
        c["budget_price"] = prices.get(c["name"])
        c["over_budget"] = cap is not None and c["budget_price"] is not None and not budget.within_budget(c["budget_price"], cap)
    return result


@app.post("/api/swaps")
async def budget_swaps(req: SwapsRequest):
    deck, commanders = _deck_and_commanders(req.decklist, req.commanders)
    settings = load_settings()
    try:
        return await swaps.budget_swaps([c.name for c in deck.cards], commanders, settings,
                                        float(settings["brewing"]["budget_max_usd"]))
    except edhrec.EdhrecError as exc:
        raise HTTPException(404, str(exc))


# ---------------------------------------------------------------------------
# Deck links + new sets
# ---------------------------------------------------------------------------

@app.post("/api/import")
async def import_deck(req: ImportRequest):
    try:
        return await importer.import_deck(req.url)
    except importer.ImportError_ as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/sets")
async def sets():
    return await scryfall.list_sets()


@app.post("/api/setpicks")
async def set_picks(req: SetPicksRequest):
    deck = parse_decklist(req.decklist)
    commanders = [c for c in req.commanders if c.strip()] or deck.commanders
    names = [c.name for c in deck.cards] + commanders
    settings = load_settings()
    try:
        return await setpicks.set_picks(req.set, commanders, names, settings, _budget_cap(req.status, settings))
    except edhrec.EdhrecError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/recentpicks")
async def recent_picks(req: SetPicksRequest):
    deck = parse_decklist(req.decklist)
    commanders = [c for c in req.commanders if c.strip()] or deck.commanders
    if not commanders:
        raise HTTPException(400, "Enter a commander, or mark one in the list (a Commander section or *CMDR*)")
    names = [c.name for c in deck.cards] + commanders
    settings = load_settings()
    return await setpicks.recent_picks(commanders, names, settings, _budget_cap(req.status, settings))


# ---------------------------------------------------------------------------
# Collection + deck library
# ---------------------------------------------------------------------------

@app.get("/api/collection")
def get_collection():
    return collection.summary()


@app.post("/api/collection/import")
async def import_collection(req: CollectionImportRequest):
    try:
        if req.text.strip():
            cards = collection.parse_collection_text(req.text)
            if not cards:
                raise collection.CollectionError("No cards found in that export.")
            return collection.import_collection(cards, "Pasted export")
        if req.url.strip():
            cards = await collection.fetch_archidekt_collection(req.url)
            return collection.import_collection(cards, req.url.strip())
    except collection.CollectionError as exc:
        raise HTTPException(400, str(exc))
    raise HTTPException(400, "Paste an Archidekt collection link or a CSV export")


@app.post("/api/collection/decks/import")
async def import_user_decks(req: UserDecksRequest):
    try:
        decks = await collection.fetch_archidekt_user_decks(req.username)
    except collection.CollectionError as exc:
        raise HTTPException(400, str(exc))
    result = collection.upsert_decks(decks, req.status if req.status in ("built", "brewing") else "built")
    result["imported"] = len(decks)
    return result


@app.post("/api/collection/decks")
async def save_deck(req: SaveDeckRequest):
    try:
        decklist, name, commanders = req.decklist, req.name, req.commanders
        if req.url.strip() and not decklist.strip():
            try:
                imp = await importer.import_deck(req.url)
            except importer.ImportError_ as exc:
                raise collection.CollectionError(str(exc))
            decklist, name, commanders = imp["decklist"], name or imp["name"], imp["commanders"]
        deck = collection.new_deck(name, decklist, commanders, req.status, req.url.strip())
    except collection.CollectionError as exc:
        raise HTTPException(400, str(exc))
    if m := importer._ARCHIDEKT_RE.search(req.url):
        deck["id"] = f"archidekt-{m.group(1)}"   # same id as a username import, so re-imports refresh it
    result = collection.upsert_decks([deck], deck["status"], keep_status=False)
    result["saved"] = deck["id"]
    return result


@app.post("/api/collection/decks/{deck_id}")
def update_deck(deck_id: str, req: UpdateDeckRequest):
    try:
        return collection.update_deck(deck_id, req.status, req.name)
    except collection.CollectionError as exc:
        raise HTTPException(404, str(exc))


@app.delete("/api/collection/decks/{deck_id}")
def delete_deck(deck_id: str):
    return collection.delete_deck(deck_id)


@app.post("/api/collection/check")
def check_collection(req: CheckRequest):
    deck = parse_decklist(req.decklist)
    commanders = [c for c in req.commanders if c.strip()] or deck.commanders
    if not deck.cards and not commanders:
        raise HTTPException(400, "Paste or fetch a deck first")
    return collection.check_deck(req.decklist, commanders, req.deck_id)


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

@app.post("/api/cache/clear")
def clear_cache():
    cache.clear()
    cardkingdom._path().unlink(missing_ok=True)
    cardkingdom._list = None
    return {"ok": True}


@app.get("/api/status")
def status():
    path = cardkingdom._path()
    return {
        "ok": True,
        "ck_pricelist_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        if path.exists() else None,
    }


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/favicon.png")
def favicon():
    return FileResponse(FRONTEND / "favicon.png")
