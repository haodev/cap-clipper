"""Build the English GLP-1 slice and hourly English firehose counts.

Usage: python scripts/extract_glp1.py
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from cc_paths import CURATED_PATH, DAY_END, DAY_START, FIRST_DAY_DIR, HOURLY_PATH, load_terms

MAX_EXPAND_PER_CONVO = 40
COLUMNS = [
    "id",
    "author_id",
    "body",
    "created_at",
    "like_count",
    "reply_count",
    "retweet_count",
    "quote_count",
    "views_count",
    "lang",
    "conversation_id",
    "quoting_id",
    "reply_to_status_id",
]


def _shard_paths():
    files = sorted(FIRST_DAY_DIR.glob("tweets-*.parquet"))
    if len(files) != 23:
        raise FileNotFoundError(f"expected 23 shards in {FIRST_DAY_DIR}, found {len(files)}")
    return files


def _on_day(table: pa.Table) -> pa.Array:
    start = pa.scalar(DAY_START).cast(table["created_at"].type)
    end = pa.scalar(DAY_END).cast(table["created_at"].type)
    return pc.and_(pc.greater_equal(table["created_at"], start), pc.less(table["created_at"], end))


def _is_en(table: pa.Table) -> pa.Array:
    return pc.equal(table["lang"], "en")


def _keyword_mask(body_lower: pa.Array, terms: list[str]) -> pa.Array:
    mask = pc.match_substring(body_lower, terms[0])
    for term in terms[1:]:
        mask = pc.or_(mask, pc.match_substring(body_lower, term))
    return mask


def _is_rt(body: pa.Array) -> pa.Array:
    return pc.starts_with(body, "RT @")


def extract(expand: bool) -> None:
    terms = load_terms("glp1.yml")
    files = _shard_paths()
    hourly = defaultdict(int)
    keyword_tables: list[pa.Table] = []
    seed_convos: set[str] = set()
    seed_ids: set[str] = set()
    quoted_ids: set[str] = set()

    print(f"pass 1: keyword + hourly en  ({len(terms)} terms)")
    for path in files:
        table = pq.read_table(path, columns=COLUMNS)
        day = _on_day(table)
        en = _is_en(table)
        keep_en_day = pc.and_(day, en)
        en_day = table.filter(keep_en_day)
        if en_day.num_rows:
            hours = pc.floor_temporal(en_day["created_at"], unit="hour")
            vc = pc.value_counts(hours)
            for ts, n in zip(vc.field(0).to_pylist(), vc.field(1).to_pylist()):
                hourly[ts] += int(n)

        lower = pc.utf8_lower(table["body"])
        hits = table.filter(pc.and_(keep_en_day, _keyword_mask(lower, terms)))
        if hits.num_rows:
            hits = hits.append_column("is_retweet", _is_rt(hits["body"]))
            hits = hits.append_column("match_source", pa.array(["keyword"] * hits.num_rows))
            keyword_tables.append(hits)
            seed_ids.update(x for x in hits["id"].to_pylist() if x)
            seed_convos.update(x for x in hits["conversation_id"].to_pylist() if x)
            quoted_ids.update(x for x in hits["quoting_id"].to_pylist() if x)
        print(f"  {path.name}: keyword={hits.num_rows:,} en_day={en_day.num_rows:,}")

    if not keyword_tables:
        raise SystemExit("no English GLP-1 keyword hits on 2026-08-17")

    curated = pa.concat_tables(keyword_tables, promote_options="default")
    n_keyword = curated.num_rows
    print(f"keyword hits: {n_keyword:,} unique convos={len(seed_convos):,}")

    if expand and (seed_ids or quoted_ids):
        print("pass 2: conversation / quote expand")
        extra_tables: list[pa.Table] = []
        convo_arr = pa.array(list(seed_convos)) if seed_convos else None
        seed_id_arr = pa.array(list(seed_ids))
        quoted_arr = pa.array(list(quoted_ids)) if quoted_ids else None
        for path in files:
            table = pq.read_table(path, columns=COLUMNS)
            keep = pc.and_(_on_day(table), _is_en(table))
            table = table.filter(keep)
            if table.num_rows == 0:
                continue
            # Direct relationships only. Matching on conversation_id alone drags in
            # whole unrelated threads: 82 of 89 such rows never mentioned GLP-1.
            mask = pc.is_in(table["reply_to_status_id"], value_set=seed_id_arr)
            mask = pc.or_(mask, pc.is_in(table["quoting_id"], value_set=seed_id_arr))
            if quoted_arr is not None:
                mask = pc.or_(mask, pc.is_in(table["id"], value_set=quoted_arr))
            part = table.filter(mask)
            if part.num_rows:
                extra_tables.append(part)
            print(f"  {path.name}: expand_candidates={part.num_rows:,}")

        if extra_tables:
            expanded = pa.concat_tables(extra_tables, promote_options="default")
            already = set(curated["id"].to_pylist())
            is_new = pa.array([i not in already for i in expanded["id"].to_pylist()])
            expanded = expanded.filter(is_new)
            expanded = _cap_conversations(expanded, seed_convos)
            if expanded.num_rows:
                expanded = expanded.append_column("is_retweet", _is_rt(expanded["body"]))
                expanded = expanded.append_column(
                    "match_source", pa.array(["expand"] * expanded.num_rows)
                )
                curated = pa.concat_tables([curated, expanded], promote_options="default")
            print(f"expanded added: {expanded.num_rows:,}")

    # de-dupe ids
    seen: set[str] = set()
    keep = []
    for i in curated["id"].to_pylist():
        if i in seen:
            keep.append(False)
        else:
            seen.add(i)
            keep.append(True)
    curated = curated.filter(pa.array(keep))

    CURATED_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(curated, CURATED_PATH)

    hours_sorted = sorted(hourly.items(), key=lambda x: x[0])
    hourly_table = pa.table(
        {
            "hour": pa.array([k for k, _ in hours_sorted], type=pa.timestamp("ms", tz="UTC")),
            "en_count": pa.array([v for _, v in hours_sorted], type=pa.int64()),
        }
    )
    pq.write_table(hourly_table, HOURLY_PATH)

    n_rt = int(pc.sum(curated["is_retweet"].cast(pa.int64())).as_py() or 0)
    print(
        f"wrote {CURATED_PATH} rows={curated.num_rows:,} "
        f"keyword={n_keyword:,} expand={curated.num_rows - n_keyword:,} "
        f"retweets={n_rt:,} originals={curated.num_rows - n_rt:,}"
    )
    print(f"wrote {HOURLY_PATH} hours={hourly_table.num_rows}")


def _cap_conversations(table: pa.Table, seed_convos: set[str]) -> pa.Table:
    if table.num_rows == 0:
        return table
    by_convo: dict[str, list[int]] = defaultdict(list)
    other: list[int] = []
    convos = table["conversation_id"].to_pylist()
    for i, cid in enumerate(convos):
        if cid in seed_convos:
            by_convo[cid].append(i)
        else:
            other.append(i)
    keep_idx = list(other)
    for cid, idxs in by_convo.items():
        keep_idx.extend(idxs[:MAX_EXPAND_PER_CONVO])
    keep_idx.sort()
    return table.take(pa.array(keep_idx, type=pa.int32()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract English GLP-1 slice from first-day shards.")
    # Expand is off by default: on 2026-08-17 it added 75 rows of which only 4
    # were on topic. Replies to a matched tweet are usually generic chatter.
    parser.add_argument(
        "--expand", action="store_true", help="also pull direct replies/quotes of matched tweets"
    )
    args = parser.parse_args()
    extract(expand=args.expand)


if __name__ == "__main__":
    main()
