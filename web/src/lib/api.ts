export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const DAY_DEMO = "2026-08-17";

export type Scores = {
  cap_score: number;
  promo_score: number;
  coord_score: number;
  astroturf_score: number;
  syndication_score: number;
  affiliate_ring: number;
  sentiment_vader: number;
};

export type Tweet = {
  id: string;
  author_id: string;
  /** Joins into `claims` to fetch this tweet's spread curve. */
  claim_id: string;
  created_at: string;
  body: string;
  is_retweet: boolean;
  register: string;
  diffusion: Diffusion;
  narratives: string[];
  like_count: number;
  reply_count: number;
  retweet_count: number;
  affiliate_code: string | null;
  scores: Scores;
  tags: string[];
  cluster: { size: number; authors: number };
};

export type Diffusion = "isolated" | "organic" | "coordinated" | "mixed";

export type Narrative = {
  key: string;
  label: string;
  total: number;
  originals: number;
  retweets: number;
  unique_authors: number;
  amplification_ratio: number;
  mean_sentiment: number;
  peak_hour?: string | null;
  hourly?: number[];
  top_example: string;
};

export type Claim = {
  claim_id: string;
  text: string;
  diffusion: Diffusion;
  copies: number;
  unique_authors: number;
  author_ratio: number;
  burstiness: number;
  span_minutes: number;
  first_seen: string;
  peak_hour?: string;
  hourly?: number[];
  narratives: string[];
  mean_sentiment: number;
};

/** How a forensic card points the feed at the rows it was built from. */
export type Focus =
  | { type: "claim"; value: string }
  | { type: "affiliate_code"; value: string }
  | { type: "hour"; value: string };

export type Anomaly = {
  id: string;
  narrative_type: string;
  headline: string;
  focus: Focus;
  evidence: Record<string, unknown> & { why_it_matters?: string };
  explanation?: string;
  tweets: Tweet[];
};

/** A single selection shared by the rail, the feed and the forensic cards, so
 *  that picking one always updates the others. */
export type Filter =
  | { kind: "all" }
  | { kind: "narrative"; key: string }
  | { kind: "card"; cardId: string; focus: Focus };

export function matches(t: Tweet, f: Filter): boolean {
  if (!f || f.kind === "all") return true;
  if (f.kind === "narrative") return t.narratives.includes(f.key);
  const focus = f.focus;
  if (!focus?.type || focus.value == null) return false;
  if (focus.type === "claim") return t.claim_id === focus.value;
  if (focus.type === "affiliate_code") return t.affiliate_code === focus.value;
  return t.created_at.slice(0, 13) === String(focus.value).slice(0, 13);
}

export type Hour = {
  hour: string;
  en_firehose: number;
  originals: number;
  retweets: number;
  topic_share_per_100k: number;
  sentiment: number;
  side_effect_rate: number;
  promo: number;
  astroturf: number;
  low_confidence: boolean;
};

export type Meta = {
  topic: string;
  day_utc: string | null;
  start_utc?: string | null;
  end_utc?: string | null;
  source: string;
  firehose_rows_scanned: number | null;
  english_rows: number | null;
  slice_rows: number;
  originals: number;
  retweets: number;
  score_definitions: Record<string, string>;
};

export type Payload = {
  meta: Meta;
  hourly: Hour[];
  narratives: Narrative[];
  claims: Claim[];
  anomalies: Anomaly[];
  feed: Tweet[];
};

export type Scope = { kind: "day"; date: string } | { kind: "range" };

function prefix(scope: Scope): string {
  return scope.kind === "day" ? `/api/day/${scope.date}` : "/api/range";
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export async function loadAll(scope: Scope): Promise<Payload> {
  const base = prefix(scope);
  const hourly =
    scope.kind === "day" ? get<Hour[]>(`${base}/hourly`) : Promise.resolve([] as Hour[]);
  const [meta, hours, narratives, claims, anomalies, feed] = await Promise.all([
    get<Meta>(`${base}/meta`),
    hourly,
    get<Narrative[]>(`${base}/narratives`),
    get<Claim[]>(`${base}/claims`),
    get<Anomaly[]>(`${base}/anomalies`),
    get<Tweet[]>(`${base}/feed?limit=20000`),
  ]);
  return { meta, hourly: hours, narratives, claims, anomalies, feed };
}

/** Colour + copy for each diffusion verdict. High volume is not guilt. */
export const DIFFUSION_STYLE: Record<
  Diffusion,
  { label: string; tone: string; blurb: string }
> = {
  isolated: {
    label: "Isolated",
    tone: "text-slate-400 border-slate-700 bg-slate-800/50",
    blurb: "No meaningful copies. Nothing to amplify.",
  },
  organic: {
    label: "Organic spread",
    tone: "text-emerald-300 border-emerald-800 bg-emerald-950/50",
    blurb: "Many distinct accounts, spread over hours. Looks like real virality.",
  },
  coordinated: {
    label: "Coordinated",
    tone: "text-rose-300 border-rose-800 bg-rose-950/50",
    blurb: "Copies concentrated in a short burst from few accounts.",
  },
  mixed: {
    label: "Mixed signals",
    tone: "text-amber-300 border-amber-800 bg-amber-950/50",
    blurb: "Some coordination markers, but not conclusive.",
  },
};

export function capBand(score: number) {
  if (score >= 0.5) return { label: "High", tone: "text-rose-400" };
  if (score >= 0.25) return { label: "Elevated", tone: "text-amber-400" };
  if (score >= 0.1) return { label: "Low", tone: "text-sky-400" };
  return { label: "Clean", tone: "text-emerald-400" };
}

export const fmt = new Intl.NumberFormat("en-US");

export function plural(n: number, word: string) {
  return `${fmt.format(n)} ${word}${n === 1 ? "" : "s"}`;
}

export function hourLabel(iso: string) {
  return `${String(new Date(iso).getUTCHours()).padStart(2, "0")}:00 UTC`;
}

export function stamp(iso: string, withDate: boolean) {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  if (!withDate) return `${hh}:${mm}`;
  const mon = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  return `${mon} ${d.getUTCDate()} · ${hh}:${mm}`;
}
