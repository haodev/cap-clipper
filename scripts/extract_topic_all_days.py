"""Extract every tweet matching a topic from the whole month, one file at a time.

This reads all 396 source files and keeps only the tweets that match.

The source files are kept in capclipper_data/all_files/ (51.9 GB in total) so they can be
searched again for another topic without downloading anything twice. A file already on
disk is not downloaded again.

Because the dataset covers some days more densely than others, the per-day totals are
recorded too, so the topic can be reported per million tweets rather than as raw counts.

Writes into capclipper_data/topics/<name>/:
  <name>_tweets.parquet   every matching row (all languages, retweets included)
  <name>_tweets.csv       the same rows, for reading by hand
  day_totals.csv          per day: all rows and all distinct tweets in the dataset (the
                          denominators; build_topic_dataset.py adds the topic counts)
  progress.csv            one row per file processed (lets the run resume)
  search.json             the search pattern used, so a resume cannot mix two searches

Usage:  python scripts/extract_topic_all_days.py ozempic
        python scripts/extract_topic_all_days.py ozempic "some|other|pattern"
"""
import json
import shutil
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd
import pyarrow.parquet as pq

from download_file import BUCKET_URL, DATA_DIR
from drug_terms import ANY_DRUG

WORKERS = 5  # files handled at the same time; each one downloads, reads and searches

ALL_FILES = range(396)
ALL_FILES_DIR = DATA_DIR / "all_files"   # every downloaded file is kept here
COLUMNS = None  # keep every column the dataset has


def local_file(file_number: int):
    """Path to the file on disk, downloading it first if it is not there yet."""
    path = ALL_FILES_DIR / f"tweets-{file_number:06d}.parquet"
    if not path.exists():
        ALL_FILES_DIR.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")  # download to .part so a broken download is obvious
        with urllib.request.urlopen(f"{BUCKET_URL}/{path.name}") as response, open(part, "wb") as out:
            shutil.copyfileobj(response, out)
        part.replace(path)
    return path


def process_file(file_number: int, pattern: str) -> tuple[int, pd.DataFrame, pd.DataFrame]:
    """(file number, matching rows, per-day totals for this file). Runs in a worker process."""
    df = pq.read_table(local_file(file_number), columns=COLUMNS).to_pandas()
    df["date"] = df["created_at"].dt.date.astype(str)   # text, so a resume cannot mix types
    per_day = df.groupby("date").agg(all_rows=("id", "size"), all_tweets=("id", "nunique")).reset_index()
    hits = df[df["body"].str.contains(pattern, case=False, regex=True, na=False)].copy()
    hits["hour"] = hits["created_at"].dt.hour
    hits["source_file"] = file_number
    return file_number, hits, per_day


def save(out, name, hits_all, days_all, progress) -> None:
    """Write what has been collected so far, so an interruption costs nothing.

    Only the denominators are written here (all rows and all distinct tweets per day).
    The topic counts come from build_topic_dataset.py, which knows which matches are real.
    """
    pd.concat(hits_all, ignore_index=True).to_parquet(out / f"{name}_tweets.parquet", index=False)
    days = pd.concat(days_all)
    days["date"] = days["date"].astype(str)
    days.groupby("date")[["all_rows", "all_tweets"]].sum().to_csv(out / "day_totals.csv")
    pd.concat(progress, ignore_index=True).to_csv(out / "progress.csv", index=False)


if __name__ == "__main__":
    name = sys.argv[1]
    pattern = sys.argv[2] if len(sys.argv) > 2 else ANY_DRUG
    out = DATA_DIR / "topics" / name
    out.mkdir(parents=True, exist_ok=True)
    search_file = out / "search.json"

    done = set()
    if (out / "progress.csv").exists():  # resume after an interruption
        previous = json.loads(search_file.read_text())["pattern"] if search_file.exists() else None
        if previous != pattern:
            sys.exit("The saved results used a different search pattern. Delete progress.csv, "
                     "day_totals.csv and the _tweets files to start a clean run.")
        done = set(pd.read_csv(out / "progress.csv")["file"])
        print(f"resuming: {len(done)} files already processed")
    search_file.write_text(json.dumps({"pattern": pattern}, indent=2))

    hits_all, days_all, progress = [], [], []
    if done:
        hits_all.append(pd.read_parquet(out / f"{name}_tweets.parquet"))
        days_all.append(pd.read_csv(out / "day_totals.csv", dtype={"date": str}))
        progress.append(pd.read_csv(out / "progress.csv"))

    started = time.time()
    todo = [n for n in ALL_FILES if n not in done]
    finished = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(process_file, n, pattern) for n in todo]
        for future in as_completed(futures):
            n, hits, per_day = future.result()
            hits_all.append(hits)
            days_all.append(per_day)
            progress.append(pd.DataFrame([{"file": n, "matches": len(hits)}]))
            finished += 1
            total = sum(len(h) for h in hits_all)
            print(f"{finished:3}/{len(todo)} done (file {n:3})  matched {len(hits):5}  "
                  f"total {total:7,}  elapsed {(time.time() - started) / 60:5.1f} min", flush=True)
            if finished % 20 == 0:
                save(out, name, hits_all, days_all, progress)

    save(out, name, hits_all, days_all, progress)
    tweets = pd.concat(hits_all, ignore_index=True)
    tweets.to_csv(out / f"{name}_tweets.csv", index=False, encoding="utf-8-sig")
    print(f"\ndone: {len(tweets):,} matching rows, {tweets['id'].nunique():,} distinct tweets, "
          f"{tweets['author_id'].nunique():,} accounts, in {(time.time() - started) / 60:.0f} min")
    print(f"saved to {out}")
    print("next: python scripts/build_topic_dataset.py " + name)
