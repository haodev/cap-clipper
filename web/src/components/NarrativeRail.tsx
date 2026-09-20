"use client";

import Sparkline from "./Sparkline";
import { Filter, Narrative, fmt, hourLabel } from "@/lib/api";

export default function NarrativeRail({
  narratives,
  filter,
  onSelect,
  counts,
  showHourly = true,
}: {
  narratives: Narrative[];
  filter: Filter;
  onSelect: (key: string | null) => void;
  /** Feed rows per narrative, so the rail never promises more than it shows. */
  counts: Record<string, number>;
  showHourly?: boolean;
}) {
  const active = filter.kind === "narrative" ? filter.key : null;

  return (
    <aside className="space-y-2">
      <div className="flex items-baseline justify-between px-1">
        <h2 className="text-sm font-semibold text-slate-200">Narratives</h2>
        {active && (
          <button
            onClick={() => onSelect(null)}
            className="text-[11px] text-sky-400 hover:underline"
          >
            clear
          </button>
        )}
      </div>
      <p className="px-1 pb-1 text-[11px] leading-relaxed text-slate-500">
        {showHourly
          ? "Found bottom-up from the day's text, not from a preset topic list. Counts are distinct claims / total posts."
          : "Same narrative lexicon as the day demo, scored across the labeled window. Counts are distinct claims / total posts."}
      </p>

      {narratives.map((n) => {
        const on = active === n.key;
        const peakIdx =
          showHourly && n.peak_hour ? new Date(n.peak_hour).getUTCHours() : undefined;
        return (
          <button
            key={n.key}
            onClick={() => onSelect(on ? null : n.key)}
            className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
              on
                ? "border-sky-600 bg-sky-950/40"
                : "border-slate-800 bg-slate-900/40 hover:border-slate-700"
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-slate-100">{n.label}</span>
              <span
                className="shrink-0 text-xs tabular-nums text-slate-400"
                title={`${counts[n.key] ?? 0} distinct claims · ${n.total} posts`}
              >
                {fmt.format(counts[n.key] ?? 0)}
                <span className="text-slate-600"> / {fmt.format(n.total)}</span>
              </span>
            </div>
            {showHourly && n.hourly && n.hourly.length > 0 && (
              <>
                <Sparkline
                  values={n.hourly}
                  width={230}
                  height={32}
                  markIndex={peakIdx}
                  stroke={on ? "#38bdf8" : "#64748b"}
                  fill={on ? "rgba(56,189,248,0.16)" : "rgba(100,116,139,0.12)"}
                />
                <div className="flex justify-between text-[10px] text-slate-500">
                  <span>peak {n.peak_hour ? hourLabel(n.peak_hour) : "—"}</span>
                  <span>{n.amplification_ratio.toFixed(1)}x amplified</span>
                </div>
              </>
            )}
            {!showHourly && (
              <div className="mt-1 text-[10px] text-slate-500">
                {n.amplification_ratio.toFixed(1)}x amplified
              </div>
            )}
          </button>
        );
      })}
    </aside>
  );
}
