# Ozempic and weight-loss drugs: dataset

Every tweet **in the 396 files supplied for HopHacks** whose text names a weight-loss drug.
The supplied files cover 17 Aug to 17 Sep 2026. How they were collected, and what share of
all posts about these drugs they contain, is not known to us, so nothing here should be read
as describing X as a whole.

**How to read this file.** Three kinds of statement are kept apart:
*measured* (counted in a stated population, either the 396 supplied files, the 24,894-row raw
extract or the 23,058-tweet dataset, and repeatable),
*our choice* (a decision we made while building the dataset), and
*not verified* (something we have not checked, or cannot check with these fields).

Measured across the dataset itself, meaning all 23,058 tweets:

| | |
| --- | --- |
| Tweets | **23,058** (one row each) |
| Columns | 44 |
| Accounts | 19,768 |
| Dates | 17 Aug to 17 Sep 2026 (32 days, UTC) |
| Languages | 42, led by English 13,285, Portuguese 3,777, Spanish 3,262 |
| Retweets | 56.5% (replies 2.4%, quotes 10.4%, with media 26.1%) |
| File | `data/ozempic_dataset.csv` (12.3 MB) |

Measured: searched from 395,352,258 rows across the 396 supplied files.

## Processing steps

We searched all 396 source files, containing 395,352,258 rows, using case-insensitive drug
terms and spelling variants documented below. This produced 24,894 matching rows. We
deduplicated by tweet ID, keeping the latest matching snapshot by `version`, leaving 23,272
unique tweets. We then tested a temporary copy of each tweet's text with URLs and @usernames
removed. This excluded 214 tweets whose only mention was inside a username, and none whose
only mention was inside a link, producing the final 23,058-tweet dataset. The original tweet
text was preserved unchanged. All languages, retweets, replies, quotes and low- or
zero-engagement posts were retained; no engagement threshold was applied, so 70.0% of the
23,058 dataset tweets have zero likes, with no missing values. Identical wording posted under
different tweet IDs remains separate: within the dataset, after lowercasing, 903 texts appear
more than once, covering 11,675 of the 23,058 rows (898 texts and 11,659 rows on an exact
match); 99.0% of those 11,675 rows are retweets. Drug and post-type flags were added before
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
| `day_totals.csv` | Rows and distinct tweets per day across all supplied files (the denominators) |
| `search.json`, `progress.csv` | The search pattern used, and which of the 396 files were processed |
| `capclipper_data/all_files/` | The 51.9 GB source archive |

## Columns

**Identity and time**

| Column | Meaning |
| --- | --- |
| `id` | Tweet id |
| `author_id` | Account id (numeric; no usernames in this dataset) |
| `created_at` | Posting time as supplied (UTC). We did not verify it against X |
| `date`, `hour` | Date and hour of `created_at`, added by us for grouping |
| `lang` | Language code as supplied. How it was determined is not documented, and we did not check its accuracy |
| `body` | The tweet text, exactly as supplied |

**Which drug is named** (all computed on the text after links and @usernames are removed)

`has_ozempic`, `has_wegovy`, `has_semaglutide`, `has_mounjaro`, `has_zepbound`,
`has_tirzepatide`, `has_retatrutide`, `has_glp1`, `has_weight_loss_drug`

A tweet can name several, so these counts overlap and do not sum to the dataset size.
Measured across the 23,058 dataset tweets: ozempic 12,473, glp1 5,139, mounjaro 3,948,
semaglutide 783, weight_loss_drug 715, retatrutide 687, tirzepatide 644, wegovy 644,
zepbound 214.

**Where the name appeared**

| Column | Meaning |
| --- | --- |
| `drug_in_text` | True for every row in this dataset: the tweet itself names a drug |
| `drug_in_username` | The name also appears in an @username |
| `drug_in_link` | The name also appears inside a link |

**Type of post** (added by us): `is_rt`, `is_reply`, `is_quote`, `has_media`.

`is_rt` is a rule, not a supplied field: the text begins with `RT @`. That is the usual form
of a re-share, but we did not confirm it against X, and a tweet quoting that prefix in its own
words would be counted as a retweet. `is_reply` and `is_quote` come from
`reply_to_status_id` and `quoting_id` being present.

**Engagement counts as supplied, at the latest observation we have**: `like_count`,
`reply_count`, `retweet_count`, `quote_count`, `views_count`, `bookmarks_count`. How these
were obtained, and how current they were, is not documented.

**Threading, as supplied**: `reply_to_status_id`, `reply_to_user_id`, `conversation_id`,
`quoting_id`.

**Observation fields**: `version` (the timestamp supplied with that observation),
`first_seen` (the earliest `version` we hold for the tweet), `snapshots` (how many
observations of it appear in our extract; measured: 1,210 tweets have more than one, and
21,848 have exactly one), `source_file` (added by us), plus `added_at`, `media`, `source`,
`poll`, `embed`, `synced` and `embedded` exactly as supplied. We do not know what `synced`
and `embedded` mean.

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

Timings measured on the machine used to build this dataset (a Windows laptop, five files
processed at a time): about 25 minutes including downloads, about 3 minutes from local files.
Your hardware and connection will differ.

**The 51.9 GB source archive is not in this repository.** Only the scripts and the finished
dataset are.

## How it was checked

- **Counted independently:** in 9 randomly chosen supplied files, matching tweets were
  counted directly with a plain text search and compared with our extract. All 9 matched
  exactly. This checks that the extraction loses nothing; it says nothing about whether the
  search terms are the right ones.
- **Repeatable:** rerunning the whole pipeline produces an identical dataset and a 32-row
  daily table.
- **All 396 supplied files processed:** recorded in `progress.csv`, none missing.
- **Every row verified** to have `drug_in_text = true`.
- **Not checked:** whether the matched tweets are genuinely about the drugs, how many
  relevant tweets the terms miss, and whether any supplied field is accurate.

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
- **The `source`, `poll` and `embed` columns are empty** in every row of this dataset. All
  396 supplied files share one identical column set, so no posting-app information is
  available to us. Why those fields are empty is not known.
- **Engagement counts cannot show growth.** Measured across all 23,058 dataset tweets, every
  one of which has both timestamps: the gap between `created_at` and the first observation
  has a median of 23.8 hours (25th percentile 9.1, 75th 45.8), and 17.9% are first observed
  within 6 hours. 21,848 of the 23,058 (94.8%) appear only once in our extract. Among the
  1,210 that appear two or more times, the view count is unchanged for 42.4%, and the median
  gain is 2 views (90th percentile 1,696). So these counts can be compared between tweets,
  but they do not describe how fast a tweet grew. We do not know why observations are spaced
  this way.
- **The supplied files are not evenly spread over the month.** Measured across the 23,058
  dataset tweets: 21,254 are dated in August and 1,804 in September, and the daily
  totals fall sharply after 31 August. Raw daily counts are therefore not comparable across
  the month; compare rates instead (`build_topic_dataset.py` writes `ozempic_by_day.csv`
  locally with a `per_million` column). **Not verified:** whether this reflects collection,
  storage or anything about real posting activity. It should not be read as interest
  declining.
- **Retweets are included**: 56.5% of the 23,058 dataset tweets, by the `RT @` rule above.
  Measured within the dataset: 11,675 of those 23,058 rows (50.6%) have lowercased text that
  also appears under another tweet id, and 99.0% of those 11,675 are retweets. So repeated
  wording in this dataset mostly reflects re-sharing, not separate accounts independently
  writing the same thing. Exclude retweets with `is_rt = false` when studying what people
  wrote themselves.
- **Not a representative sample.** We cannot say what fraction of all posts about these
  drugs the supplied files contain, and the accounts here are not a sample of any
  population. Counts describe this dataset only.
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
