"""Write one plain-English paragraph per anomaly card into demo_payload.json.

Runs offline and ahead of the demo: the model never sits in the request path,
so the UI stays fast and deterministic. Results are cached by a hash of the
evidence, so re-running is free unless the underlying numbers changed.

Without GEMINI_API_KEY this is a no-op and the UI falls back to the
hand-written `why_it_matters` line already in the payload.

Usage: GEMINI_API_KEY=... python scripts/gemini_explain.py
       python scripts/gemini_explain.py --dry-run   # print prompts only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cc_paths import DATA_DIR  # noqa: E402
from gemini import DEFAULT_MODEL, api_key, generate  # noqa: E402

PAYLOAD_PATH = DATA_DIR / "demo_payload.json"
CACHE_PATH = DATA_DIR / "gemini_cache.json"
MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

SYSTEM = """You are a misinformation analyst writing one short paragraph for a \
dashboard card about GLP-1 drug discourse on X.

Hard rules:
- Use ONLY the numbers and facts in the evidence block. Never invent a figure.
- 2-3 sentences, under 60 words, plain English, no bullet points, no markdown.
- Say what the pattern is AND what it is not. High volume alone is not proof of \
a campaign; identical wire headlines are not astroturf; a shared discount code \
across accounts IS meaningful evidence.
- Hedge honestly. This is one UTC day of data from lexicon heuristics.
- No preamble. Output the paragraph only."""


def prompt_for(card: dict) -> str:
    evidence = {k: v for k, v in card["evidence"].items() if k != "why_it_matters"}
    examples = [t["body"][:180] for t in card.get("tweets", [])[:3]]
    return (
        f"{SYSTEM}\n\n"
        f"Card headline: {card['headline']}\n"
        f"Pattern type: {card['narrative_type']}\n"
        f"Evidence: {json.dumps(evidence, indent=1)}\n"
        f"Example posts: {json.dumps(examples, indent=1)}\n\n"
        "Paragraph:"
    )


def fingerprint(card: dict) -> str:
    blob = json.dumps(
        {"h": card["headline"], "e": card["evidence"], "m": MODEL}, sort_keys=True
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def call_gemini(prompt: str, key: str) -> str:
    # Low temperature: this is a description of fixed numbers, not prose.
    return generate(prompt, key, model=MODEL, temperature=0.2, max_tokens=400)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print prompts, no calls")
    parser.add_argument("--force", action="store_true", help="ignore the cache")
    args = parser.parse_args()

    payload = json.loads(PAYLOAD_PATH.read_text())
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    key = api_key()

    if args.dry_run:
        for card in payload["anomalies"]:
            print(f"\n{'=' * 70}\n{card['id']}\n{'=' * 70}")
            print(prompt_for(card))
        return

    if not key:
        print("GEMINI_API_KEY not set - leaving cards with their why_it_matters text.")
        print("The UI renders fine without this step.")
        return

    wrote = 0
    for card in payload["anomalies"]:
        fp = fingerprint(card)
        if not args.force and fp in cache:
            card["explanation"] = cache[fp]
            print(f"{card['id']}: cached")
            continue
        try:
            text = call_gemini(prompt_for(card), key)
        except (RuntimeError, OSError) as exc:
            print(f"{card['id']}: FAILED ({exc}); keeping fallback text")
            continue
        cache[fp] = text
        card["explanation"] = text
        wrote += 1
        print(f"{card['id']}: {text}")

    CACHE_PATH.write_text(json.dumps(cache, indent=1))
    PAYLOAD_PATH.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {wrote} new paragraph(s) into {PAYLOAD_PATH}")


if __name__ == "__main__":
    main()
