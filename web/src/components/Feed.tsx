"use client";

import { useRef, useState } from "react";
import CapCard from "./CapCard";
import { Claim, Tweet, capBand, fmt } from "@/lib/api";

/** Must match the CapCard width and its rough max height, so the card can be
 *  positioned before it has rendered and been measured. */
const CARD_W = 340;
const CARD_H = 470;

function Avatar({ id }: { id: string }) {
  const hue = Number(id.slice(-4)) % 360;
  return (
    <div
      className="h-10 w-10 shrink-0 rounded-full"
      style={{ background: `linear-gradient(135deg,hsl(${hue} 55% 45%),hsl(${(hue + 50) % 360} 55% 30%))` }}
    />
  );
}

function handleOf(t: Tweet) {
  return `@user_${t.author_id.slice(-6)}`;
}

function timeOf(iso: string) {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <span className="tabular-nums">
      {label} {fmt.format(value)}
    </span>
  );
}

export default function Feed({
  tweets,
  claims,
  limit,
}: {
  tweets: Tweet[];
  claims: Claim[];
  limit: number;
}) {
  const [hovered, setHovered] = useState<Tweet | null>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const listRef = useRef<HTMLDivElement>(null);

  const claimById = new Map(claims.map((c) => [c.claim_id, c]));
  const shown = tweets.slice(0, limit);

  function onEnter(t: Tweet, e: React.MouseEvent<HTMLElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const gap = 16;
    // Prefer the right of the row, flip to the left when that would run off
    // screen or cover the forensics panel, and clamp as a last resort.
    let left = r.right + gap;
    if (left + CARD_W > window.innerWidth - 8) left = r.left - CARD_W - gap;
    left = Math.max(8, Math.min(left, window.innerWidth - CARD_W - 8));
    const top = Math.max(8, Math.min(r.top, window.innerHeight - CARD_H - 8));
    setPos({ top, left });
    setHovered(t);
  }

  return (
    <div ref={listRef} className="relative">
      {shown.length === 0 && (
        <p className="p-8 text-center text-sm text-slate-500">
          Nothing matches this selection.
        </p>
      )}

      {shown.map((t) => {
        const band = capBand(t.scores.cap_score);
        return (
          <article
            key={t.id}
            onMouseEnter={(e) => onEnter(t, e)}
            onMouseLeave={() => setHovered(null)}
            className="flex cursor-default gap-3 border-b border-slate-800 px-4 py-3 transition-colors hover:bg-slate-900/70"
          >
            <Avatar id={t.author_id} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-semibold text-slate-100">{handleOf(t)}</span>
                <span className="text-slate-500">· {timeOf(t.created_at)} UTC</span>
                {t.is_retweet && (
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                    RT
                  </span>
                )}
                <span className={`ml-auto text-xs font-medium tabular-nums ${band.tone}`}>
                  {t.scores.cap_score.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap break-words text-[15px] leading-snug text-slate-200">
                {t.body}
              </p>
              <div className="mt-2 flex gap-5 text-xs text-slate-500">
                <Stat label="↺" value={t.retweet_count} />
                <Stat label="♥" value={t.like_count} />
                <Stat label="💬" value={t.reply_count} />
                {t.cluster.size > 1 && (
                  <span
                    className="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-slate-300"
                    title="This row stands for every identical copy of the claim"
                  >
                    {fmt.format(t.cluster.size)} copies ·{" "}
                    {fmt.format(t.cluster.authors)} accounts
                  </span>
                )}
              </div>
            </div>
          </article>
        );
      })}

      {hovered && (
        <div
          className="pointer-events-none fixed z-50"
          style={{ top: pos.top, left: pos.left }}
        >
          <CapCard tweet={hovered} claim={claimById.get(hovered.claim_id)} />
        </div>
      )}
    </div>
  );
}
