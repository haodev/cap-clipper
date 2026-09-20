"use client";

import { Meta, fmt } from "@/lib/api";

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums text-slate-100">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

/** Totals for the labeled window. No time bars — hour-by-hour lives on the day demo. */
export default function RangeStrip({ meta }: { meta: Meta }) {
  const en = meta.english_rows;
  return (
    <div className="flex flex-wrap items-end gap-x-10 gap-y-4 border-b border-slate-800 px-5 py-4">
      <Metric
        label="Window"
        value={`${meta.start_utc ?? "—"} → ${meta.end_utc ?? "—"}`}
        sub="UTC, no day filter"
      />
      <Metric
        label="GLP-1 slice"
        value={fmt.format(meta.slice_rows)}
        sub={`${fmt.format(meta.originals)} original · ${fmt.format(meta.retweets)} RT`}
      />
      {en != null && (
        <Metric label="English rows" value={fmt.format(en)} sub="all languages kept in the slice" />
      )}
    </div>
  );
}
