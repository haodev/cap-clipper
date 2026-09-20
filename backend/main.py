"""CapClipper read API.

Serves the precomputed analysis in demo_payload.json. There is no NLP, no
model call, and no database at request time - the payload is loaded once at
startup and every endpoint is a dictionary lookup. Rebuild the payload with
`python scripts/build_payload.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cc_paths import DATA_DIR  # noqa: E402

PAYLOAD_PATH = DATA_DIR / "demo_payload.json"

app = FastAPI(title="CapClipper API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load() -> dict:
    if not PAYLOAD_PATH.exists():
        raise RuntimeError(
            f"missing {PAYLOAD_PATH}. Run: python scripts/build_payload.py"
        )
    return json.loads(PAYLOAD_PATH.read_text())


PAYLOAD = _load()
TWEETS_BY_ID = {t["id"]: t for t in PAYLOAD["feed"]}
for _card in PAYLOAD["anomalies"]:
    for _t in _card["tweets"]:
        TWEETS_BY_ID.setdefault(_t["id"], _t)


@app.get("/api/meta")
def meta() -> dict:
    """Dataset provenance and score definitions."""
    return PAYLOAD["meta"]


@app.get("/api/hourly")
def hourly() -> list[dict]:
    """24 hourly rows: volume, topic share, sentiment, side-effect rate."""
    return PAYLOAD["hourly"]


@app.get("/api/narratives")
def narratives() -> list[dict]:
    """The discovered narrative threads, ranked by volume."""
    return PAYLOAD["narratives"]


@app.get("/api/claims")
def claims(diffusion: str | None = None) -> list[dict]:
    """Claims that spread, with their organic/coordinated verdict."""
    items = PAYLOAD["claims"]
    if diffusion:
        items = [c for c in items if c["diffusion"] == diffusion]
    return items


@app.get("/api/anomalies")
def anomalies() -> list[dict]:
    """Frozen forensic cards with evidence and cached Gemini prose."""
    return PAYLOAD["anomalies"]


@app.get("/api/feed")
def feed(narrative: str | None = None, limit: int = 40) -> list[dict]:
    """Tweets for the read-only feed, optionally filtered to one narrative."""
    items = PAYLOAD["feed"]
    if narrative:
        items = [t for t in items if narrative in t["narratives"]]
    return items[:limit]


@app.get("/api/tweet/{tweet_id}")
def tweet(tweet_id: str) -> dict:
    """One tweet with its scores, for the hover card."""
    found = TWEETS_BY_ID.get(tweet_id)
    if not found:
        raise HTTPException(status_code=404, detail="tweet not in payload")
    return found


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "day": PAYLOAD["meta"]["day_utc"],
        "tweets": PAYLOAD["meta"]["slice_rows"],
        "narratives": len(PAYLOAD["narratives"]),
        "claims": len(PAYLOAD["claims"]),
        "anomalies": len(PAYLOAD["anomalies"]),
    }
