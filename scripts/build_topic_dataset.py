"""Turn the raw topic extract into ONE clean dataset, plus a corrected per-day table.

Input:  capclipper_data/topics/<name>/<name>_tweets.parquet   every matching row, all columns
        capclipper_data/topics/<name>/day_totals.csv          all rows and tweets per day

Output: <name>_dataset.csv / .parquet    one row per tweet, ONLY tweets whose TEXT names a drug
        <name>_excluded.csv              matches that were only in a link or a username
        <name>_by_day.csv                per day: all tweets, topic tweets, topic per million

A drug name inside a link (https://t.co/dNVNWGlP1i) or a username (@OzempicPigMan) does not
mean the tweet is about the drug, so those rows are moved to the excluded file.

Usage:  python scripts/build_topic_dataset.py ozempic
"""
import sys

import pandas as pd

from download_file import DATA_DIR
from drug_terms import DRUGS, links_only, text_only, usernames_only


def one_row_per_tweet(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest snapshot of each tweet, and record how many snapshots there were."""
    counts = raw.groupby("id").agg(snapshots=("version", "size"), first_seen=("version", "min"))
    latest = raw.sort_values("version").drop_duplicates("id", keep="last").set_index("id")
    return latest.join(counts).reset_index()


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Where each drug name appears: in the text, in a username, or inside a link."""
    text, names, links = text_only(df["body"]), usernames_only(df["body"]), links_only(df["body"])
    in_text, in_name, in_link = [], [], []
    for drug, pattern in DRUGS.items():
        df[f"has_{drug}"] = text.str.contains(pattern, regex=True, na=False)
        in_text.append(df[f"has_{drug}"])
        in_name.append(names.str.contains(pattern, regex=True, na=False))
        in_link.append(links.str.contains(pattern, regex=True, na=False))
    df["drug_in_text"] = pd.concat(in_text, axis=1).any(axis=1)
    df["drug_in_username"] = pd.concat(in_name, axis=1).any(axis=1)
    df["drug_in_link"] = pd.concat(in_link, axis=1).any(axis=1)

    df["is_rt"] = df["body"].str.startswith("RT @")
    df["is_reply"] = df["reply_to_status_id"].notna() & ~df["is_rt"]
    df["is_quote"] = df["quoting_id"].notna() & ~df["is_rt"] & ~df["is_reply"]
    df["has_media"] = df["media"].notna()
    return df


def order_columns(df: pd.DataFrame) -> pd.DataFrame:
    first = ["id", "author_id", "created_at", "date", "hour", "lang", "body"]
    flags = ([f"has_{d}" for d in DRUGS] +
             ["drug_in_text", "drug_in_username", "drug_in_link", "is_rt", "is_reply", "is_quote"])
    rest = [c for c in df.columns if c not in first + flags]
    return df[first + flags + rest].sort_values("created_at")


def by_day(dataset: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """Topic tweets per day against all tweets that day. Both counts are distinct tweets."""
    topic = dataset.groupby("date").size().rename("topic_tweets")
    table = totals.join(topic).fillna({"topic_tweets": 0})
    table["topic_tweets"] = table["topic_tweets"].astype(int)
    table["per_million"] = (table["topic_tweets"] / table["all_tweets"] * 1e6).round(1)
    return table


if __name__ == "__main__":
    name = sys.argv[1]
    folder = DATA_DIR / "topics" / name
    raw = pd.read_parquet(folder / f"{name}_tweets.parquet")
    raw["date"] = raw["date"].astype(str)
    print(f"{len(raw):,} rows in, {raw['id'].nunique():,} distinct tweets")

    df = order_columns(add_flags(one_row_per_tweet(raw)))
    dataset, excluded = df[df["drug_in_text"]], df[~df["drug_in_text"]]

    dataset.to_parquet(folder / f"{name}_dataset.parquet", index=False)
    dataset.to_csv(folder / f"{name}_dataset.csv", index=False, encoding="utf-8-sig")
    excluded.to_csv(folder / f"{name}_excluded.csv", index=False, encoding="utf-8-sig")

    totals = pd.read_csv(folder / "day_totals.csv", dtype={"date": str}).set_index("date")
    by_day(dataset, totals).to_csv(folder / f"{name}_by_day.csv")

    print(f"dataset: {len(dataset):,} tweets whose text names a drug, {len(dataset.columns)} columns")
    print(f"excluded: {len(excluded):,} (in a username only: {excluded['drug_in_username'].sum():,}, "
          f"in a link only: {excluded['drug_in_link'].sum():,})")
    print(f"  languages: {dict(dataset['lang'].value_counts().head(5))}")
    print(f"  english: {(dataset['lang'] == 'en').sum():,} | mentions ozempic: {dataset['has_ozempic'].sum():,}")
    print(f"  retweets: {dataset['is_rt'].mean():.0%} | accounts: {dataset['author_id'].nunique():,} | "
          f"days: {dataset['date'].nunique()}")
    print(f"saved to {folder}")
