"""
main.py — MTG Toolkit FastAPI server.

Endpoints:
  GET  /                        → serve web UI
  GET  /api/settings            → return current config
  POST /api/settings            → update config
  POST /api/parse               → parse a pasted decklist (cards + detected commanders)
  POST /api/prices/jobs         → start a best-price lookup for a decklist
  GET  /api/prices/jobs/{id}    → progress + results of a price lookup
  POST /api/edhrec              → EDHREC cards the deck is missing for its commander
  POST /api/cache/clear         → drop cached Scryfall/EDHREC data and the CK price list
  GET  /api/status              → health check
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import cache, cardkingdom, edhrec
from backend.config import load_settings, save_settings
from backend.decklist import parse_decklist
from backend.pricing import price_cards

app = FastAPI(title="MTG Toolkit")

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


class UpdateSettingsRequest(BaseModel):
    cache_hours: float = 12
    skip_basic_lands: bool = True
    tie_goes_to: str = "cardkingdom"
    min_inclusion_pct: float = 0


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
    settings["edhrec"].update(min_inclusion_pct=max(0.0, req.min_inclusion_pct))
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
    min_pct = float(load_settings()["edhrec"].get("min_inclusion_pct", 0))
    return edhrec.suggestions(page, names, min_pct)


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
