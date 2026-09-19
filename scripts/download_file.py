"""Download one Parquet file of the Calcifer X firehose (public S3 bucket, no login).

Usage:  python scripts/download_file.py 0      -> tweets-000000.parquet
        python scripts/download_file.py 22     -> tweets-000022.parquet (last first-day file)
"""
import shutil
import sys
import urllib.request
from pathlib import Path

BUCKET_URL = "https://calcifer-hot.s3.amazonaws.com/hopkins-hackathon-2026/twitter-firehose-last-month"

# Data lives next to the repo, not inside it, so it can never be committed.
DATA_DIR = Path(__file__).resolve().parents[2] / "capclipper_data"

# The project uses only the first day of the dataset: Mon 17 Aug 2026 (UTC) = files 0-22.
# (File 22 runs past midnight to 00:55 Tue; analyze_day.py trims it to the day.)
FIRST_DAY = "2026-08-17"
FIRST_DAY_FILES = range(0, 23)
FIRST_DAY_DIR = DATA_DIR / f"first_day_{FIRST_DAY}"


def parquet_path(file_number: int) -> Path:
    """Where a first-day file lives. Refuses files from any other day."""
    if file_number not in FIRST_DAY_FILES:
        raise ValueError(f"file {file_number} is not part of the first day (files 0-22 only)")
    return FIRST_DAY_DIR / f"tweets-{file_number:06d}.parquet"


def download(file_number: int) -> Path:
    target = parquet_path(file_number)
    name = target.name
    if target.exists():
        print(f"already have {target}")
        return target
    FIRST_DAY_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {name} (~140 MB) ...")
    with urllib.request.urlopen(f"{BUCKET_URL}/{name}") as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out)
    print(f"saved {target} ({target.stat().st_size / 1e6:.0f} MB)")
    return target


if __name__ == "__main__":
    download(int(sys.argv[1]))
