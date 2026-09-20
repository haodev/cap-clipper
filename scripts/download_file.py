"""Download Parquet files of the Calcifer X firehose (public S3 bucket, no login).

Usage:  python scripts/download_file.py 0      -> tweets-000000.parquet
        python scripts/download_file.py 22     -> tweets-000022.parquet (last first-day file)
        python scripts/download_file.py --all  -> files 0-22
"""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

BUCKET_URL = "https://calcifer-hot.s3.amazonaws.com/hopkins-hackathon-2026/twitter-firehose-last-month"

# Data lives next to the repo, not inside it, so it can never be committed.
DATA_DIR = Path(__file__).resolve().parents[2] / "capclipper_data"

# The project uses only the first day of the dataset: Mon 17 Aug 2026 (UTC) = files 0-22.
# (File 22 runs past midnight to 00:55 Tue; later analysis should trim it to the day.)
FIRST_DAY = "2026-08-17"
FIRST_DAY_FILES = range(0, 23)
FIRST_DAY_DIR = DATA_DIR / f"first_day_{FIRST_DAY}"

# Complete objects are ~140 MB. Anything this small is a truncated/failed write.
MIN_BYTES = 1_000_000
MAX_RETRIES = 5
RETRY_BASE_SECONDS = 2


def parquet_path(file_number: int) -> Path:
    """Where a first-day file lives. Refuses files from any other day."""
    if file_number not in FIRST_DAY_FILES:
        raise ValueError(f"file {file_number} is not part of the first day (files 0-22 only)")
    return FIRST_DAY_DIR / f"tweets-{file_number:06d}.parquet"


def _is_complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size >= MIN_BYTES


def _remove_incomplete(path: Path) -> None:
    if path.exists():
        print(f"removing incomplete {path.name} ({path.stat().st_size} bytes)")
        path.unlink()


def download(file_number: int) -> Path:
    target = parquet_path(file_number)
    name = target.name
    if _is_complete(target):
        print(f"already have {target} ({target.stat().st_size / 1e6:.0f} MB)")
        return target

    _remove_incomplete(target)
    FIRST_DAY_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{BUCKET_URL}/{name}"
    tmp = target.with_suffix(target.suffix + ".part")

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"downloading {name} (~140 MB) [attempt {attempt}/{MAX_RETRIES}] ...")
            if tmp.exists():
                tmp.unlink()
            # curl uses the macOS cert store; python.org 3.14 urllib does not
            # until Install Certificates.command has been run.
            result = subprocess.run(
                ["curl", "-fL", "--retry", "2", "--retry-delay", "2", "-o", str(tmp), url],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"curl exit {result.returncode}")
            if tmp.stat().st_size < MIN_BYTES:
                raise RuntimeError(f"{name} is only {tmp.stat().st_size} bytes")
            tmp.replace(target)
            print(f"saved {target} ({target.stat().st_size / 1e6:.0f} MB)")
            return target
        except (OSError, RuntimeError) as exc:
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            if attempt == MAX_RETRIES:
                break
            wait = RETRY_BASE_SECONDS ** attempt
            print(f"failed ({exc}); retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"could not download {name} after {MAX_RETRIES} attempts") from last_error


def download_all() -> list[Path]:
    paths = [download(n) for n in FIRST_DAY_FILES]
    _print_summary(paths)
    return paths


def _print_summary(paths: list[Path]) -> None:
    total = sum(p.stat().st_size for p in paths)
    print(
        f"summary: {len(paths)} files, {total / 1e9:.2f} GB, dest {FIRST_DAY_DIR}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download first-day Calcifer firehose Parquet files.")
    parser.add_argument(
        "file_number",
        nargs="?",
        type=int,
        help="single file in 0-22 (tweets-00000N.parquet)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="download files 0-22 (skip complete files)",
    )
    args = parser.parse_args()

    if args.all == (args.file_number is not None):
        parser.error("pass a file number or --all, not both")

    if args.all:
        download_all()
        return

    path = download(args.file_number)
    _print_summary([path])


if __name__ == "__main__":
    main()
