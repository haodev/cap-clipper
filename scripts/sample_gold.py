"""Stratified 50-claim gold sample. Does not invent labels.

Taking the top 50 by reach would be 50 near-copies of the culture-war joke.
Strata: 15 largest claims, 15 lexicon-untagged, 10 promo/affiliate, 10 tail.

Usage: python scripts/sample_gold.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cc_paths import ENRICHED_PATH, ROOT  # noqa: E402
from gemini_narratives import distinct_claims  # noqa: E402

GOLD_PATH = ROOT / "gold" / "labels_50.csv"
FIELDS = [
    "claim_id",
    "example_tweet_id",
    "text",
    "primary_topic",
    "topics",
    "drugs",
    "intent",
    "tone",
    "sarcastic",
    "stance",
    "speaker",
    "risks",
    "confidence",
    "labeler",
    "notes",
    "vader",
]


def main() -> None:
    df = distinct_claims(pd.read_parquet(ENRICHED_PATH))
    rng = 20260817
    picked: list[pd.Series] = []
    used: set[str] = set()

    def take(pool: pd.DataFrame, n: int) -> None:
        leftover = pool[~pool["text_hash"].isin(used)]
        if leftover.empty:
            return
        sample = leftover.sample(n=min(n, len(leftover)), random_state=rng)
        for _, row in sample.iterrows():
            used.add(str(row["text_hash"]))
            picked.append(row)

    take(df.nlargest(40, "retweet_count"), 15)
    untagged = df[df["narratives"].fillna("") == ""]
    take(untagged, 15)
    promo = df[(df["promo_score"] > 0) | df["affiliate_code"].notna()]
    take(promo, 10)
    take(df, 10)

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLD_PATH.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for row in picked:
            w.writerow(
                {
                    "claim_id": row["text_hash"],
                    "example_tweet_id": row["id"],
                    "text": " ".join(str(row["body"]).split())[:280],
                    "drugs": row.get("drugs") or "",
                    "vader": f"{float(row['sentiment_vader']):.3f}",
                    "labeler": "",
                    "primary_topic": "",
                    "topics": "",
                    "intent": "",
                    "tone": "",
                    "sarcastic": "",
                    "stance": "",
                    "speaker": "",
                    "risks": "",
                    "confidence": "",
                    "notes": "",
                }
            )
    print(f"wrote {len(picked)} blank gold rows to {GOLD_PATH}")


if __name__ == "__main__":
    main()
