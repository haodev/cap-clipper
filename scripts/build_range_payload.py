"""Freeze the multi-day labeled CSV into range_payload.json.

Same scoring as the one-day demo (enrich_glp1), without hourly series or
hour-focus forensic cards.

Usage: python scripts/build_range_payload.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_payload import (  # noqa: E402
    build_anomalies,
    build_claims,
    build_narratives,
    select_feed,
    tweet_json,
)
from cc_paths import (  # noqa: E402
    DATA_DIR,
    ENRICHED_RANGE_PATH,
    LABELED_CSV_PATH,
    RANGE_PAYLOAD_PATH,
)
from enrich_glp1 import STANCE_VALUE, enrich_frame, pa_from_df  # noqa: E402

ID_COLUMNS = [
    "id",
    "author_id",
    "conversation_id",
    "reply_to_status_id",
    "reply_to_user_id",
    "quoting_id",
]


def load_labeled() -> pd.DataFrame:
    if not LABELED_CSV_PATH.exists():
        raise SystemExit(f"missing {LABELED_CSV_PATH}")
    df = pd.read_csv(
        LABELED_CSV_PATH,
        dtype={c: "string" for c in ID_COLUMNS},
        low_memory=False,
    )
    return df


def attach_grok_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Map Grok columns on ozempic_labeled.csv onto the llm_* fields the payload expects."""
    topics = df["topics"].fillna("").astype(str).str.replace("|", ";", regex=False)
    df["llm_topics"] = topics
    df["llm_primary_topic"] = topics.map(lambda s: s.split(";")[0] if s and s != "nan" else None)
    df["llm_intent"] = df["intent"].where(df["intent"].notna(), None)
    df["llm_stance"] = df["stance"].where(df["stance"].notna(), None)
    emotions = df["emotions"].fillna("").astype(str)
    df["llm_sarcastic"] = emotions.str.contains("sarcastic", case=False, na=False)
    df["llm_tone"] = emotions.where(emotions != "", None)
    df["llm_speaker"] = df["speaker"].where(df["speaker"].notna(), None)
    df["llm_confidence"] = df["confidence"].where(df["confidence"].notna(), None)
    risks = df["risks"].fillna("").astype(str).str.replace("|", ";", regex=False)
    df["llm_risks"] = risks
    df["sentiment_stance"] = df["llm_stance"].map(
        lambda s: STANCE_VALUE[s] if s in STANCE_VALUE else float("nan")
    )
    return df


def main() -> None:
    raw = load_labeled()
    df = enrich_frame(raw, attach_hourly=False, join_llm=False)
    df = attach_grok_labels(df)

    ENRICHED_RANGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa_from_df(df), ENRICHED_RANGE_PATH)

    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    orig = df[~df["is_retweet"]].copy()
    feed = select_feed(df)
    start = df["created_at"].min().strftime("%Y-%m-%d")
    end = df["created_at"].max().strftime("%Y-%m-%d")

    payload = {
        "meta": {
            "topic": "GLP-1 (Ozempic / Wegovy / Mounjaro / semaglutide)",
            "day_utc": None,
            "start_utc": start,
            "end_utc": end,
            "source": "ozempic_labeled.csv (Calcifer X firehose, 17 Aug–17 Sep 2026)",
            "firehose_rows_scanned": None,
            "english_rows": int((df["lang"] == "en").sum()) if "lang" in df.columns else None,
            "slice_rows": int(len(df)),
            "originals": int(len(orig)),
            "retweets": int(len(df) - len(orig)),
            "score_definitions": {
                "promo_score": "density of explicit commercial CTA/price language (0-1)",
                "coord_score": "same normalized text from multiple authors within 4h (0-1)",
                "astroturf_score": "coord_score outside the news register",
                "syndication_score": "coord_score inside the news register (wire copy)",
                "cap_score": "0.5*astroturf + 0.3*promo + 0.2*engagement oddity",
                "sentiment_vader": "lexicon baseline only, not a medical judgement",
                "sentiment_stance": "ordinal grok stance mapped to -1..+1; null when unlabeled",
                "llm_stance": "attitude toward using the drugs, not toward the tweet's other targets",
            },
            "label_provenance": {
                "source": "data/ozempic_labeled.csv (Grok labels joined per distinct text)",
                "not_a_judgement": "model labels are not medical or legal determinations",
            },
        },
        "hourly": [],
        "narratives": build_narratives(df, include_hourly=False),
        "claims": build_claims(df, include_hourly=False),
        "anomalies": build_anomalies(
            df, orig, include_hour_cards=False, window_label="range"
        ),
        "feed": [tweet_json(r) for _, r in feed.iterrows()],
    }

    RANGE_PAYLOAD_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote {RANGE_PAYLOAD_PATH}")
    print(
        f"rows={payload['meta']['slice_rows']} claims={len(payload['feed'])} "
        f"anomalies={len(payload['anomalies'])} {start}..{end}"
    )
    for card in payload["anomalies"]:
        print(f"  - {card['id']}: {card['headline']}")
    print(f"also wrote {ENRICHED_RANGE_PATH}")


if __name__ == "__main__":
    main()
