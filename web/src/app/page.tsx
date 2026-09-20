"use client";

import { useEffect, useMemo, useState } from "react";
import AnomalyPanel from "@/components/AnomalyPanel";
import DayStrip from "@/components/DayStrip";
import Feed from "@/components/Feed";
import NarrativeRail from "@/components/NarrativeRail";
import {
  API,
  Anomaly,
  Filter,
  Payload,
  fmt,
  hourLabel,
  loadAll,
  matches,
  plural,
} from "@/lib/api";

const PAGE = 60;

export default function Home() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>({ kind: "all" });
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    loadAll().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  // Any change of selection starts the list again from the top.
  function select(next: Filter) {
    setFilter(next);
    setLimit(PAGE);
  }

  const shown = useMemo(
    () => (data ? data.feed.filter((t) => matches(t, filter)) : []),
    [data, filter],
  );

  const narrativeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    data?.feed.forEach((t) => t.narratives.forEach((n) => (c[n] = (c[n] ?? 0) + 1)));
    return c;
  }, [data]);

  const focusCounts = useMemo(() => {
    const c: Record<string, number> = {};
    data?.anomalies.forEach((a) => {
      c[a.id] = data.feed.filter((t) =>
        matches(t, { kind: "card", cardId: a.id, focus: a.focus }),
      ).length;
    });
    return c;
  }, [data]);

  if (error) {
    return (
      <main className="mx-auto max-w-lg p-16 text-sm text-slate-300">
        <h1 className="mb-2 text-lg font-semibold text-rose-400">API unreachable</h1>
        <p className="mb-4 text-slate-400">
          The frontend could not read <code className="text-slate-200">{API}</code>. Start
          the backend:
        </p>
        <pre className="rounded bg-slate-900 p-3 text-xs text-slate-300">
          uvicorn backend.main:app --port 8000
        </pre>
        <p className="mt-4 text-xs text-slate-600">{error}</p>
      </main>
    );
  }

  if (!data) {
    return <main className="p-16 text-sm text-slate-500">Loading the day…</main>;
  }

  const narrative =
    filter.kind === "narrative"
      ? data.narratives.find((n) => n.key === filter.key)
      : undefined;
  const card =
    filter.kind === "card" ? data.anomalies.find((a) => a.id === filter.cardId) : undefined;

  const copies = shown.reduce((n, t) => n + t.cluster.size, 0);

  let title = "All GLP-1 claims";
  let subtitle = `${plural(shown.length, "distinct claim")} · ${plural(copies, "post")}`;
  if (narrative) {
    title = narrative.label;
    subtitle = `${plural(shown.length, "distinct claim")} · ${plural(narrative.total, "post")} · ${plural(narrative.unique_authors, "account")}`;
  } else if (card) {
    title = card.headline;
    subtitle =
      card.focus?.type === "hour"
        ? `everything posted in ${hourLabel(card.focus.value)}`
        : `${plural(shown.length, "claim")} · ${plural(copies, "post")} behind this finding`;
  }

  function focusCard(a: Anomaly | null) {
    select(a ? { kind: "card", cardId: a.id, focus: a.focus } : { kind: "all" });
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-slate-800 px-5 py-3">
        <h1 className="text-base font-semibold tracking-tight text-slate-100">
          CapClipper<span className="ml-2 font-normal text-slate-500">GLP-1 discourse</span>
        </h1>
        <p className="text-[11px] text-slate-500">{data.meta.source}</p>
      </header>

      <DayStrip hourly={data.hourly} meta={data.meta} />

      <div className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
        <NarrativeRail
          narratives={data.narratives}
          filter={filter}
          counts={narrativeCounts}
          onSelect={(key) =>
            select(key ? { kind: "narrative", key } : { kind: "all" })
          }
        />

        <section className="rounded-xl border border-slate-800 bg-slate-950/40">
          <div className="border-b border-slate-800 px-4 py-2.5">
            <div className="flex items-start gap-3">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-slate-200">{title}</h2>
                <p className="text-[11px] text-slate-500">{subtitle}</p>
              </div>
              {filter.kind !== "all" && (
                <button
                  onClick={() => select({ kind: "all" })}
                  className="ml-auto shrink-0 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                >
                  Show everything
                </button>
              )}
            </div>
            <p className="mt-1 text-[11px] text-slate-600">
              One row per distinct claim. Hover any row for the forensic card.
            </p>
          </div>

          <Feed tweets={shown} claims={data.claims} limit={limit} />

          {shown.length > limit && (
            <button
              onClick={() => setLimit((n) => n + PAGE)}
              className="w-full border-t border-slate-800 py-3 text-xs text-sky-400 hover:bg-slate-900"
            >
              Show {Math.min(PAGE, shown.length - limit)} more of{" "}
              {fmt.format(shown.length)}
            </button>
          )}
        </section>

        <AnomalyPanel
          anomalies={data.anomalies}
          filter={filter}
          onFocus={focusCard}
          focusCounts={focusCounts}
        />
      </div>

      <footer className="border-t border-slate-800 px-5 py-4 text-[11px] leading-relaxed text-slate-600">
        One UTC day ({data.meta.day_utc}) of the X firehose:{" "}
        {fmt.format(data.meta.slice_rows)} posts collapsed into{" "}
        {fmt.format(data.feed.length)} distinct claims. Scores are lexicon and pattern
        heuristics, not medical or legal judgements. Hours with too few tweets are marked
        low-confidence rather than smoothed over.
      </footer>
    </main>
  );
}
