"""Local features on the GLP-1 slice: tags, promo, coordination, VADER, cap_score.

Usage: python scripts/enrich_glp1.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict

import pandas as pd
import pyarrow.parquet as pq

from cc_paths import (
    CURATED_PATH,
    ENRICHED_PATH,
    HOURLY_PATH,
    LABEL_CACHE_PATH,
    load_groups,
    load_narratives,
    load_terms,
)

URL_RE = re.compile(r"https?://\S+|t\.co/\S+", re.I)
MENTION_RE = re.compile(r"@\w+")
RT_RE = re.compile(r"^RT\s+@\w+:\s*|^RT\s+", re.I)
WS_RE = re.compile(r"\s+")
# "use code FOO", "promo code: FOO", "code FOO for 10% off"
CODE_RE = re.compile(r"(?:use|promo|discount|coupon)\s+code:?\s+([A-Za-z0-9]{4,20})\b", re.I)
LOW_N = 15


def normalize(text: str) -> str:
    text = text or ""
    text = RT_RE.sub("", text)
    text = URL_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = text.lower()
    return WS_RE.sub(" ", text).strip()


def text_hash(text: str) -> str:
    return hashlib.md5(normalize(text).encode("utf-8")).hexdigest()[:16]


def tag_any(text: str, terms: list[str]) -> bool:
    lower = (text or "").lower()
    return any(t in lower for t in terms)


def drug_matcher(terms: list[str]) -> re.Pattern:
    """Word-start match for drug names, unlike the plain substring tags.

    Drug names are entities, so precision matters more than recall: bare
    containment makes "glp1" fire on the record catalogue number "wiglp136".
    Anchoring the left edge to a word boundary still catches plurals and
    stems ("glp1s", "tirz" inside "tirzepatide").
    """
    return re.compile("|".join(rf"\b{re.escape(t)}" for t in terms))


def promo_score(text: str, strong: list[str], weak: list[str]) -> float:
    lower = (text or "").lower()
    n_strong = sum(1 for t in strong if t in lower)
    n_weak = sum(1 for t in weak if t in lower)
    if not n_strong and not n_weak:
        return 0.0
    return min(1.0, (2 * n_strong + n_weak) / 4.0)


def affiliate_code(text: str) -> str | None:
    match = CODE_RE.search(text or "")
    return match.group(1).upper() if match else None


def classify_register(text: str, news_cues: list[str], fp_cues: list[str]) -> str:
    """news = wire/headline copy, personal = first-person account, other = neither."""
    padded = f" {(text or '').lower()} "
    if any(cue in padded for cue in news_cues):
        return "news"
    if any(cue in padded for cue in fp_cues):
        return "personal"
    return "other"


def engagement_oddity(row: pd.Series) -> float:
    if row["is_retweet"]:
        return 0.0
    likes = float(row.get("like_count") or 0)
    replies = float(row.get("reply_count") or 0)
    rts = float(row.get("retweet_count") or 0)
    if rts <= 0:
        return 0.0
    return min(1.0, rts / (likes + replies + 1.0) / 50.0)


def vader_scores(texts: list[str]) -> list[float]:
    try:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
    except ImportError as exc:
        raise SystemExit("nltk is required: pip install nltk") from exc
    try:
        sia = SentimentIntensityAnalyzer()
    except LookupError as exc:
        raise SystemExit(
            "VADER lexicon missing. Place vader_lexicon.zip in ~/nltk_data/sentiment/ "
            "(curl the nltk_data package; python.org SSL is broken on this machine)."
        ) from exc
    return [float(sia.polarity_scores(t or "")["compound"]) for t in texts]


def enrich() -> pd.DataFrame:
    if not CURATED_PATH.exists():
        raise SystemExit(f"missing {CURATED_PATH}; run python scripts/extract_glp1.py first")

    df = pq.read_table(CURATED_PATH).to_pandas()
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["hour"] = df["created_at"].dt.floor("h")
    df["is_retweet"] = df["is_retweet"].astype(bool)
    df["text_norm"] = df["body"].map(normalize)
    df["text_hash"] = df["body"].map(text_hash)

    promo = load_groups("promo.yml")
    promo_terms = promo["strong"] + promo["weak"]
    register_cues = load_groups("register.yml")
    se_terms = load_terms("side_effect.yml")
    sh_terms = load_terms("shortage.yml")
    co_terms = load_terms("cosmetic.yml")

    df["tag_side_effect"] = df["body"].map(lambda t: tag_any(t, se_terms))
    df["tag_shortage"] = df["body"].map(lambda t: tag_any(t, sh_terms))
    df["tag_cosmetic"] = df["body"].map(lambda t: tag_any(t, co_terms))
    df["tag_telehealth"] = df["body"].map(lambda t: tag_any(t, promo_terms))

    # Which drug each post is actually about, matched on the normalized text so
    # URLs and @handles cannot contribute a match.
    drugs = {name: drug_matcher(terms) for name, terms in load_groups("drugs.yml").items()}
    for name, pattern in drugs.items():
        df[f"drug_{name}"] = df["text_norm"].map(lambda t, p=pattern: bool(p.search(t)))
    df["drugs"] = [
        ";".join(d for d in drugs if row[f"drug_{d}"]) for _, row in df.iterrows()
    ]

    # Narrative threads found by bottom-up exploration, not by prior hypothesis.
    narratives = {k: v["terms"] for k, v in load_narratives().items()}
    for name, terms in narratives.items():
        df[f"narr_{name}"] = df["body"].map(lambda t, terms=terms: tag_any(t, terms))
    df["narratives"] = [
        ";".join(n for n in narratives if row[f"narr_{n}"]) for _, row in df.iterrows()
    ]
    df["promo_score"] = df["body"].map(lambda t: promo_score(t, promo["strong"], promo["weak"]))
    df["register"] = df["body"].map(
        lambda t: classify_register(t, register_cues["news"], register_cues["first_person"])
    )
    df["sentiment_vader"] = vader_scores(df["body"].tolist())

    # Rolling 4h coordination on exact normalized hash.
    df = df.sort_values("created_at").reset_index(drop=True)
    times = df["created_at"].tolist()
    hashes = df["text_hash"].tolist()
    authors = df["author_id"].tolist()
    window = pd.Timedelta(hours=4)
    coord = []
    buckets: dict[str, list[tuple[pd.Timestamp, str]]] = defaultdict(list)
    left = 0
    for i, ts in enumerate(times):
        cutoff = ts - window
        while left < i and times[left] < cutoff:
            h = hashes[left]
            buckets[h].pop(0)
            if not buckets[h]:
                del buckets[h]
            left += 1
        h = hashes[i]
        prior = buckets[h]
        uniq = {a for _, a in prior}
        uniq.add(authors[i])
        n = len(prior) + 1
        n_auth = len(uniq)
        if n <= 1 or n_auth <= 1:
            score = 0.0
        else:
            score = min(1.0, (n_auth - 1) / 8.0 * min(1.0, n / 5.0))
        coord.append(score)
        buckets[h].append((ts, authors[i]))
    df["coord_score"] = coord

    cluster = df.groupby("text_hash").agg(
        cluster_size=("id", "size"),
        cluster_authors=("author_id", "nunique"),
    )
    df = df.merge(cluster, on="text_hash", how="left")

    df = _add_diffusion(df)

    # coord_score only counts duplicate text by distinct authors, which is also
    # exactly what ordinary virality looks like. Two things must override it
    # before it can be read as astroturf:
    #   - news register: many outlets running one headline is wire syndication
    #   - organic diffusion: many distinct accounts spread over hours, low burst
    # Without the second gate the day's most-retweeted joke scores 1.0 astroturf
    # while the diffusion classifier calls it organic - a visible contradiction.
    is_news = df["register"].eq("news")
    is_organic = df["diffusion"].eq("organic")
    df["syndication_score"] = df["coord_score"].where(is_news, 0.0)
    df["astroturf_score"] = df["coord_score"].where(~is_news & ~is_organic, 0.0)

    # A shared affiliate code links accounts that rewrite the text for each vendor,
    # which defeats text-hash clustering. Multiple authors on one code is the signal.
    df["affiliate_code"] = df["body"].map(affiliate_code)
    coded = df[df["affiliate_code"].notna()]
    code_authors = coded.groupby("affiliate_code")["author_id"].nunique()
    df["affiliate_ring"] = (
        df["affiliate_code"].map(code_authors).fillna(0).clip(upper=8) / 8.0
    )
    # A shared code survives both gates: it is evidence regardless of how the
    # text spread, because the accounts are provably linked.
    df["astroturf_score"] = df[["astroturf_score", "affiliate_ring"]].max(axis=1)

    hour_n = df.groupby("hour").size().rename("hour_n")
    df = df.merge(hour_n, on="hour", how="left")
    df["low_n"] = df["hour_n"] < LOW_N

    df["engagement_oddity"] = df.apply(engagement_oddity, axis=1)
    df["cap_score"] = (
        0.5 * df["astroturf_score"] + 0.3 * df["promo_score"] + 0.2 * df["engagement_oddity"]
    ).clip(0, 1)

    if HOURLY_PATH.exists():
        hourly = pq.read_table(HOURLY_PATH).to_pandas()
        hourly["hour"] = pd.to_datetime(hourly["hour"], utc=True)
        topic_n = df.groupby("hour").size().rename("topic_n")
        share = hourly.merge(topic_n, on="hour", how="left")
        share["topic_n"] = share["topic_n"].fillna(0).astype(int)
        share["topic_share"] = share["topic_n"] / share["en_count"].clip(lower=1)
        df = df.merge(share[["hour", "en_count", "topic_share"]], on="hour", how="left")

    df = _join_llm_labels(df)

    ENRICHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa_from_df(df), ENRICHED_PATH)
    _print_report(df)
    print(f"wrote {ENRICHED_PATH} rows={len(df):,}")
    return df


def _add_diffusion(df: pd.DataFrame) -> pd.DataFrame:
    """Per-claim spread shape: organic virality vs coordinated amplification.

    A claim is one normalized text, counting retweets, since amplification is
    the thing being measured. Many distinct accounts spread smoothly over hours
    is organic. Few accounts, repeat posters, or one tight burst is coordinated.
    """
    stats = df.groupby("text_hash").agg(
        claim_copies=("id", "size"),
        claim_authors=("author_id", "nunique"),
        claim_start=("created_at", "min"),
        claim_end=("created_at", "max"),
    )
    stats["claim_span_min"] = (
        stats["claim_end"] - stats["claim_start"]
    ).dt.total_seconds() / 60.0

    # Share of a claim's copies landing in its single busiest hour.
    peak = (
        df.groupby(["text_hash", "hour"]).size().groupby(level=0).max().rename("claim_peak_hour_n")
    )
    stats = stats.join(peak)
    stats["claim_burstiness"] = stats["claim_peak_hour_n"] / stats["claim_copies"]
    stats["claim_author_ratio"] = stats["claim_authors"] / stats["claim_copies"]

    df = df.merge(stats.drop(columns=["claim_start", "claim_end"]), on="text_hash", how="left")

    spreading = df["claim_copies"] >= 5
    # Organic: nearly every copy from a different account, spread across hours.
    organic = (df["claim_author_ratio"] >= 0.9) & (df["claim_burstiness"] <= 0.5)
    # Coordinated: same accounts repeating, or the whole claim fired in one hour.
    coordinated = (df["claim_author_ratio"] < 0.7) | (df["claim_burstiness"] > 0.8)

    df["diffusion"] = "isolated"
    df.loc[spreading & organic, "diffusion"] = "organic"
    df.loc[spreading & coordinated, "diffusion"] = "coordinated"
    df.loc[spreading & ~organic & ~coordinated, "diffusion"] = "mixed"
    return df


LLM_COLS = (
    "llm_primary_topic",
    "llm_topics",
    "llm_intent",
    "llm_stance",
    "llm_sarcastic",
    "llm_tone",
    "llm_speaker",
    "llm_risks",
    "llm_confidence",
)

STANCE_VALUE = {
    "strongly_positive": 1.0,
    "positive": 0.5,
    "mixed": 0.0,
    "neutral": 0.0,
    "negative": -0.5,
    "strongly_negative": -1.0,
}


def _join_llm_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Attach cached Gemini labels. Missing cache is fine — columns stay null."""
    cache: dict = {}
    if LABEL_CACHE_PATH.exists():
        raw = json.loads(LABEL_CACHE_PATH.read_text())
        # Keys are "text_hash:prompt_version"; keep the newest entry per hash.
        for key, body in raw.items():
            h = str(key).split(":", 1)[0]
            cache[h] = body
    for col in LLM_COLS:
        df[col] = None
    df["llm_sarcastic"] = False
    if cache:
        topics, risks = [], []
        for h in df["text_hash"]:
            lab = cache.get(str(h)) or {}
            topics.append(";".join(lab.get("topics") or []))
            risks.append(";".join(lab.get("risks") or []))
        df["llm_primary_topic"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("primary_topic"))
        df["llm_topics"] = topics
        df["llm_intent"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("intent"))
        df["llm_stance"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("stance"))
        df["llm_sarcastic"] = df["text_hash"].map(
            lambda h: bool((cache.get(str(h)) or {}).get("sarcastic"))
        )
        df["llm_tone"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("tone"))
        df["llm_speaker"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("speaker"))
        df["llm_risks"] = risks
        df["llm_confidence"] = df["text_hash"].map(lambda h: (cache.get(str(h)) or {}).get("confidence"))
    df["sentiment_stance"] = df["llm_stance"].map(
        lambda s: STANCE_VALUE[s] if s in STANCE_VALUE else float("nan")
    )
    return df


def pa_from_df(df: pd.DataFrame):
    import pyarrow as pa

    out = df.copy()
    drop = [c for c in ("text_norm",) if c in out.columns]
    return pa.Table.from_pandas(out.drop(columns=drop), preserve_index=False)


def _print_report(df: pd.DataFrame) -> None:
    orig = df.loc[~df["is_retweet"]]
    print("\n=== slice ===")
    print(f"rows={len(df):,} originals={len(orig):,} retweets={int(df['is_retweet'].sum()):,}")
    print(f"match_source:\n{df['match_source'].value_counts().to_string()}")
    print(
        "tags originals: "
        f"side_effect={int(orig['tag_side_effect'].sum())} "
        f"shortage={int(orig['tag_shortage'].sum())} "
        f"cosmetic={int(orig['tag_cosmetic'].sum())} "
        f"telehealth={int(orig['tag_telehealth'].sum())}"
    )
    print(
        f"mean vader originals={orig['sentiment_vader'].mean():.3f} "
        f"promo={orig['promo_score'].mean():.3f} coord={orig['coord_score'].mean():.3f}"
    )
    print(f"register originals:\n{orig['register'].value_counts().to_string()}")

    clusters = (
        orig.groupby("text_hash")
        .agg(
            n=("id", "size"),
            authors=("author_id", "nunique"),
            promo=("promo_score", "mean"),
            coord=("coord_score", "max"),
            register=("register", "first"),
            example=("body", "first"),
        )
        .sort_values(["authors", "n"], ascending=False)
    )
    print("\n=== top original clusters (by unique authors) ===")
    shown = 0
    for _, row in clusters.iterrows():
        if row["n"] < 2 and row["authors"] < 2:
            continue
        text = WS_RE.sub(" ", str(row["example"]))[:160]
        kind = "syndication" if row["register"] == "news" else "astroturf?"
        print(
            f"n={int(row['n'])} authors={int(row['authors'])} "
            f"promo={row['promo']:.2f} coord={row['coord']:.2f} [{kind}] | {text}"
        )
        shown += 1
        if shown >= 10:
            break
    if shown == 0:
        print("null: no multi-author exact-hash clusters on this day")

    print("\n=== example originals ===")
    sample = orig.sort_values("cap_score", ascending=False).head(10)
    for _, row in sample.iterrows():
        text = WS_RE.sub(" ", str(row["body"]))[:160]
        print(
            f"cap={row['cap_score']:.2f} se={int(row['tag_side_effect'])} "
            f"promo={row['promo_score']:.2f} | {text}"
        )

    print("\n=== hourly originals (topic) ===")
    hourly = (
        orig.groupby("hour")
        .agg(
            n=("id", "size"),
            vader=("sentiment_vader", "mean"),
            se=("tag_side_effect", "mean"),
            promo=("promo_score", "mean"),
        )
        .reset_index()
    )
    hourly["low_n"] = hourly["n"] < LOW_N
    print(hourly.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich GLP-1 slice with local NLP features.")
    parser.add_argument("--skip-llm", action="store_true", default=True, help="local only (default)")
    args = parser.parse_args()
    _ = args
    enrich()


if __name__ == "__main__":
    main()
