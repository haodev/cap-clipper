"""Shared paths and YAML lexicon loader."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEXICON_DIR = ROOT / "lexicons"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from download_file import DATA_DIR, FIRST_DAY, FIRST_DAY_DIR  # noqa: E402

DAY_START = f"{FIRST_DAY}T00:00:00Z"
DAY_END = "2026-08-18T00:00:00Z"
CURATED_PATH = DATA_DIR / "curated_glp1.parquet"
HOURLY_PATH = DATA_DIR / "hourly_en_firehose.parquet"
ENRICHED_PATH = DATA_DIR / "enriched_glp1.parquet"
ENRICHED_RANGE_PATH = DATA_DIR / "enriched_range.parquet"
RANGE_PAYLOAD_PATH = DATA_DIR / "range_payload.json"
LABELED_CSV_PATH = ROOT / "data" / "ozempic_labeled.csv"
LABEL_CACHE_PATH = DATA_DIR / "gemini_labels.json"


def load_terms(name: str) -> list[str]:
    return load_groups(name)["terms"]


def load_groups(name: str) -> dict[str, list[str]]:
    """Load a lexicon file as {group_name: [terms]}."""
    path = LEXICON_DIR / name
    data = yaml.safe_load(path.read_text())
    groups = {
        key: [str(t).strip().lower() for t in values if str(t).strip()]
        for key, values in data.items()
    }
    if not any(groups.values()):
        raise ValueError(f"{path} has no terms")
    return groups


NARRATIVES_FILE = "narratives.yml"


def load_narratives() -> dict[str, dict]:
    """Load narratives.yml as {key: {"label": str, "terms": [str]}}.

    Unlike the other lexicons these carry a display label, so a theme added by
    scripts/gemini_narratives.py arrives already named.
    """
    path = LEXICON_DIR / NARRATIVES_FILE
    data = yaml.safe_load(path.read_text())
    out: dict[str, dict] = {}
    for key, body in data.items():
        if not isinstance(body, dict) or "terms" not in body:
            raise ValueError(f"{path}:{key} must be a mapping with label and terms")
        terms = [str(t).strip().lower() for t in body["terms"] if str(t).strip()]
        if not terms:
            raise ValueError(f"{path}:{key} has no terms")
        out[key] = {"label": str(body.get("label") or key), "terms": terms}
    return out


def env_value(name: str) -> str:
    """Read a key from the process env, falling back to a .env file.

    Secrets stay out of the repo; .env is gitignored.
    """
    import os

    found = os.environ.get(name, "").strip()
    if found:
        return found
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip("'\"")
    return ""
