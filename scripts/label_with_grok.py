"""Label the weight-loss drug tweets with Grok, in parallel, resumably and within a budget.

Sends prompts/labeling_guide.md verbatim as the system prompt and a batch of tweets as
JSON, and asks for strict-schema JSON back. What the model receives is exactly the file
you can read, so reviewing the guide is reviewing the run.

Two things keep the bill down:
  - Identical texts are labeled once. Half the corpus is retweets of the same wording
    (one meme appears 1,773 times), so 23,058 rows collapse to 11,561 unique texts.
  - The guide is a stable prefix, so it should hit the prompt cache at a sixth the price.

    python scripts/label_with_grok.py --dry-run        # cost estimate, no API calls
    python scripts/label_with_grok.py --limit 200      # small pilot, check quality first
    python scripts/label_with_grok.py                  # the whole corpus
    python scripts/label_with_grok.py --max-usd 5      # stop before spending more than $5
    python scripts/label_with_grok.py --workers 8      # more requests in flight

Three layers keep coverage complete when the API misbehaves:
  1. Each request retries transient failures (429, 5xx, dropped connections) with
     jittered backoff.
  2. A batch whose reply is malformed or the wrong length is split in half and retried,
     down to single items, so one bad tweet cannot lose its 99 neighbours.
  3. After the main pass, any text still missing is swept up in extra passes until
     nothing is left or no further progress is possible.

Resume is automatic: finished texts are appended to labels.jsonl and skipped next time.
If credits run out the run stops promptly, keeps everything already paid for, and exits
3. Put a new key in XAI_API_KEY and run the same command again to carry on.
"""
import argparse
import http.client
import json
import os
import random
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from label_schema import TAXONOMY_VERSION, check_guide, label_schema, validate

API_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.3"

# $ per million tokens, grok-4.3 under the 200k-context tier (docs.x.ai, Sep 2026).
PRICE_IN, PRICE_CACHED, PRICE_OUT = 1.25, 0.20, 2.50

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "prompts" / "labeling_guide.md"
SOURCE = REPO / "data" / "ozempic_dataset.csv"
OUT = REPO / "data" / "labels"

MAX_OUTPUT_TOKENS = 16000
RETRIES = 6
SWEEPS = 3

# Anything here is a hiccup worth retrying rather than a reason to lose the batch.
TRANSIENT = (urllib.error.URLError, http.client.HTTPException, ConnectionError,
             socket.timeout, ssl.SSLError, TimeoutError, json.JSONDecodeError, KeyError)


class CreditsExhausted(Exception):
    """The account is out of credits or over quota -- stop, do not retry."""


def norm_key(body: pd.Series) -> pd.Series:
    """Texts that differ only by RT prefix, links or spacing are the same text to label."""
    return (body.str.replace(r"^RT @\w+:\s*", "", regex=True)
                .str.replace(r"https?://\S+", " ", regex=True)
                .str.replace(r"\s+", " ", regex=True)
                .str.strip().str.lower())


def build_unique(limit: int | None) -> pd.DataFrame:
    """One row per distinct text, with the metadata the guide describes.

    Sorted by key so uids are stable: a resume always rebuilds the same table.
    """
    ids = ["id", "author_id", "conversation_id", "reply_to_status_id",
           "reply_to_user_id", "quoting_id"]
    df = pd.read_csv(SOURCE, dtype={c: "string" for c in ids}, low_memory=False)
    df["key"] = norm_key(df["body"])
    for flag in ["is_reply", "is_quote", "has_media"]:
        df[flag] = df[flag].astype(str).str.lower().eq("true")

    # No retweet flag: once the "RT @user:" prefix is stripped a retweet's body is
    # identical to the original's, so retweet-ness is a property of the row, not of the
    # text. It stays on every row in the source data and is a filter for analysis.
    grouped = df.groupby("key", sort=True)
    uniq = pd.DataFrame({
        "text": grouped["body"].first(),
        "lang": grouped["lang"].agg(lambda s: s.mode().iat[0] if not s.mode().empty else "und"),
        "reply": grouped["is_reply"].mean().ge(0.5),
        "quote": grouped["is_quote"].mean().ge(0.5),
        "media": grouped["has_media"].mean().ge(0.5),
        "dup": grouped.size(),
    }).reset_index()
    uniq.insert(0, "uid", range(len(uniq)))

    # The model cannot open links, and raw t.co URLs are pure token cost.
    uniq["text"] = (uniq["text"].str.replace(r"^RT @\w+:\s*", "", regex=True)
                                .str.replace(r"https?://\S+", "[link]", regex=True)
                                .str.replace(r"\s+", " ", regex=True).str.strip())
    uniq = uniq[uniq["text"].str.len() > 0]
    if limit:
        # Spread the pilot across the corpus rather than taking one alphabetical corner.
        uniq = uniq.sample(n=min(limit, len(uniq)), random_state=0).sort_values("uid")
    return uniq


def payload_for(rows: pd.DataFrame) -> list[dict]:
    return [{"id": int(r.uid), "text": r.text, "lang": r.lang,
             "reply": bool(r.reply), "quote": bool(r.quote), "media": bool(r.media),
             "dup": int(r.dup)} for r in rows.itertuples()]


def call_grok(api_key: str, guide: str, items: list[dict], stop: threading.Event):
    body = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": guide},
            {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "tweet_labels", "strict": True, "schema": label_schema()}},
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    last = None
    for attempt in range(RETRIES):
        if stop.is_set():
            raise RuntimeError("stopped")
        try:
            request = urllib.request.Request(API_URL, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read())
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)["labels"], data.get("usage", {}) or {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code in (401, 402, 403) or re.search(
                    r"credit|quota|billing|insufficient|payment", detail, re.I):
                raise CreditsExhausted(f"HTTP {e.code}: {detail}") from e
            if e.code != 429 and e.code < 500:
                raise RuntimeError(f"HTTP {e.code}: {detail}") from e
            last = f"HTTP {e.code}: {detail}"
        except TRANSIENT as e:
            last = repr(e)
        # jitter so parallel workers do not all come back at the same instant
        time.sleep(min(60, 2 ** attempt * 2) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"failed after {RETRIES} attempts: {last}")


def cost_of(usage: dict) -> float:
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    fresh = max(0, usage.get("prompt_tokens", 0) - cached)
    return (fresh * PRICE_IN + cached * PRICE_CACHED
            + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6


def label_batch(api_key, guide, rows, stop, log, lock):
    """Label one batch, halving it if the reply is malformed or the wrong length."""
    items = payload_for(rows)

    def split(reason, already=0.0):
        if len(rows) == 1:
            with lock:
                print(f"    dropping uid {int(rows.iloc[0].uid)}: {reason}", flush=True)
            return [], already
        mid = len(rows) // 2
        a, ca = label_batch(api_key, guide, rows.iloc[:mid], stop, log, lock)
        b, cb = label_batch(api_key, guide, rows.iloc[mid:], stop, log, lock)
        return a + b, already + ca + cb

    try:
        labels, usage = call_grok(api_key, guide, items, stop)
    except RuntimeError as e:
        if stop.is_set():
            return [], 0.0
        with lock:
            print(f"    batch of {len(rows)} failed ({e}); splitting", flush=True)
        return split(str(e))

    spent = cost_of(usage)
    with lock:
        log.append({"n": len(rows), "prompt_tokens": usage.get("prompt_tokens", 0),
                    "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0), "usd": spent})

    wanted = {i["id"] for i in items}
    returned = {l.get("id") for l in labels if isinstance(l, dict)}
    if returned != wanted:
        with lock:
            print(f"    got {len(returned & wanted)}/{len(wanted)} ids back; splitting", flush=True)
        return split("id mismatch", spent)

    for label in labels:
        label["_problems"] = validate(label)
    return labels, spent


def run_pass(batches, api_key, guide, sink, lock, state, stop, workers, label=""):
    """Run one set of batches across a thread pool, stopping early if asked to."""
    started = time.time()

    def do(index_batch):
        index, batch = index_batch
        if stop.is_set():
            return
        try:
            labels, cost = label_batch(api_key, guide, batch, stop, state["log"], lock)
        except CreditsExhausted as e:
            with lock:
                state["stopped"] = state["stopped"] or f"credits exhausted -- {e}"
            stop.set()
            return
        except Exception as e:                        # noqa: BLE001 - never lose a worker
            with lock:
                state["errors"].append(f"batch {index}: {e!r}")
            return

        with lock:
            for lab in labels:
                sink.write(json.dumps(lab, ensure_ascii=False) + "\n")
            sink.flush()
            state["spent"] += cost
            state["done"] += 1
            state["labeled"] += len(labels)
            bad = sum(1 for l in labels if l["_problems"])
            rate = (time.time() - started) / max(1, state["done"])
            left = (len(batches) - state["done"]) * rate / max(1, workers)
            print(f"  [{state['done']:3}/{len(batches)}]{label} {len(labels):3} labels"
                  f"{f' ({bad} flagged)' if bad else ''}  ${state['spent']:6.3f}"
                  f"  eta {left / 60:4.1f}m", flush=True)
            if state["spent"] + 0.15 > state["max_usd"]:
                state["stopped"] = state["stopped"] or f"budget cap ${state['max_usd']:.2f} reached"
                stop.set()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(do, enumerate(batches, 1)))


def labeled_uids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as fh:
        return {json.loads(line)["id"] for line in fh if line.strip()}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6, help="requests in flight (default 6)")
    ap.add_argument("--limit", type=int, help="label only N unique texts (pilot run)")
    ap.add_argument("--max-usd", type=float, default=12.0,
                    help="stop before spending more than this (default 12)")
    ap.add_argument("--dry-run", action="store_true", help="estimate cost, call nothing")
    args = ap.parse_args()

    check_guide()
    guide = GUIDE.read_text(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    uniq = build_unique(args.limit)
    uniq.to_csv(OUT / "unique_texts.csv", index=False, encoding="utf-8-sig")
    labels_path = OUT / "labels.jsonl"

    done = labeled_uids(labels_path)
    if done:
        print(f"resuming: {len(done):,} texts already labeled")
    todo = uniq[~uniq["uid"].isin(done)]
    batches = [todo.iloc[i:i + args.batch_size] for i in range(0, len(todo), args.batch_size)]

    guide_tokens = len(guide) // 4
    est_in = guide_tokens * len(batches) + int(todo["text"].str.len().sum() / 3.6) + 30 * len(todo)
    est_out = 90 * len(todo)
    est = (est_in * PRICE_IN + est_out * PRICE_OUT) / 1e6

    print(f"\ntaxonomy v{TAXONOMY_VERSION}  model {MODEL}  workers {args.workers}")
    print(f"unique texts   : {len(uniq):,}  (covering {int(uniq['dup'].sum()):,} rows)")
    print(f"to label now   : {len(todo):,} in {len(batches)} batches of {args.batch_size}")
    print(f"est. cost      : ${est:.2f} uncached, ~${est * 0.8:.2f} with prompt caching")
    print(f"budget cap     : ${args.max_usd:.2f}")

    if args.dry_run:
        print("\ndry run: nothing sent.")
        return 0
    if not batches:
        print("\nnothing to do.")
        return 0
    if est > args.max_usd:
        print(f"\nestimate ${est:.2f} exceeds --max-usd {args.max_usd:.2f}. "
              f"Raise the cap or use --limit.")
        return 2

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key and (REPO / ".env").exists():
        for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("XAI_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip("'\"")
    if not api_key:
        print("\nNo API key. Set XAI_API_KEY, or put XAI_API_KEY=... in .env")
        return 2

    stop = threading.Event()
    lock = threading.Lock()
    state = {"spent": 0.0, "done": 0, "labeled": 0, "stopped": None,
             "log": [], "errors": [], "max_usd": args.max_usd}
    t0 = time.time()

    with labels_path.open("a", encoding="utf-8") as sink:
        run_pass(batches, api_key, guide, sink, lock, state, stop, args.workers)

        # Sweeps: whatever the main pass missed, try again in fresh batches.
        for sweep in range(1, SWEEPS + 1):
            if stop.is_set():
                break
            missing = uniq[~uniq["uid"].isin(labeled_uids(labels_path))]
            if missing.empty:
                break
            print(f"\nsweep {sweep}: {len(missing):,} texts still missing, retrying")
            size = max(10, args.batch_size // (2 * sweep))
            retry = [missing.iloc[i:i + size] for i in range(0, len(missing), size)]
            state["done"] = 0
            run_pass(retry, api_key, guide, sink, lock, state, stop, args.workers,
                     label=f" sweep{sweep}")

    if state["log"]:
        log_path = OUT / "run_log.csv"
        pd.DataFrame(state["log"]).to_csv(log_path, mode="a", index=False,
                                          header=not log_path.exists())

    final = labeled_uids(labels_path)
    covered = uniq[uniq["uid"].isin(final)]
    print(f"\n{'=' * 62}")
    print(f"labeled   : {len(covered):,} of {len(uniq):,} unique texts "
          f"({len(covered) / len(uniq) * 100:.1f}%)")
    print(f"rows       : {int(covered['dup'].sum()):,} of {int(uniq['dup'].sum()):,} "
          f"({covered['dup'].sum() / uniq['dup'].sum() * 100:.1f}%)")
    print(f"spent      : ${state['spent']:.3f} this run   in {(time.time() - t0) / 60:.1f} min")
    if state["errors"]:
        print(f"errors     : {len(state['errors'])}")
        for e in state["errors"][:5]:
            print(f"  {e}")

    if state["stopped"]:
        print(f"\nSTOPPED: {state['stopped']}")
        if "credits" in state["stopped"]:
            print("Everything already labeled is saved. Put a new key in XAI_API_KEY "
                  "and run the same command again to continue.")
            return 3
        return 4

    print("\nnext: python scripts/join_labels.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
