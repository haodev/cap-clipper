"""Freeze the analysis into demo_payload.json for the API and frontend.

Everything the product shows is precomputed here. No NLP or LLM calls at
request time.

Usage: python scripts/build_payload.py
"""
from __future__ import annotations

import json
import re

import pandas as pd
import pyarrow.parquet as pq

from cc_paths import DATA_DIR, ENRICHED_PATH, HOURLY_PATH, load_narratives

PAYLOAD_PATH = DATA_DIR / "demo_payload.json"
WS_RE = re.compile(r"\s+")
LOW_N = 15


def clean(text: str, limit: int = 400) -> str:
    text = WS_RE.sub(" ", str(text or "")).strip()
    return text[:limit]


def tweet_json(row: pd.Series) -> dict:
    return {
        "id": str(row["id"]),
        "author_id": str(row["author_id"]),
        # Joins a tweet to its entry in `claims`, so the hover card can draw
        # the spread curve of the claim this tweet is a copy of.
        "claim_id": str(row["text_hash"]),
        "created_at": row["created_at"].isoformat(),
        "body": clean(row["body"]),
        "is_retweet": bool(row["is_retweet"]),
        "register": str(row["register"]),
        "diffusion": str(row["diffusion"]),
        "narratives": [n for n in str(row.get("narratives") or "").split(";") if n],
        "drugs": [d for d in str(row.get("drugs") or "").split(";") if d],
        "like_count": int(row.get("like_count") or 0),
        "reply_count": int(row.get("reply_count") or 0),
        "retweet_count": int(row.get("retweet_count") or 0),
        "affiliate_code": None if pd.isna(row["affiliate_code"]) else str(row["affiliate_code"]),
        "scores": {
            "cap_score": round(float(row["cap_score"]), 3),
            "promo_score": round(float(row["promo_score"]), 3),
            "coord_score": round(float(row["coord_score"]), 3),
            "astroturf_score": round(float(row["astroturf_score"]), 3),
            "syndication_score": round(float(row["syndication_score"]), 3),
            "affiliate_ring": round(float(row["affiliate_ring"]), 3),
            "sentiment_vader": round(float(row["sentiment_vader"]), 3),
            "sentiment_stance": None
            if pd.isna(row.get("sentiment_stance"))
            else round(float(row["sentiment_stance"]), 3),
        },
        "labels": {
            "primary_topic": None if pd.isna(row.get("llm_primary_topic")) else str(row["llm_primary_topic"]),
            "intent": None if pd.isna(row.get("llm_intent")) else str(row["llm_intent"]),
            "stance": None if pd.isna(row.get("llm_stance")) else str(row["llm_stance"]),
            "sarcastic": bool(row.get("llm_sarcastic")),
            "tone": None if pd.isna(row.get("llm_tone")) else str(row["llm_tone"]),
            "speaker": None if pd.isna(row.get("llm_speaker")) else str(row["llm_speaker"]),
            "confidence": None if pd.isna(row.get("llm_confidence")) else str(row["llm_confidence"]),
        },
        "tags": [
            name
            for name, col in (
                ("side_effect", "tag_side_effect"),
                ("shortage", "tag_shortage"),
                ("cosmetic", "tag_cosmetic"),
                ("telehealth", "tag_telehealth"),
            )
            if bool(row[col])
        ],
        "cluster": {
            "size": int(row["cluster_size"]),
            "authors": int(row["cluster_authors"]),
        },
    }


def build_hourly(df: pd.DataFrame, orig: pd.DataFrame) -> list[dict]:
    hourly_en = pq.read_table(HOURLY_PATH).to_pandas()
    hourly_en["hour"] = pd.to_datetime(hourly_en["hour"], utc=True)

    topic = (
        orig.groupby("hour")
        .agg(
            originals=("id", "size"),
            sentiment=("sentiment_vader", "mean"),
            side_effect_rate=("tag_side_effect", "mean"),
            promo=("promo_score", "mean"),
            astroturf=("astroturf_score", "max"),
        )
        .reset_index()
    )
    rts = df[df["is_retweet"]].groupby("hour").size().rename("retweets").reset_index()

    merged = hourly_en.merge(topic, on="hour", how="left").merge(rts, on="hour", how="left")
    merged["originals"] = merged["originals"].fillna(0).astype(int)
    merged["retweets"] = merged["retweets"].fillna(0).astype(int)
    merged["topic_share_per_100k"] = (
        (merged["originals"] + merged["retweets"]) / merged["en_count"] * 100_000
    )

    out = []
    for _, r in merged.iterrows():
        out.append(
            {
                "hour": r["hour"].isoformat(),
                "en_firehose": int(r["en_count"]),
                "originals": int(r["originals"]),
                "retweets": int(r["retweets"]),
                "topic_share_per_100k": round(float(r["topic_share_per_100k"]), 2),
                "sentiment": None if pd.isna(r["sentiment"]) else round(float(r["sentiment"]), 3),
                "side_effect_rate": None
                if pd.isna(r["side_effect_rate"])
                else round(float(r["side_effect_rate"]), 3),
                "promo": None if pd.isna(r["promo"]) else round(float(r["promo"]), 3),
                "astroturf": None if pd.isna(r["astroturf"]) else round(float(r["astroturf"]), 3),
                "low_confidence": bool(r["originals"] < LOW_N),
            }
        )
    return out


# Single source of truth: a theme discovered later shows up here automatically.
NARRATIVE_LABELS = {k: v["label"] for k, v in load_narratives().items()}


def _sarcasm_gap(sub: pd.DataFrame) -> float | None:
    if "sentiment_stance" not in sub.columns or sub["sentiment_stance"].isna().all():
        return None
    return round(float(sub["sentiment_vader"].mean() - sub["sentiment_stance"].mean()), 3)


def build_narratives(df: pd.DataFrame) -> list[dict]:
    """Volume and shape of every discovered narrative thread, ranked."""
    out = []
    for key, label in NARRATIVE_LABELS.items():
        col = f"narr_{key}"
        if col not in df.columns:
            continue
        sub = df[df[col]]
        if sub.empty:
            continue
        orig = sub[~sub["is_retweet"]]
        by_hour = sub.groupby(sub["hour"]).size()
        out.append(
            {
                "key": key,
                "label": label,
                "total": int(len(sub)),
                "originals": int(len(orig)),
                "retweets": int(len(sub) - len(orig)),
                "unique_authors": int(sub["author_id"].nunique()),
                "amplification_ratio": round(float(len(sub) - len(orig)) / max(len(orig), 1), 2),
                "mean_sentiment": round(float(sub["sentiment_vader"].mean()), 3),
                "mean_stance": None
                if "sentiment_stance" not in sub.columns or sub["sentiment_stance"].isna().all()
                else round(float(sub["sentiment_stance"].mean()), 3),
                "sarcasm_rate": None
                if "llm_sarcastic" not in sub.columns
                else round(float(sub["llm_sarcastic"].mean()), 3),
                "sarcasm_gap": _sarcasm_gap(sub),
                "peak_hour": by_hour.idxmax().isoformat() if len(by_hour) else None,
                "hourly": [int(by_hour.get(h, 0)) for h in sorted(df["hour"].unique())],
                "top_example": clean(
                    sub.sort_values("retweet_count", ascending=False).iloc[0]["body"], 220
                ),
            }
        )
    return sorted(out, key=lambda n: -n["total"])


def build_claims(df: pd.DataFrame) -> list[dict]:
    """Every claim that actually spread, with its diffusion verdict."""
    spreading = df[df["claim_copies"] >= 5]
    out = []
    for text_hash, grp in spreading.groupby("text_hash"):
        grp = grp.sort_values("created_at")
        by_hour = grp.groupby("hour").size()
        out.append(
            {
                "claim_id": str(text_hash),
                "text": clean(grp.iloc[0]["body"], 240),
                "diffusion": str(grp.iloc[0]["diffusion"]),
                "copies": int(len(grp)),
                "unique_authors": int(grp["author_id"].nunique()),
                "author_ratio": round(float(grp.iloc[0]["claim_author_ratio"]), 3),
                "burstiness": round(float(grp.iloc[0]["claim_burstiness"]), 3),
                "span_minutes": int(grp.iloc[0]["claim_span_min"]),
                "first_seen": grp["created_at"].min().isoformat(),
                "peak_hour": by_hour.idxmax().isoformat(),
                "hourly": [int(by_hour.get(h, 0)) for h in sorted(df["hour"].unique())],
                "narratives": [
                    k for k in NARRATIVE_LABELS if grp.iloc[0].get(f"narr_{k}", False)
                ],
                "mean_sentiment": round(float(grp["sentiment_vader"].mean()), 3),
                "stance": None if pd.isna(grp.iloc[0].get("llm_stance")) else str(grp.iloc[0]["llm_stance"]),
                "intent": None if pd.isna(grp.iloc[0].get("llm_intent")) else str(grp.iloc[0]["llm_intent"]),
                "sarcastic": bool(grp.iloc[0].get("llm_sarcastic")),
            }
        )
    return sorted(out, key=lambda c: -c["copies"])


def build_anomalies(df: pd.DataFrame, orig: pd.DataFrame) -> list[dict]:
    """Three frozen forensic cards. Evidence only; Gemini prose is added later."""
    cards: list[dict] = []

    # 0. The claim that dominated the day, with its organic/coordinated verdict.
    spread = df[df["claim_copies"] >= 5]
    if len(spread):
        top_hash = spread.groupby("text_hash").size().idxmax()
        grp = spread[spread["text_hash"] == top_hash].sort_values("created_at")
        cards.append(
            {
                "id": "dominant_claim",
                "narrative_type": "organic_virality",
                "headline": "One claim drove a quarter of the day's GLP-1 volume",
                # Lets the UI point the feed at the rows behind this card.
                "focus": {"type": "claim", "value": str(top_hash)},
                "evidence": {
                    "text": clean(grp.iloc[0]["body"], 220),
                    "copies": int(len(grp)),
                    "unique_authors": int(grp["author_id"].nunique()),
                    "repeat_authors": int(len(grp) - grp["author_id"].nunique()),
                    "diffusion": str(grp.iloc[0]["diffusion"]),
                    "burstiness": round(float(grp.iloc[0]["claim_burstiness"]), 3),
                    "span_minutes": int(grp.iloc[0]["claim_span_min"]),
                    "why_it_matters": (
                        "Every copy came from a different account and spread across the whole "
                        "day, so the coordination score is zero. High volume is not evidence "
                        "of a campaign."
                    ),
                },
                "tweets": [tweet_json(r) for _, r in grp.head(3).iterrows()],
            }
        )

    # 1. Affiliate ring: one promo code, multiple accounts, multiple vendor brands.
    coded = orig[orig["affiliate_code"].notna()]
    if len(coded):
        rings = (
            coded.groupby("affiliate_code")
            .agg(posts=("id", "size"), authors=("author_id", "nunique"))
            .sort_values(["authors", "posts"], ascending=False)
        )
        code = rings.index[0]
        members = coded[coded["affiliate_code"] == code].sort_values("created_at")
        gaps = members["created_at"].diff().dropna()
        cards.append(
            {
                "id": "affiliate_ring",
                "narrative_type": "telehealth_astroturf",
                "headline": f"One affiliate code ({code}) shared by multiple accounts and vendor brands",
                "focus": {"type": "affiliate_code", "value": str(code)},
                "evidence": {
                    "affiliate_code": str(code),
                    "posts": int(len(members)),
                    "unique_authors": int(members["author_id"].nunique()),
                    "distinct_templates": int(members["text_hash"].nunique()),
                    "window_start": members["created_at"].min().isoformat(),
                    "window_end": members["created_at"].max().isoformat(),
                    "min_gap_seconds": int(gaps.min().total_seconds()) if len(gaps) else None,
                    "mean_promo_score": round(float(members["promo_score"].mean()), 3),
                    "why_it_matters": (
                        "Different vendor names and rewritten copy defeat duplicate-text "
                        "detection, but the shared code links the accounts."
                    ),
                },
                "tweets": [tweet_json(r) for _, r in members.head(6).iterrows()],
            }
        )

    # 2. Syndication: identical headline, many authors, news register.
    news_cl = (
        orig[orig["register"] == "news"]
        .groupby("text_hash")
        .agg(n=("id", "size"), authors=("author_id", "nunique"))
        .sort_values(["authors", "n"], ascending=False)
    )
    if len(news_cl):
        top_hash = news_cl.index[0]
        members = orig[orig["text_hash"] == top_hash].sort_values("created_at")
        cards.append(
            {
                "id": "news_syndication",
                "narrative_type": "syndication_not_astroturf",
                "headline": "Identical headline from many accounts - wire copy, not a campaign",
                "focus": {"type": "claim", "value": str(top_hash)},
                "evidence": {
                    "template": clean(members.iloc[0]["body"], 200),
                    "posts": int(len(members)),
                    "unique_authors": int(members["author_id"].nunique()),
                    "window_start": members["created_at"].min().isoformat(),
                    "window_end": members["created_at"].max().isoformat(),
                    "max_coord_score": round(float(members["coord_score"].max()), 3),
                },
                "tweets": [tweet_json(r) for _, r in members.head(5).iterrows()],
            }
        )

    # 3. Side-effect concentration: hour with the highest tagged rate.
    se_hours = (
        orig.groupby("hour")
        .agg(n=("id", "size"), rate=("tag_side_effect", "mean"))
        .query(f"n >= {LOW_N}")
        .sort_values("rate", ascending=False)
    )
    if len(se_hours):
        peak_hour = se_hours.index[0]
        baseline = orig[orig["hour"] < peak_hour]["tag_side_effect"].mean()
        members = orig[(orig["hour"] == peak_hour) & orig["tag_side_effect"]].nsmallest(
            3, "sentiment_vader"
        )
        worst = orig[orig["tag_side_effect"]].nsmallest(3, "sentiment_vader")
        cards.append(
            {
                "id": "side_effect_concentration",
                "narrative_type": "side_effect_panic",
                "headline": "Side-effect mentions concentrate in one hour",
                "focus": {"type": "hour", "value": peak_hour.isoformat()},
                "evidence": {
                    "hour": peak_hour.isoformat(),
                    "originals_in_hour": int(se_hours.iloc[0]["n"]),
                    "side_effect_rate": round(float(se_hours.iloc[0]["rate"]), 3),
                    "baseline_rate_before": round(float(baseline), 3),
                    "lift": round(float(se_hours.iloc[0]["rate"] / max(baseline, 1e-6)), 2),
                },
                "tweets": [tweet_json(r) for _, r in members.head(3).iterrows()]
                + [tweet_json(r) for _, r in worst.iterrows()],
            }
        )

    # 4. VADER reads hostile sarcasm as positive. Only if stance labels exist.
    if "sentiment_stance" in df.columns and not df["sentiment_stance"].isna().all():
        sarcastic = df[df.get("llm_sarcastic", False) == True] if "llm_sarcastic" in df.columns else df.iloc[0:0]
        if len(sarcastic):
            vader_mean = float(sarcastic["sentiment_vader"].mean())
            stance_mean = float(sarcastic["sentiment_stance"].mean())
            top = sarcastic.sort_values("retweet_count", ascending=False).iloc[0]
            cards.append(
                {
                    "id": "sentiment_blindspot",
                    "narrative_type": "sentiment_blindspot",
                    "headline": "The day's most hostile jokes read as positive to the lexicon",
                    "focus": {"type": "claim", "value": str(top["text_hash"])},
                    "evidence": {
                        "text": clean(top["body"], 220),
                        "sarcastic_posts": int(len(sarcastic)),
                        "vader_mean_on_sarcasm": round(vader_mean, 3),
                        "stance_mean_on_sarcasm": round(stance_mean, 3),
                        "gap": round(vader_mean - stance_mean, 3),
                        "why_it_matters": (
                            "VADER scores 'Funny how that works' as positive. Stance is "
                            "attitude toward the drug, labeled on the claim, and does not "
                            "treat mockery of a movement as endorsement of the drug."
                        ),
                    },
                    "tweets": [tweet_json(r) for _, r in sarcastic.drop_duplicates("text_hash").head(3).iterrows()],
                }
            )

    return cards


def main() -> None:
    if not ENRICHED_PATH.exists():
        raise SystemExit(f"missing {ENRICHED_PATH}; run scripts/enrich_glp1.py first")

    df = pq.read_table(ENRICHED_PATH).to_pandas()
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    orig = df[~df["is_retweet"]].copy()

    # One row per distinct claim, not per tweet. The whole slice is small enough
    # to ship, but 193 of its rows are the same retweet, and a narrative filter
    # over raw rows either returns a wall of duplicates or, for the small
    # narratives, nothing at all. The representative is the copy with the most
    # engagement; `cluster.size` carries how many copies it stands for.
    feed = (
        df.sort_values(["retweet_count", "like_count"], ascending=False)
        .drop_duplicates(subset="text_hash")
        .sort_values(["cluster_size", "retweet_count"], ascending=False)
    )
    # minor_involved is an internal suppression flag, never a displayed badge.
    if "llm_risks" in feed.columns:
        feed = feed[~feed["llm_risks"].fillna("").str.contains("minor_involved")]

    payload = {
        "meta": {
            "topic": "GLP-1 (Ozempic / Wegovy / Mounjaro / semaglutide)",
            "day_utc": "2026-08-17",
            "source": "Calcifer X firehose, shards 0-22",
            "firehose_rows_scanned": 23_000_000,
            "english_rows": int(pq.read_table(HOURLY_PATH).to_pandas()["en_count"].sum()),
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
                "sentiment_stance": "ordinal llm_stance mapped to -1..+1; null when unlabeled",
                "llm_stance": "attitude toward using the drugs, not toward the tweet's other targets",
            },
            "label_provenance": {
                "source": "scripts/gemini_label.py cache",
                "not_a_judgement": "model labels are not medical or legal determinations",
            },
        },
        "hourly": build_hourly(df, orig),
        "narratives": build_narratives(df),
        "claims": build_claims(df),
        "anomalies": build_anomalies(df, orig),
        "feed": [tweet_json(r) for _, r in feed.iterrows()],
    }

    PAYLOAD_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote {PAYLOAD_PATH}")
    print(
        f"hourly={len(payload['hourly'])} anomalies={len(payload['anomalies'])} "
        f"feed={len(payload['feed'])}"
    )
    for card in payload["anomalies"]:
        print(f"  - {card['id']}: {card['headline']}")


if __name__ == "__main__":
    main()
