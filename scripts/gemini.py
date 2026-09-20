"""Minimal Gemini REST client shared by the offline enrichment scripts.

Every call happens in batch, ahead of the demo. Nothing here is ever on the
request path of the API.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cc_paths import env_value  # noqa: E402

# The python.org build has no CA store of its own, so verification fails
# against Google's endpoint unless we hand it certifi's bundle.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

DEFAULT_MODEL = "gemini-3.6-flash"
RETRIES = 4
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def api_key() -> str:
    return env_value("GEMINI_API_KEY")


def generate(
    prompt: str,
    key: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    as_json: bool = False,
    retries: int = RETRIES,
) -> str:
    """One prompt in, one string out. Raises on transport or shape errors.

    `retries=1` disables the backoff, which is what a quota probe wants: when
    the free tier is already exhausted, sleeping through four 429s just wastes
    two minutes to learn what the first reply said.
    """
    config: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if as_json:
        config["responseMimeType"] = "application/json"
    body = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
    ).encode()
    req = urllib.request.Request(
        ENDPOINT.format(m=model),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    # 429 and 503 are load, not errors in the request; back off and retry.
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:300]
            if exc.code not in (429, 503) or attempt == retries:
                raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}") from exc
            wait = 2**attempt
            print(f"    {exc.code} from Gemini, retrying in {wait}s")
            time.sleep(wait)
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {json.dumps(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        finish = candidates[0].get("finishReason", "unknown")
        raise RuntimeError(f"Gemini returned empty text (finishReason={finish})")
    return text


def generate_json(prompt: str, key: str, **kw) -> dict | list:
    """Same, but parse the reply as JSON, tolerating ```json fences."""
    raw = generate(prompt, key, as_json=True, **kw)
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()
    return json.loads(raw)
