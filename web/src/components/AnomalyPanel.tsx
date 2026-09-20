"use client";

import { useState } from "react";
import { Anomaly, Filter, fmt } from "@/lib/api";

const TONE: Record<string, string> = {
  organic_virality: "border-emerald-800 bg-emerald-950/30 text-emerald-300",
  telehealth_astroturf: "border-rose-800 bg-rose-950/30 text-rose-300",
  syndication_not_astroturf: "border-sky-800 bg-sky-950/30 text-sky-300",
  side_effect_cluster: "border-amber-800 bg-amber-950/30 text-amber-300",
  side_effect_panic: "border-amber-800 bg-amber-950/30 text-amber-300",
  sentiment_blindspot: "border-violet-800 bg-violet-950/30 text-violet-300",
};

const HIDDEN = new Set(["why_it_matters", "text", "template"]);

function label(k: string) {
  return k.replace(/_/g, " ");
}

function render(v: unknown) {
  if (typeof v === "number") return Number.isInteger(v) ? fmt.format(v) : v.toFixed(3);
  if (v === null) return "—";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) {
    const d = new Date(v);
    return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
  }
  return String(v);
}

export default function AnomalyPanel({
  anomalies,
  filter,
  onFocus,
  focusCounts,
}: {
  anomalies: Anomaly[];
  filter: Filter;
  onFocus: (card: Anomaly | null) => void;
  /** Feed rows each card would show, so the button can say so up front. */
  focusCounts: Record<string, number>;
}) {
  const [open, setOpen] = useState<string | null>(anomalies[0]?.id ?? null);
  const focused = filter?.kind === "card" ? filter.cardId : null;

  return (
    <aside className="space-y-3">
      <h2 className="px-1 text-sm font-semibold text-slate-200">Forensic findings</h2>
      <p className="px-1 text-[11px] leading-relaxed text-slate-500">
        Each card separates what spread from why. Volume alone is never the verdict.
      </p>

      {anomalies.map((a) => {
        const on = open === a.id;
        const quote = (a.evidence.text ?? a.evidence.template) as string | undefined;
        return (
          <div
            key={a.id}
            className={`rounded-lg border ${TONE[a.narrative_type] ?? "border-slate-800 bg-slate-900/40 text-slate-300"} ${
              focused === a.id ? "ring-1 ring-current" : ""
            }`}
          >
            <button
              onClick={() => setOpen(on ? null : a.id)}
              className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
            >
              <span className="text-[13px] font-medium leading-snug">{a.headline}</span>
              <span className="ml-auto shrink-0 text-xs opacity-60">{on ? "−" : "+"}</span>
            </button>

            {on && (
              <div className="space-y-3 border-t border-white/10 px-3 py-3">
                {quote && (
                  <blockquote className="border-l-2 border-current/40 pl-2 text-[12px] italic leading-snug text-slate-300">
                    {quote}
                  </blockquote>
                )}

                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                  {Object.entries(a.evidence)
                    .filter(([k]) => !HIDDEN.has(k))
                    .map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="capitalize text-slate-500">{label(k)}</dt>
                        <dd className="text-right tabular-nums text-slate-300">
                          {render(v)}
                        </dd>
                      </div>
                    ))}
                </dl>

                {a.explanation ? (
                  <p className="rounded bg-black/30 p-2 text-[12px] leading-relaxed text-slate-300">
                    {a.explanation}
                  </p>
                ) : (
                  a.evidence.why_it_matters && (
                    <p className="rounded bg-black/30 p-2 text-[12px] leading-relaxed text-slate-300">
                      {a.evidence.why_it_matters}
                    </p>
                  )
                )}

                <div className="space-y-1.5">
                  {a.tweets.slice(0, 3).map((t) => (
                    <p
                      key={t.id}
                      className="truncate rounded bg-slate-900/60 px-2 py-1 text-[11px] text-slate-400"
                      title={t.body}
                    >
                      {t.body}
                    </p>
                  ))}
                </div>

                <button
                  onClick={() => onFocus(focused === a.id ? null : a)}
                  className="w-full rounded border border-current/40 py-1.5 text-[11px] font-medium hover:bg-white/5"
                >
                  {focused === a.id
                    ? "Clear feed filter"
                    : `Show these ${focusCounts[a.id] ?? 0} in the feed`}
                </button>
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
