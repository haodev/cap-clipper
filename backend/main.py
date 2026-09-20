"""CapClipper read API.

Serves precomputed analysis JSON. There is no NLP, no model call, and no
database at request time. Two frozen payloads:

- demo_payload.json  — one UTC day (2026-08-17), including hourly series
- range_payload.json — labeled multi-day slice, no hourly analysis

Rebuild with `python scripts/build_payload.py` and
`python scripts/build_range_payload.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cc_paths import DATA_DIR, RANGE_PAYLOAD_PATH  # noqa: E402

DAY_DATE = "2026-08-17"
DAY_PAYLOAD_PATH = DATA_DIR / "demo_payload.json"

app = FastAPI(title="CapClipper API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load(path: Path, hint: str) -> dict:
    if not path.exists():
        raise RuntimeError(f"missing {path}. Run: {hint}")
    return json.loads(path.read_text())


DAY_PAYLOAD = _load(DAY_PAYLOAD_PATH, "python scripts/build_payload.py")
try:
    RANGE_PAYLOAD = _load(RANGE_PAYLOAD_PATH, "python scripts/build_range_payload.py")
except RuntimeError:
    RANGE_PAYLOAD = None

DAY_TWEETS = {t["id"]: t for t in DAY_PAYLOAD["feed"]}
for _card in DAY_PAYLOAD["anomalies"]:
    for _t in _card["tweets"]:
        DAY_TWEETS.setdefault(_t["id"], _t)

RANGE_TWEETS: dict[str, dict] = {}
if RANGE_PAYLOAD:
    RANGE_TWEETS = {t["id"]: t for t in RANGE_PAYLOAD["feed"]}
    for _card in RANGE_PAYLOAD["anomalies"]:
        for _t in _card["tweets"]:
            RANGE_TWEETS.setdefault(_t["id"], _t)


def _day(day: str) -> dict:
    if day != DAY_DATE:
        raise HTTPException(status_code=404, detail=f"no day demo for {day}")
    return DAY_PAYLOAD


def _range() -> dict:
    if RANGE_PAYLOAD is None:
        raise HTTPException(
            status_code=503,
            detail="range payload missing. Run: python scripts/build_range_payload.py",
        )
    return RANGE_PAYLOAD


def _feed(items: list, narrative: str | None, limit: int) -> list:
    if narrative:
        items = [t for t in items if narrative in t["narratives"]]
    return items[:limit]


@app.get("/api/meta")
def meta() -> dict:
    """Legacy alias of the 2026-08-17 day demo."""
    return DAY_PAYLOAD["meta"]


@app.get("/api/hourly")
def hourly() -> list[dict]:
    return DAY_PAYLOAD["hourly"]


@app.get("/api/narratives")
def narratives() -> list[dict]:
    return DAY_PAYLOAD["narratives"]


@app.get("/api/claims")
def claims(diffusion: str | None = None) -> list[dict]:
    items = DAY_PAYLOAD["claims"]
    if diffusion:
        items = [c for c in items if c["diffusion"] == diffusion]
    return items


@app.get("/api/anomalies")
def anomalies() -> list[dict]:
    return DAY_PAYLOAD["anomalies"]


@app.get("/api/feed")
def feed(narrative: str | None = None, limit: int = 40) -> list[dict]:
    return _feed(DAY_PAYLOAD["feed"], narrative, limit)


@app.get("/api/tweet/{tweet_id}")
def tweet(tweet_id: str) -> dict:
    found = DAY_TWEETS.get(tweet_id) or RANGE_TWEETS.get(tweet_id)
    if not found:
        raise HTTPException(status_code=404, detail="tweet not in payload")
    return found


@app.get("/api/day/{day}/meta")
def day_meta(day: str) -> dict:
    return _day(day)["meta"]


@app.get("/api/day/{day}/hourly")
def day_hourly(day: str) -> list[dict]:
    return _day(day)["hourly"]


@app.get("/api/day/{day}/narratives")
def day_narratives(day: str) -> list[dict]:
    return _day(day)["narratives"]


@app.get("/api/day/{day}/claims")
def day_claims(day: str, diffusion: str | None = None) -> list[dict]:
    items = _day(day)["claims"]
    if diffusion:
        items = [c for c in items if c["diffusion"] == diffusion]
    return items


@app.get("/api/day/{day}/anomalies")
def day_anomalies(day: str) -> list[dict]:
    return _day(day)["anomalies"]


@app.get("/api/day/{day}/feed")
def day_feed(day: str, narrative: str | None = None, limit: int = 40) -> list[dict]:
    return _feed(_day(day)["feed"], narrative, limit)


@app.get("/api/range/meta")
def range_meta() -> dict:
    return _range()["meta"]


@app.get("/api/range/narratives")
def range_narratives() -> list[dict]:
    return _range()["narratives"]


@app.get("/api/range/claims")
def range_claims(diffusion: str | None = None) -> list[dict]:
    items = _range()["claims"]
    if diffusion:
        items = [c for c in items if c["diffusion"] == diffusion]
    return items


@app.get("/api/range/anomalies")
def range_anomalies() -> list[dict]:
    return _range()["anomalies"]


@app.get("/api/range/feed")
def range_feed(narrative: str | None = None, limit: int = 40) -> list[dict]:
    return _feed(_range()["feed"], narrative, limit)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "day": DAY_PAYLOAD["meta"]["day_utc"],
        "range": None
        if RANGE_PAYLOAD is None
        else {
            "start": RANGE_PAYLOAD["meta"].get("start_utc"),
            "end": RANGE_PAYLOAD["meta"].get("end_utc"),
            "tweets": RANGE_PAYLOAD["meta"]["slice_rows"],
        },
        "tweets": DAY_PAYLOAD["meta"]["slice_rows"],
        "narratives": len(DAY_PAYLOAD["narratives"]),
        "claims": len(DAY_PAYLOAD["claims"]),
        "anomalies": len(DAY_PAYLOAD["anomalies"]),
    }
