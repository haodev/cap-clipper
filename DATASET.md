# Ozempic and weight-loss drugs: dataset

Every tweet in the HopHacks X firehose whose **text** names a weight-loss drug, for the full
month the sponsor provided.

| | |
| --- | --- |
| Tweets | **23,058** (one row each) |
| Columns | 44 |
| Accounts | 19,768 |
| Dates | 17 Aug to 17 Sep 2026 (32 days, UTC) |
| Languages | 42, led by English 13,285, Portuguese 3,777, Spanish 3,262 |
| Retweets | 56.5% (replies 2.4%, quotes 10.4%, with media 26.1%) |
| File | `data/ozempic_dataset.csv` (12.3 MB) |

Searched from 395,352,258 rows across 396 source files.

## Processing steps

We searched all 396 source files, containing 395,352,258 rows, using case-insensitive drug
terms and spelling variants documented below. This produced 24,894 matching rows. We
deduplicated by tweet ID, keeping the latest matching snapshot by `version`, leaving 23,272
unique tweets. We then tested a temporary copy of each tweet's text with URLs and @usernames
removed. This excluded 214 tweets whose only mention was inside a username, and none whose
only mention was inside a link, producing the final 23,058-tweet dataset. The original tweet
text was preserved unchanged. All languages, retweets, replies, quotes and low- or
zero-engagement posts were retained; no engagement threshold was applied, so 70% of the
dataset has zero likes. Identical wording posted under different tweet IDs remains separate:
after lowercasing, 903 texts appear more than once across 11,675 rows (898 texts and 11,659
rows on an exact match), mostly retweets. Drug and post-type flags were added before
exporting the CSV.

## Files

This repository holds one data file:

| File | What it is |
| --- | --- |
| `data/ozempic_dataset.csv` | **The dataset.** One row per tweet; the drug name appears in the tweet's own text |

Running the scripts produces several more files locally, which are **not** committed because
they are large, intermediate, or rebuildable in seconds:

| Produced locally | What it is |
| --- | --- |
| `ozempic_dataset.parquet` | The same dataset, 3.7 MB, faster for scripts to load |
| `ozempic_by_day.csv` | 32 rows, one per day: all tweets that day, topic tweets, rate per million |
| `ozempic_excluded.csv` | 214 tweets whose only drug mention was inside a username, e.g. `@OzempicPigMan` |
| `ozempic_tweets.parquet` / `.csv` | The raw extract, 24,894 rows, including repeat observations of the same tweet |
| `day_totals.csv` | Rows and distinct tweets per day across the whole firehose (the denominators) |
| `search.json`, `progress.csv` | The search pattern used, and which of the 396 files were processed |
| `capclipper_data/all_files/` | The 51.9 GB source archive |

## Columns

**Identity and time**

| Column | Meaning |
| --- | --- |
| `id` | Tweet id |
| `author_id` | Account id (numeric; no usernames in this dataset) |
| `created_at` | When the tweet was posted (UTC) |
| `date`, `hour` | Date and hour of `created_at`, for grouping |
| `lang` | Language code recorded by the collector |
| `body` | The tweet text |

**Which drug is named** (all computed on the text after links and @usernames are removed)

`has_ozempic`, `has_wegovy`, `has_semaglutide`, `has_mounjaro`, `has_zepbound`,
`has_tirzepatide`, `has_retatrutide`, `has_glp1`, `has_weight_loss_drug`

A tweet can name several. Counts: ozempic 12,473, glp1 5,139, mounjaro 3,948,
semaglutide 783, weight_loss_drug 715, retatrutide 687, tirzepatide 644, wegovy 644,
zepbound 214.

**Where the name appeared**

| Column | Meaning |
| --- | --- |
| `drug_in_text` | True for every row in this dataset: the tweet itself names a drug |
| `drug_in_username` | The name also appears in an @username |
| `drug_in_link` | The name also appears inside a link |

**Type of post**: `is_rt` (starts with `RT @`), `is_reply`, `is_quote`, `has_media`.

**Engagement, at the last time the tweet was observed**: `like_count`, `reply_count`,
`retweet_count`, `quote_count`, `views_count`, `bookmarks_count`.

**Threading**: `reply_to_status_id`, `reply_to_user_id`, `conversation_id`, `quoting_id`.

**Collection details**: `version` (when this observation was recorded), `first_seen` (first
observation), `snapshots` (how many times the tweet was observed; 1,210 tweets were observed
more than once), `source_file`, `added_at`, `media`, and the collector's own fields
`source`, `poll`, `embed`, `synced`, `embedded`.

## What counts as a topic tweet

A tweet is included when its **text** matches one of these, ignoring case:

| Drug | Spellings matched |
| --- | --- |
| Ozempic | ozempic, ozempick, ozempc, ozempik |
| Wegovy | wegovy, wegovi |
| Semaglutide | semaglutide, semaglutida |
| Mounjaro | mounjaro, munjaro |
| Zepbound | zepbound |
| Tirzepatide | tirzepatide, tirzepatida |
| Retatrutide | retatrutide, retatrutida |
| GLP-1 | glp-1, glp1, glp 1, and the forms glp-1s, glp-1r, glp-1ra, including unicode dashes |
| Generic phrase | weight loss drug / jab / shot / injection / med(ication), singular or plural |

Links and @usernames are removed before matching, so a drug name inside `https://t.co/...`
or `@OzempicPigMan` does not qualify. **These terms are frozen**; they live in
`scripts/drug_terms.py` and are used by both scripts, so the two can never disagree.

### The exact search pattern

This is what produced the dataset, applied to the tweet text with case ignored:

```
(?:ozempi[ck]|ozempc|ozempik)|(?:wegov[yi])|(?:semaglutid[ea])|
(?:mounjaro|munjaro)|(?:zepbound)|(?:tirzepatid[ea])|(?:retatrutid[ea])|
(?:\bglp[ _.‐‑‒–—−-]?1(?:ra|rs|r|s)?\b)|
(?:weight[ _.‐‑‒–—−-]?loss (?:drug|jab|shot|injection|med|medication)s?)
```

The character class after `glp` and `weight` holds a space, underscore, dot, the unicode
hyphens `‐ ‑ ‒ – — −`, and a normal hyphen, so "GLP-1", "GLP 1", "GLP1" and pasted
unicode-dash versions all match. The pattern is one line in `scripts/drug_terms.py`; it is
wrapped here only so it fits the page.

## Loading the CSV: keep the ids as text

`id`, `author_id`, `conversation_id`, `reply_to_status_id`, `reply_to_user_id` and
`quoting_id` are 19-digit numbers. If a tool reads them as numbers it will round them, and
ids like `2089140150454645144` become `2089140150454645000` or `2.08914E+18`. That damage
cannot be undone, so always load these six columns as text.

**pandas**

```python
import pandas as pd

ID_COLUMNS = ["id", "author_id", "conversation_id",
              "reply_to_status_id", "reply_to_user_id", "quoting_id"]

df = pd.read_csv("data/ozempic_dataset.csv", dtype={c: "string" for c in ID_COLUMNS},
                 parse_dates=["created_at", "version", "first_seen", "added_at"])
```

**Excel.** Do not double-click the file: Excel will convert the ids to scientific notation.
Open Excel first, then:

1. **Data > Get Data > From File > From Text/CSV**, and choose the file.
2. In the preview window, click **Transform Data**.
3. Select the six id columns (ctrl-click the headers), then **Transform > Data Type > Text**.
   If Excel offers "Replace current conversion" or "Add new step", choose to replace.
4. **Home > Close & Load**.

The file is UTF-8 with a byte order mark, so accents and non-English text display correctly.
Tweet text can contain commas, quotes and line breaks; it is quoted properly, so use a real
CSV reader rather than splitting on commas.

**Google Sheets.** File > Import > Upload, and untick "Convert text to numbers, dates and
formulas". Note the file has 23,058 rows, which Sheets handles, but it is slow to scroll.

## Reproducing it

Requires Python with pandas and pyarrow. No credentials and no AWS CLI: the bucket is public.

```
python scripts/extract_topic_all_days.py ozempic     # search all 396 files
python scripts/build_topic_dataset.py ozempic        # build the dataset and the daily table
```

The first command downloads each source file to `capclipper_data/all_files/` (51.9 GB in
total) and keeps it, so a later search reads from disk instead of the network. It handles
five files at a time, records progress after every 20, and can resume after an interruption.
It refuses to resume if the search pattern has changed, so two different searches can never
be mixed in one output.

Timings on a laptop: about 25 minutes including downloads, about 3 minutes from local files.

**The 51.9 GB source archive is not in this repository.** Only the scripts and the finished
dataset are.

## How it was checked

- **Counted independently:** for 9 randomly chosen source files, tweets were counted directly
  with a plain text search and compared with the extract. All 9 matched exactly.
- **Repeatable:** rerunning the whole pipeline produces an identical dataset and a 32-row
  daily table.
- **All 396 files processed:** recorded in `progress.csv`, none missing.
- **Every row verified** to have `drug_in_text = true`.

## Known limitations

- **Names only.** Tweets that discuss these drugs without naming them ("the skinny jab",
  "she's on something") are not included. How many that is has not been measured.
- **Relevance not hand-checked.** A tweet naming a drug may still be a joke, an insult or an
  aside. No sample has been read and marked yet.
- **No structured geographic metadata is available.** The source data has no country, city,
  coordinates, profile location or user time zone in any column. Tweet text may mention
  places, but those mentions have not been extracted, and a place named in a tweet does not
  establish where its author lives or posted from. Language and posting time do not
  establish location either.
- **The posting app is unknown**: the `source` column is empty in every row, as are `poll`
  and `embed`.
- **Engagement is late and nearly static.** A tweet is usually first observed about a day
  after posting, and repeat observations barely change, so the growth of a single tweet
  cannot be measured. Counts describe reach, not speed.
- **Coverage is uneven.** The collector captured far more in August than in September, so
  raw daily counts are not comparable. Compare rates instead: `build_topic_dataset.py`
  writes `ozempic_by_day.csv` locally with a `per_million` column for exactly this.
- **Retweets are included** (56.5%). They copy another tweet's text, so exclude them with
  `is_rt = false` when analysing what people wrote themselves.
- **No usernames**, only numeric account ids, and no follower counts or profile information.
- **1,309 source rows have no timestamp.** They are counted in the 395,352,258 total but
  cannot appear in any per-day figure, so daily totals sum to 395,350,949.
- **An interrupted extraction can need a clean restart.** `extract_topic_all_days.py` saves
  its progress after every 20 files it finishes. Stopping it normally is safe: it resumes
  from the last checkpoint and simply redoes up to 19 files. But the checkpoint writes three
  files one after another (the extract, the daily totals, the progress list), so a crash or
  a power cut *during* a checkpoint can leave them disagreeing with each other, and a resume
  would then miss or double-count those files. This is known and not guarded against. If the
  run dies unexpectedly, delete the topic output folder and start again; with the archive
  already downloaded, a full rerun takes about 3 minutes.
