"use client";

import Sparkline from "./Sparkline";
import {
  Claim,
  DIFFUSION_STYLE,
  Tweet,
  capBand,
  fmt,
  hourLabel,
} from "@/lib/api";

function Bar({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="group/bar">
      <div className="flex justify-between text-[11px] text-slate-400">
        <span title={hint}>{label}</span>
        <span className="tabular-nums text-slate-300">{value.toFixed(2)}</span>
      </div>
      <div className="mt-1 h-1 rounded-full bg-slate-800">
        <div
          className="h-1 rounded-full bg-sky-500"
          style={{ width: `${Math.min(value, 1) * 100}%` }}
        />
      </div>
    </div>
  );
}

export default function CapCard({
  tweet,
  claim,
  showHourly = true,
}: {
  tweet: Tweet;
  claim?: Claim;
  showHourly?: boolean;
}) {
  const s = tweet.scores;
  const band = capBand(s.cap_score);
  // Ring members rewrite the copy per vendor, so text clustering calls them
  // isolated. The shared code is the stronger link and should lead the card.
  const diff =
    s.affiliate_ring > 0 && tweet.diffusion === "isolated"
      ? {
          label: "Linked by promo code",
          tone: "text-amber-300 border-amber-800 bg-amber-950/50",
          blurb:
            "Text is unique, but the same code appears under other accounts and vendor names.",
        }
      : DIFFUSION_STYLE[tweet.diffusion];
  const peakIdx =
    showHourly && claim?.peak_hour ? new Date(claim.peak_hour).getUTCHours() : undefined;

  return (
    <div className="w-[340px] rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl shadow-black/60">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
          Cap Score
        </span>
        <span className={`text-2xl font-semibold tabular-nums ${band.tone}`}>
          {s.cap_score.toFixed(2)}
          <span className="ml-2 text-xs font-normal">{band.label}</span>
        </span>
      </div>

      <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${diff.tone}`}>
        <div className="font-semibold">{diff.label}</div>
        <div className="mt-0.5 opacity-80">{diff.blurb}</div>
      </div>

      {claim && claim.copies > 1 && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-[11px] text-slate-400">
            <span>Spread of this exact claim</span>
            <span className="tabular-nums">
              {fmt.format(claim.copies)} copies / {fmt.format(claim.unique_authors)} accounts
            </span>
          </div>
          {showHourly && claim.hourly && claim.hourly.length > 0 && (
            <>
              <Sparkline
                values={claim.hourly}
                width={300}
                markIndex={peakIdx}
                stroke={tweet.diffusion === "coordinated" ? "#fb7185" : "#34d399"}
                fill={
                  tweet.diffusion === "coordinated"
                    ? "rgba(251,113,133,0.15)"
                    : "rgba(52,211,153,0.15)"
                }
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>00:00</span>
                <span>peak {claim.peak_hour ? hourLabel(claim.peak_hour) : "—"}</span>
                <span>23:00</span>
              </div>
            </>
          )}
        </div>
      )}

      <div className="mt-3 space-y-2">
        <Bar
          label="Astroturf"
          value={s.astroturf_score}
          hint="Same text from multiple accounts, outside the news register"
        />
        <Bar
          label="Promo"
          value={s.promo_score}
          hint="Density of explicit commercial call-to-action or price language"
        />
        {s.syndication_score > 0 && (
          <Bar
            label="Syndication"
            value={s.syndication_score}
            hint="Duplicate text inside the news register - wire copy, not a campaign"
          />
        )}
        {s.affiliate_ring > 0 && (
          <Bar
            label="Affiliate ring"
            value={s.affiliate_ring}
            hint="Promo code shared across accounts and vendor brands"
          />
        )}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-slate-800 pt-3 text-[11px]">
        <dt className="text-slate-500">Register</dt>
        <dd className="text-right text-slate-300">{tweet.register}</dd>
        <dt className="text-slate-500">Sentiment</dt>
        <dd className="text-right tabular-nums text-slate-300">
          {s.sentiment_vader.toFixed(2)}
        </dd>
        {tweet.affiliate_code && (
          <>
            <dt className="text-slate-500">Promo code</dt>
            <dd className="text-right font-mono text-amber-300">{tweet.affiliate_code}</dd>
          </>
        )}
        {tweet.tags.length > 0 && (
          <>
            <dt className="text-slate-500">Tags</dt>
            <dd className="text-right text-slate-300">{tweet.tags.join(", ")}</dd>
          </>
        )}
      </dl>

      <p className="mt-3 border-t border-slate-800 pt-2 text-[10px] leading-relaxed text-slate-500">
        Scores are lexicon and pattern heuristics
        {showHourly ? " over one UTC day" : " over the labeled window"}, not a medical or
        legal judgement.
      </p>
    </div>
  );
}
