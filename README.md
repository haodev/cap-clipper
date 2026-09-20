# cap-clipper

CamelCamelCamel for internet culture. Real-time truthfulness, astroturf detection, and narrative velocity tracking for social feeds.

The demo has two frozen views:

- **Day demo** (`/day/2026-08-17`) — one UTC day of GLP-1 discourse with hour-by-hour
  topic share, sparklines, and hour-focus forensic cards.
- **Multi-day** (`/`) — the labeled 17 Aug–17 Sep 2026 slice in `data/ozempic_labeled.csv`,
  same Cap scores / claims / narratives / cards, without hour-by-hour charts.

Both are served from precomputed JSON. Nothing is analysed at request time.

## Running the demo

Two processes. The backend serves a precomputed JSON payload, so nothing is
analysed at request time.

```bash
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
```

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

The backend reads `demo_payload.json` once at startup, so restart it after any
rebuild of the payload.

## Rebuilding the analysis

Only needed if the raw shards or the lexicons change.

```bash
python scripts/download_file.py --all      # ~23 shards, ~140 MB each
python scripts/extract_glp1.py             # firehose -> curated_glp1.parquet
python scripts/enrich_glp1.py              # scores    -> enriched_glp1.parquet
python scripts/build_payload.py            # freeze    -> demo_payload.json
python scripts/build_range_payload.py      # labeled CSV -> range_payload.json
```

## Where Gemini is used

Both uses run offline, in batch, ahead of the demo. No model call is ever on the
request path, so the UI stays fast and every number on screen is reproducible
without an API key. The key is read from `GEMINI_API_KEY` in the environment or
in `.env`.

```bash
python scripts/gemini_narratives.py --dry-run   # propose threads, write nothing
python scripts/gemini_narratives.py             # validate and merge
python scripts/gemini_explain.py                # a paragraph per forensic card
```

`gemini_narratives.py` is the one that does analytic work. The hand-written
lexicons only recognised 22% of the day's distinct claims, so the script shows
Gemini the claims that matched nothing and asks what recurring threads are in
there. Two rules keep the result trustworthy:

- **Nothing is ever deleted.** The script can add a thread or add terms to an
  existing thread. Curated entries always survive.
- **No proposed term is taken on trust.** Each is tested against the corpus and
  dropped unless at least 3 distinct claims from 3 *independent sources* contain
  it, and it matches under 25% of the corpus. Sources matter because a retweet's
  author is the amplifier, not the speaker: one supplement brand retweeted three
  times looks like three voices until you resolve `RT @handle`.

Replies are cached to `narrative_proposals.json`, and `--from-file` re-validates
them without spending quota.

`extract_glp1.py --expand` also pulls direct replies and quotes of matched
tweets. It is off by default because most of what it drags in never mentions a
GLP-1 drug.

Rebuild the payload and restart the backend after editing any lexicon.

Data artifacts are written outside the repo, next to it in `../capclipper_data/`.

## How a tweet is scored

Each score answers a different question, and they are deliberately not merged
into one number until the last step.

| Score | Question |
| --- | --- |
| `promo_score` | Is this selling something? Density of price and call-to-action language. |
| `coord_score` | Is this exact text being repeated by different accounts in a short window? |
| `syndication_score` | `coord_score` inside the news register — wire copy, not a campaign. |
| `astroturf_score` | `coord_score` that survives the news and organic-diffusion gates. |
| `affiliate_ring` | Is one discount code being used by several accounts and vendor brands? |
| `cap_score` | `0.5·astroturf + 0.3·promo + 0.2·engagement oddity`. |

The load-bearing idea is that **volume is not guilt**. The day's biggest claim
was retweeted 193 times by 193 distinct accounts across 23 hours; naive
duplicate-counting scores that as maximum coordination. The diffusion classifier
labels it organic and zeroes its astroturf score. What survives is the genuinely
suspicious material — a single affiliate code (`PROFPEPTIDE`) appearing under
multiple account names and vendor brands, with rewritten copy each time so that
text clustering alone would miss it.

Scores are lexicon and pattern heuristics over one day. They are not medical or
legal judgements, and hours with too few tweets are flagged low-confidence
rather than smoothed over.

## One row per claim

The feed shows the 406 *distinct claims* in the day, not the 742 posts. The unit
has to be the claim: 203 of the posts belong to just six culture-war claims, so
a per-post feed is mostly the same retweet repeated, while the smaller
narratives are too sparse to survive sampling. Each row is the highest-reach
copy and carries how many copies and accounts it stands for.

Selecting a narrative in the rail, or pressing *show these in the feed* on a
forensic card, drives the same single selection, so the three panels never
disagree about what is being looked at.

## Layout

```
backend/main.py        read-only FastAPI over demo_payload.json
scripts/               download -> extract -> enrich -> build_payload
lexicons/*.yml         editable term lists; every keyword rule lives here
web/                   Next.js dashboard (narrative rail, feed, hover card)
gold/labels_50.csv     human labels for spot-checking the heuristics
```
