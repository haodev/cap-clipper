"""Attach the Grok labels back onto every row of the dataset.

Labels are produced once per distinct text; this fans them back out to all 23,058 rows,
so a meme labeled once carries its labels on all 1,773 copies.

Output: data/ozempic_labeled.csv -- the original 44 columns plus the label columns.
Multi-value fields arrive two ways: a pipe-joined string for reading, and one boolean
column per topic and per risk flag for filtering and pivoting.

    python scripts/join_labels.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

from label_schema import FIELDS, RISKS, TOPICS
from label_with_grok import OUT, SOURCE, norm_key

ID_COLUMNS = ["id", "author_id", "conversation_id", "reply_to_status_id",
              "reply_to_user_id", "quoting_id"]


def main():
    labels_path = OUT / "labels.jsonl"
    if not labels_path.exists():
        sys.exit("No labels yet. Run: python scripts/label_with_grok.py")

    rows, seen = [], set()
    with labels_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            label = json.loads(line)
            if label["id"] in seen:      # a resumed run can re-label a text; last wins
                rows = [r for r in rows if r["id"] != label["id"]]
            seen.add(label["id"])
            rows.append(label)
    labels = pd.DataFrame(rows).rename(columns={"id": "uid"})
    flagged = labels["_problems"].map(bool).sum() if "_problems" in labels else 0
    print(f"{len(labels):,} labeled texts ({flagged:,} with schema problems)")

    uniq = pd.read_csv(OUT / "unique_texts.csv")[["uid", "key", "dup"]]
    labels = uniq.merge(labels, on="uid", how="inner")

    df = pd.read_csv(SOURCE, dtype={c: "string" for c in ID_COLUMNS}, low_memory=False)
    df["key"] = norm_key(df["body"])
    before = len(df)
    df = df.merge(labels.drop(columns=["dup"]), on="key", how="left")
    assert len(df) == before, "join changed the row count"

    covered = df["uid"].notna()
    print(f"rows labeled: {covered.sum():,} of {before:,} ({covered.mean() * 100:.1f}%)")

    for field, (kind, _) in FIELDS.items():
        if kind in ("many", "free"):
            df[field] = df[field].map(lambda v: "|".join(v) if isinstance(v, list) else "")
    for topic in TOPICS:
        df[f"topic_{topic}"] = df["topics"].str.split("|").map(
            lambda v, t=topic: t in v if isinstance(v, list) else False)
    for risk in RISKS:
        df[f"risk_{risk}"] = df["risks"].str.split("|").map(
            lambda v, r=risk: r in v if isinstance(v, list) else False)
    df["label_problems"] = df.pop("_problems").map(
        lambda v: "|".join(v) if isinstance(v, list) and v else "")

    out = SOURCE.parent / "ozempic_labeled.csv"
    df.drop(columns=["key", "uid"]).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"wrote {out}  ({out.stat().st_size / 1e6:.1f} MB, {len(df.columns) - 2} columns)")

    done = df[covered]
    if not done.empty:
        print("\ntop topics (by row, duplicates included):")
        counts = pd.Series({t: done[f"topic_{t}"].sum() for t in TOPICS})
        for topic, n in counts[counts > 0].sort_values(ascending=False).head(12).items():
            print(f"  {topic:26} {n:6,}  ({n / len(done) * 100:4.1f}%)")
        print("\nrisk flags:")
        for risk in RISKS:
            n = done[f"risk_{risk}"].sum()
            if n:
                print(f"  {risk:26} {n:6,}")
        print(f"\nintent: {dict(done['intent'].value_counts().head(5))}")
        print(f"stance: {dict(done['stance'].value_counts())}")


if __name__ == "__main__":
    sys.exit(main())
