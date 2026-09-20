"use client";

import { Hour, Meta, fmt } from "@/lib/api";

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums text-slate-100">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

/** Topic share over the day. Bars, not a line, because several hours are
 *  low-confidence and should read as gaps rather than interpolation. */
export default function DayStrip({ hourly, meta }: { hourly: Hour[]; meta: Meta }) {
  const max = Math.max(...hourly.map((h) => h.topic_share_per_100k), 1);

  return (
    <div className="flex flex-wrap items-end gap-x-10 gap-y-4 border-b border-slate-800 px-5 py-4">
      <Metric
        label="Firehose scanned"
        value={
          meta.firehose_rows_scanned != null
            ? `${(meta.firehose_rows_scanned / 1e6).toFixed(0)}M`
            : "—"
        }
        sub={meta.english_rows != null ? `${fmt.format(meta.english_rows)} English` : undefined}
      />
      <Metric
        label="GLP-1 slice"
        value={fmt.format(meta.slice_rows)}
        sub={`${fmt.format(meta.originals)} original · ${fmt.format(meta.retweets)} RT`}
      />

      <div className="min-w-[260px] flex-1">
        <div className="mb-1 flex justify-between text-[10px] uppercase tracking-wider text-slate-500">
          <span>Topic share per 100k English tweets</span>
          <span className="normal-case tracking-normal">{meta.day_utc} UTC</span>
        </div>
        <div className="flex h-10 items-end gap-[3px]">
          {hourly.map((h) => (
            <div
              key={h.hour}
              title={`${new Date(h.hour).getUTCHours()}:00 — ${h.topic_share_per_100k.toFixed(1)} per 100k${
                h.low_confidence ? " (low confidence)" : ""
              }`}
              className={`flex-1 rounded-sm ${
                h.low_confidence ? "bg-slate-700" : "bg-sky-500"
              }`}
              style={{ height: `${Math.max((h.topic_share_per_100k / max) * 100, 4)}%` }}
            />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-slate-500">
          <span>00h</span>
          <span className="text-slate-600">grey = too few tweets to trust</span>
          <span>23h</span>
        </div>
      </div>
    </div>
  );
}
