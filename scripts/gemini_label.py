"""Per-claim Gemini labels for stance, sarcasm, intent, speaker, topics.

Labels the 406 distinct claims, not the 742 posts. Cached by text_hash plus a
prompt-version hash so the demo stays deterministic: if Gemini is unreachable
the payload still builds from whatever is already on disk.

The human labeling guide's taxonomy is adopted; its I/O spec is not. We send
the RT-stripped text, never a copy-count, and we ask the model to echo a
small integer index rather than the hex hash.

Usage:
    python scripts/gemini_label.py --dry-run
    python scripts/gemini_label.py
    python scripts/gemini_label.py --score
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cc_paths import ENRICHED_PATH, LABEL_CACHE_PATH, ROOT  # noqa: E402
from gemini import api_key, generate, generate_json  # noqa: E402
from gemini_narratives import distinct_claims  # noqa: E402

PROMPT_VERSION = "claim-label-v1"
GOLD_PATH = ROOT / "gold" / "labels_50.csv"
BATCH = 30
MAX_TOKENS = 8192

TOPICS = [
    "affordability_access",
    "grey_market",
    "telehealth_rx",
    "marketing_promo",
    "side_effects_safety",
    "medical_condition",
    "personal_experience",
    "weight_loss_results",
    "celebrity_watch",
    "culture_war_body",
    "eating_disorder",
    "appearance_commentary",
    "politics_policy",
    "pharma_industry_critique",
    "finance_investing",
    "science_news",
    "conspiracy_framing",
    "humor_meme",
    "dating_sexual",
    "religion_morality",
    "fitness_muscle",
    "food_industry",
    "off_label_use",
    "spam_irrelevant",
]
INTENTS = [
    "share_experience",
    "seek_info",
    "give_advice",
    "inform_news",
    "promote_sell",
    "joke",
    "opinion_argue",
    "criticize_attack",
    "praise_endorse",
    "gossip_speculate",
    "vent",
    "other",
]
STANCES = [
    "strongly_positive",
    "positive",
    "mixed",
    "neutral",
    "negative",
    "strongly_negative",
    "unclear",
]
TONES = ["sarcastic", "shaming_mocking", "angry", "anxious_fearful", "neutral_factual"]
SPEAKERS = [
    "current_user",
    "former_user",
    "prospective_user",
    "caregiver_proxy",
    "health_professional",
    "seller_vendor",
    "observer_commentator",
    "unclear",
]
RISKS = [
    "grey_market_sourcing",
    "vendor_solicitation",
    "unverified_dosing_advice",
    "eating_disorder_signal",
    "unsourced_health_claim",
    "minor_involved",
    "hateful_content",
]

STANCE_VALUE = {
    "strongly_positive": 1.0,
    "positive": 0.5,
    "mixed": 0.0,
    "neutral": 0.0,
    "negative": -0.5,
    "strongly_negative": -1.0,
}

PROMPT = """You are labeling GLP-1 drug posts from one UTC day of X.

Each item is a distinct CLAIM (normalized text). Label the original speaker of
the words, even if the text arrived as a retweet. Do not infer coordination,
bots, or campaigns from how often a line was repeated — you are not given a
copy count on purpose.

Stance is attitude toward USING these drugs, not toward the tweet's other
targets. A jab at body-positivity that never praises the drug is mixed or
unclear, not positive. "Funny how that works" is sarcastic.

Topics are an unordered set. Also pick one primary_topic. fitness_muscle
covers muscle-loss fear and the supplements sold against it — do not invent a
second name for that thread.

tone is exactly one of: sarcastic, shaming_mocking, angry, anxious_fearful,
neutral_factual. sarcastic is also a boolean.

risks.unsourced_health_claim = a definite health assertion with no citation,
study, or source. Do not adjudicate whether the claim is medically true.
risks.minor_involved = poster appears under 18, or the post is about a minor
using these drugs. Use sparingly.

Allowed values
- topics / primary_topic: {topics}
- intent: {intents}
- stance: {stances}
- tone: {tones}
- speaker: {speakers}
- risks: {risks}

Return JSON: {{"labels": [{{"id": 0, "primary_topic": "...", "topics": [...],
"intent": "...", "stance": "...", "sarcastic": true, "tone": "...",
"speaker": "...", "risks": [...], "confidence": "high|medium|low"}}]}}
Echo every id you received. No extra keys.

Examples of the intended reading (from this day's real posts):
{shots}

Items:
{items}"""

# Real rows from this slice, not the guide's examples from a different corpus.
SHOTS = [
    {
        "text": "Ozempic hit the streets and the entire body positivity movement died. Funny how that works.",
        "label": {
            "primary_topic": "culture_war_body",
            "topics": ["culture_war_body", "humor_meme"],
            "intent": "joke",
            "stance": "mixed",
            "sarcastic": True,
            "tone": "sarcastic",
            "speaker": "observer_commentator",
            "risks": [],
            "confidence": "high",
        },
    },
    {
        "text": "Amino Club has Retatrutide in stock! Use code PROFPEPTIDE for 35% off through August 31.",
        "label": {
            "primary_topic": "marketing_promo",
            "topics": ["marketing_promo", "grey_market"],
            "intent": "promote_sell",
            "stance": "positive",
            "sarcastic": False,
            "tone": "neutral_factual",
            "speaker": "seller_vendor",
            "risks": ["vendor_solicitation", "grey_market_sourcing"],
            "confidence": "high",
        },
    },
    {
        "text": "I lost 38 lbs without ozempic or GLP-1s. It's not that hard tbh. Just focus.",
        "label": {
            "primary_topic": "weight_loss_results",
            "topics": ["weight_loss_results", "culture_war_body"],
            "intent": "opinion_argue",
            "stance": "negative",
            "sarcastic": False,
            "tone": "shaming_mocking",
            "speaker": "observer_commentator",
            "risks": [],
            "confidence": "medium",
        },
    },
]


def cache_key(text_hash: str) -> str:
    return f"{text_hash}:{PROMPT_VERSION}"


def load_cache() -> dict:
    if not LABEL_CACHE_PATH.exists():
        return {}
    return json.loads(LABEL_CACHE_PATH.read_text())


def save_cache(cache: dict) -> None:
    LABEL_CACHE_PATH.write_text(json.dumps(cache, indent=1))


def strip_rt(text: str) -> str:
    t = (text or "").strip()
    if t.lower().startswith("rt @"):
        cut = t.find(":")
        if cut != -1:
            return t[cut + 1 :].strip()
    return t


def prompt_for(batch: list[tuple[int, str]]) -> str:
    shots = json.dumps(SHOTS, indent=1)
    items = json.dumps([{"id": i, "text": text} for i, text in batch], indent=1)
    return PROMPT.format(
        topics=", ".join(TOPICS),
        intents=", ".join(INTENTS),
        stances=", ".join(STANCES),
        tones=", ".join(TONES),
        speakers=", ".join(SPEAKERS),
        risks=", ".join(RISKS),
        shots=shots,
        items=items,
    )


def sanitize(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    stance = raw.get("stance") if raw.get("stance") in STANCES else "unclear"
    tone = raw.get("tone") if raw.get("tone") in TONES else "neutral_factual"
    intent = raw.get("intent") if raw.get("intent") in INTENTS else "other"
    speaker = raw.get("speaker") if raw.get("speaker") in SPEAKERS else "unclear"
    topics = [t for t in (raw.get("topics") or []) if t in TOPICS][:4]
    primary = raw.get("primary_topic")
    if primary not in TOPICS:
        primary = topics[0] if topics else "spam_irrelevant"
    if primary not in topics:
        topics = [primary] + topics
    risks = [r for r in (raw.get("risks") or []) if r in RISKS]
    conf = raw.get("confidence") if raw.get("confidence") in ("high", "medium", "low") else "medium"
    sarcastic = bool(raw.get("sarcastic")) or tone == "sarcastic"
    return {
        "primary_topic": primary,
        "topics": topics,
        "intent": intent,
        "stance": stance,
        "sarcastic": sarcastic,
        "tone": tone,
        "speaker": speaker,
        "risks": risks,
        "confidence": conf,
    }


def probe_quota(key: str) -> str | None:
    """One tiny call, no backoff. Returns an error string if we must stop."""
    try:
        generate("Reply with the single word ok.", key, max_tokens=8, retries=1)
    except RuntimeError as exc:
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            return msg
        if "503" in msg:
            return msg
        return msg
    return None


def label_batch(batch: list[tuple[int, str]], key: str) -> dict[int, dict]:
    size = len(batch)
    while size >= 5:
        chunk = batch[:size]
        try:
            reply = generate_json(prompt_for(chunk), key, temperature=0, max_tokens=MAX_TOKENS)
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"  batch of {size} failed: {exc}")
            size = size // 2
            continue
        rows = reply.get("labels") if isinstance(reply, dict) else reply
        if not isinstance(rows, list):
            size = size // 2
            continue
        out: dict[int, dict] = {}
        for row in rows:
            if not isinstance(row, dict) or "id" not in row:
                continue
            try:
                idx = int(row["id"])
            except (TypeError, ValueError):
                continue
            cleaned = sanitize(row)
            if cleaned:
                out[idx] = cleaned
        missing = [i for i, _ in chunk if i not in out]
        if missing and size > 1:
            print(f"  missing {len(missing)} ids, shrinking batch")
            size = size // 2
            continue
        return out
    return {}


def run_label(dry_run: bool) -> None:
    if not ENRICHED_PATH.exists():
        raise SystemExit(f"missing {ENRICHED_PATH}; run scripts/enrich_glp1.py first")
    df = pd.read_parquet(ENRICHED_PATH)
    claims = distinct_claims(df)
    cache = load_cache()
    pending = []
    for _, row in claims.iterrows():
        h = str(row["text_hash"])
        if cache_key(h) in cache:
            continue
        pending.append((h, strip_rt(str(row["body"]))))
    print(f"{len(claims)} claims, {len(pending)} unlabeled, {len(claims) - len(pending)} cached")

    if dry_run:
        sample = pending[:3] or [(str(claims.iloc[0]["text_hash"]), strip_rt(str(claims.iloc[0]["body"])))]
        print(prompt_for(list(enumerate(t for _, t in sample))))
        print("dry run: cache untouched")
        return

    key = api_key()
    if not key:
        raise SystemExit("GEMINI_API_KEY not found in the environment or .env")
    if not pending:
        print("nothing to label")
        return

    blocked = probe_quota(key)
    if blocked:
        print(f"quota probe failed — stopping without a batch loop:\n{blocked}")
        return

    for start in range(0, len(pending), BATCH):
        chunk = pending[start : start + BATCH]
        indexed = [(i, text) for i, (_, text) in enumerate(chunk)]
        print(f"batch {start // BATCH + 1}: {len(chunk)} claims")
        labeled = label_batch(indexed, key)
        wrote = 0
        for i, (h, _) in enumerate(chunk):
            if i in labeled:
                cache[cache_key(h)] = labeled[i]
                wrote += 1
        save_cache(cache)
        print(f"  wrote {wrote}/{len(chunk)}  cache={len(cache)}")
        missing = [i for i in range(len(chunk)) if i not in labeled]
        if missing:
            print(f"  retrying {len(missing)} missing one-by-one")
            for i in missing:
                h, text = chunk[i]
                one = label_batch([(0, text)], key)
                if 0 in one:
                    cache[cache_key(h)] = one[0]
                    save_cache(cache)


def score() -> None:
    if not GOLD_PATH.exists():
        print(f"no gold file at {GOLD_PATH}")
        return
    rows = [r for r in csv.DictReader(GOLD_PATH.open()) if (r.get("stance") or "").strip()]
    print(f"gold labeled rows={len(rows)}")
    if not rows:
        print("gold is empty; run scripts/sample_gold.py then fill stance/sarcastic")
        return
    cache = load_cache()
    paired = []
    for r in rows:
        pred = cache.get(cache_key(r["claim_id"]))
        if pred:
            paired.append((r, pred))
    print(f"paired with cache={len(paired)}")
    if not paired:
        print("no overlapping cache entries; run scripts/gemini_label.py first")
        return

    sarcastic = [(g, p) for g, p in paired if str(g.get("sarcastic")).lower() in ("1", "true", "yes")]
    disagree = 0
    for g, _p in sarcastic:
        human = STANCE_VALUE.get(g["stance"])
        try:
            vader = float(g.get("vader") or "nan")
        except ValueError:
            vader = float("nan")
        if human is None or math.isnan(vader):
            continue
        if (vader > 0 and human < 0) or (vader < 0 and human > 0):
            disagree += 1
    n_sarc = len(sarcastic)
    print(
        f"VADER's sign disagrees with human stance on "
        f"{(disagree / n_sarc):.0%} of sarcastic claims ({disagree}/{n_sarc})"
        if n_sarc
        else "VADER's sign disagrees with human stance on n/a of sarcastic claims (none labeled sarcastic)"
    )

    def exact(field: str) -> float:
        ok = sum(1 for g, p in paired if g.get(field) == p.get(field))
        return ok / len(paired)

    print(f"exact stance={exact('stance'):.2f} intent={exact('intent'):.2f} speaker={exact('speaker'):.2f}")

    order = {s: i for i, s in enumerate(STANCES)}
    band = 0
    kappa_n = 0
    for g, p in paired:
        if g.get("stance") in order and p.get("stance") in order:
            kappa_n += 1
            if abs(order[g["stance"]] - order[p["stance"]]) <= 1:
                band += 1
    if kappa_n:
        print(f"stance ±1-band={band / kappa_n:.2f}")
        print(f"stance Cohen's κ={_kappa([g['stance'] for g, _ in paired], [p['stance'] for _, p in paired]):.2f}")


def _kappa(gold: list[str], pred: list[str]) -> float:
    n = len(gold)
    if not n:
        return float("nan")
    agree = sum(a == b for a, b in zip(gold, pred)) / n
    cg, cp = Counter(gold), Counter(pred)
    chance = sum((cg[k] / n) * (cp[k] / n) for k in set(cg) | set(cp))
    if chance == 1:
        return 1.0
    return (agree - chance) / (1 - chance)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    if args.score:
        score()
        return
    run_label(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
