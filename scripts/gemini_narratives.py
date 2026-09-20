"""Discover narrative threads bottom-up with Gemini, then merge them additively.

The hand-written lexicons only tag about a fifth of the day's distinct claims.
This script shows Gemini the claims nothing matched, asks what recurring themes
are in there, and folds the answer back into lexicons/narratives.yml.

Two rules keep this honest:

  - Nothing is ever deleted. Existing themes and existing terms survive every
    run; the script can only add a new theme or add terms to an old one.
  - No proposed term is trusted. Each one is tested against the corpus first
    and dropped if it matches too few claims (dead weight or hallucinated) or
    too many (so generic it would swallow the feed).

Usage:
    python scripts/gemini_narratives.py --dry-run   # propose, print, write nothing
    python scripts/gemini_narratives.py             # propose, validate, merge
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cc_paths import (  # noqa: E402
    DATA_DIR,
    ENRICHED_PATH,
    LEXICON_DIR,
    NARRATIVES_FILE,
    load_narratives,
)
from gemini import api_key, generate_json  # noqa: E402

PROPOSALS_PATH = DATA_DIR / "narrative_proposals.json"

# A term must appear in at least this many distinct claims to be worth a rule,
# from at least this many independent sources.
MIN_CLAIMS = 3
MIN_SOURCES = 3
# A thread normally needs two surviving terms, but one term carrying this much
# of the corpus is a thread on its own.
STRONG_CLAIMS = 8
# ...and in no more than this share of them, or it is not a narrative, it is
# just a word everyone uses.
MAX_SHARE = 0.25
BATCH = 70
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,28}$")

PROMPT = """You are analysing one UTC day of X posts about GLP-1 drugs \
(Ozempic, Wegovy, Mounjaro, semaglutide, retatrutide).

A keyword system already recognises these narrative threads:
{existing}

Below are posts that matched NONE of them. Find the recurring narrative \
threads these posts represent.

Rules:
- Propose a thread only if at least 4 DIFFERENT posts in this batch are on it.
- Prefer threads about a distinct social claim or conflict, not a topic label. \
"People claim it destroys muscle, and supplements are sold against that fear" \
is a thread; "health" is not.
- Patterns are matched by plain lowercase substring containment.

CRITICAL - patterns must GENERALISE, not quote:
- A pattern must be a word or short stem that many different people would \
independently type when posting about the thread.
- NEVER copy a distinctive phrase out of one post. "protects your hard-earned \
muscle" and "19 year old dies" are useless: they match only the post they came \
from. Write "muscle loss", "lean mass", "teenager" instead.
- Never use a brand or person's name that appears in only one story.
- 1 to 3 words each. Word stems are good ("addict" catches addicted, \
addiction). A pattern matching under 3 posts will be thrown away.
- You may also suggest extra patterns for the EXISTING threads listed above.
- Do not propose a thread that duplicates an existing one; extend it instead.

Return JSON of this exact shape:
{{"new_threads": [{{"key": "snake_case_id", "label": "Short human label", \
"why": "one sentence", "terms": ["pattern", ...]}}],
 "extend_existing": [{{"key": "existing_key", "terms": ["pattern", ...]}}]}}

Posts:
{posts}"""


RT_RE = re.compile(r"^rt @([a-z0-9_]+)", re.I)


def distinct_claims(df: pd.DataFrame) -> pd.DataFrame:
    """One row per claim, highest-reach copy, matching the feed's unit."""
    return df.sort_values(["retweet_count", "like_count"], ascending=False).drop_duplicates(
        "text_hash"
    )


def source_of(row: pd.Series) -> str:
    """Who actually said it.

    A retweet's author_id is the amplifier, not the source, so counting raw
    author_id makes one advertiser retweeted three times look like three
    independent voices. Credit the handle inside "RT @handle:" instead.
    """
    m = RT_RE.match(str(row.get("body") or ""))
    return f"@{m.group(1).lower()}" if m else str(row.get("author_id"))


def validate(
    term: str, bodies: pd.Series, authors: pd.Series, existing_terms: set[str]
) -> tuple[bool, str]:
    """Keep a proposed pattern only if the corpus actually supports it."""
    term = term.strip().lower()
    if len(term) < 4:
        return False, "too short"
    if term in existing_terms:
        return False, "already covered"
    hit = bodies.str.contains(re.escape(term), regex=True)
    n = int(hit.sum())
    if n < MIN_CLAIMS:
        return False, f"only {n} claim(s)"
    # A phrase from one advertiser or one syndicated story can clear the claim
    # threshold while coming from a single voice. Require independent sources.
    n_src = int(authors[hit].nunique())
    if n_src < MIN_SOURCES:
        return False, f"{n} claims but only {n_src} source(s)"
    share = n / len(bodies)
    if share > MAX_SHARE:
        return False, f"matches {share:.0%} of claims"
    return True, f"{n} claims / {n_src} sources"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print, do not write")
    parser.add_argument("--batches", type=int, default=5, help="batches of untagged claims")
    parser.add_argument(
        "--from-file",
        action="store_true",
        help="re-validate saved proposals without calling Gemini",
    )
    args = parser.parse_args()

    key = "" if args.from_file else api_key()
    if not key and not args.from_file:
        raise SystemExit("GEMINI_API_KEY not found in the environment or .env")

    df = pd.read_parquet(ENRICHED_PATH)
    claims = distinct_claims(df)
    bodies = claims["body"].fillna("").str.lower()
    authors = claims.apply(source_of, axis=1)
    untagged = claims[claims["narratives"].fillna("") == ""]
    print(f"{len(claims)} distinct claims, {len(untagged)} matched no narrative")

    current = load_narratives()
    existing_terms = {t for v in current.values() for t in v["terms"]}
    existing_desc = "\n".join(f"- {k}: {v['label']}" for k, v in current.items())

    ranked = untagged.sort_values("retweet_count", ascending=False)
    proposals: list[dict] = []
    extensions: dict[str, list[str]] = {}

    # Gemini's raw answers are kept on disk. The free tier runs out of quota
    # quickly, and re-validating against the corpus is pure local work, so a
    # second opinion on the same proposals should never cost another call.
    if args.from_file:
        if not PROPOSALS_PATH.exists():
            raise SystemExit(f"no saved proposals at {PROPOSALS_PATH}")
        saved = json.loads(PROPOSALS_PATH.read_text())
        for reply in saved:
            proposals.extend(reply.get("new_threads") or [])
            for ext in reply.get("extend_existing") or []:
                if ext.get("key") in current:
                    extensions.setdefault(ext["key"], []).extend(ext.get("terms") or [])
        print(f"loaded {len(saved)} saved Gemini repl(ies) from {PROPOSALS_PATH.name}")

    raw_replies: list[dict] = []
    for i in range(0 if args.from_file else min(args.batches, (len(ranked) + BATCH - 1) // BATCH)):
        chunk = ranked.iloc[i * BATCH : (i + 1) * BATCH]
        if chunk.empty:
            break
        posts = "\n".join(
            f"- {' '.join(str(b).split())[:200]}" for b in chunk["body"].tolist()
        )
        print(f"batch {i + 1}: {len(chunk)} claims -> Gemini")
        try:
            reply = generate_json(
                PROMPT.format(existing=existing_desc, posts=posts),
                key,
                temperature=0.3,
                max_tokens=4096,
            )
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"  failed: {exc}")
            continue
        raw_replies.append(reply)
        proposals.extend(reply.get("new_threads") or [])
        for ext in reply.get("extend_existing") or []:
            if ext.get("key") in current:
                extensions.setdefault(ext["key"], []).extend(ext.get("terms") or [])

    if raw_replies:
        previous = json.loads(PROPOSALS_PATH.read_text()) if PROPOSALS_PATH.exists() else []
        PROPOSALS_PATH.write_text(json.dumps(previous + raw_replies, indent=1))
        print(f"saved {len(raw_replies)} repl(ies) to {PROPOSALS_PATH}")

    # Merge proposals that named the same thread in different batches.
    merged: dict[str, dict] = {}
    for p in proposals:
        k = str(p.get("key") or "").strip().lower()
        if not KEY_RE.match(k) or k in current:
            if k in current:
                extensions.setdefault(k, []).extend(p.get("terms") or [])
            continue
        entry = merged.setdefault(k, {"label": p.get("label") or k, "why": p.get("why", ""), "terms": []})
        entry["terms"].extend(p.get("terms") or [])

    print("\n=== proposed new threads ===")
    survivors: dict[str, dict] = {}
    for k, entry in merged.items():
        kept, seen = [], set()
        for t in entry["terms"]:
            t = str(t).strip().lower()
            if t in seen:
                continue
            seen.add(t)
            ok, why = validate(t, bodies, authors, existing_terms)
            print(f"  {'KEEP' if ok else 'drop'}  {k:24s} {t!r:38s} {why}")
            if ok:
                kept.append(t)
        if kept:
            survivors[k] = {"label": entry["label"], "terms": kept}

    # Separate batches often name the same thread twice (muscle_loss_supplements
    # and muscle_loss_prevention). Fold together anything sharing a term.
    additions: dict[str, dict] = {}
    for k, entry in survivors.items():
        twin = next(
            (o for o, v in additions.items() if set(v["terms"]) & set(entry["terms"])),
            None,
        )
        if twin:
            print(f"  -> merging {k} into {twin} (shared terms)")
            additions[twin]["terms"] = list(
                dict.fromkeys(additions[twin]["terms"] + entry["terms"])
            )
            continue
        additions[k] = entry

    for k in list(additions):
        terms = additions[k]["terms"]
        strong = any(
            int(bodies.str.contains(re.escape(t), regex=True).sum()) >= STRONG_CLAIMS
            for t in terms
        )
        if len(terms) < 2 and not strong:
            print(f"  -> {k} rejected: one weak term")
            del additions[k]

    # A term that just earned its own thread must not also be grafted onto an
    # old one. Gemini proposed both a gastroparesis thread and "gastroparesis"
    # as an eating-disorder cue; the posts are awareness-month advocacy, so the
    # graft would have mislabelled 22 claims.
    claimed = {t for v in additions.values() for t in v["terms"]}

    print("\n=== proposed additions to existing threads ===")
    extra: dict[str, list[str]] = {}
    for k, terms in extensions.items():
        for t in dict.fromkeys(str(x).strip().lower() for x in terms):
            if t in claimed:
                print(f"  drop  {k:24s} {t!r:38s} anchors its own new thread")
                continue
            ok, why = validate(t, bodies, authors, existing_terms)
            print(f"  {'KEEP' if ok else 'drop'}  {k:24s} {t!r:38s} {why}")
            if ok:
                extra.setdefault(k, []).append(t)

    n_new = sum(len(v["terms"]) for v in additions.values())
    n_ext = sum(len(v) for v in extra.values())
    print(
        f"\n{len(additions)} new thread(s) with {n_new} term(s); "
        f"{n_ext} term(s) added to existing threads"
    )

    if args.dry_run:
        print("dry run: narratives.yml untouched")
        return
    if not additions and not extra:
        print("nothing survived validation; narratives.yml untouched")
        return

    write_back(additions, extra)


def write_back(additions: dict[str, dict], extra: dict[str, list[str]]) -> None:
    """Append to narratives.yml by hand to preserve comments and ordering.

    yaml.dump would reformat the curated file and drop its comments, so new
    material is appended as text and existing lines are left exactly as they
    are. That also makes the git diff readable.
    """
    path = LEXICON_DIR / NARRATIVES_FILE
    lines = path.read_text().rstrip("\n").split("\n")

    for key, terms in extra.items():
        # Find the thread's terms block and append to the end of it.
        start = next(i for i, ln in enumerate(lines) if ln.startswith(f"{key}:"))
        end = start + 1
        while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
            end += 1
        insert = [f"    - {yaml_scalar(t)}" for t in terms]
        lines[end:end] = insert

    if additions:
        lines.append("")
        lines.append("# --- discovered by scripts/gemini_narratives.py ---")
        for key, body in additions.items():
            lines.append(f"{key}:")
            lines.append(f"  label: {body['label']}")
            lines.append("  terms:")
            lines.extend(f"    - {yaml_scalar(t)}" for t in body["terms"])

    path.write_text("\n".join(lines) + "\n")
    print(f"updated {path}")


def yaml_scalar(term: str) -> str:
    """Quote anything YAML would otherwise mangle."""
    if term != term.strip() or re.search(r"[:#\[\]{},&*?|>%@`\"']", term) or not term:
        return json.dumps(term)
    if term.replace(".", "").isdigit():
        return json.dumps(term)
    return term


if __name__ == "__main__":
    main()
