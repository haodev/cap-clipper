"use client";

import Link from "next/link";
import { DAY_DEMO } from "@/lib/api";

export default function SiteNav({ current }: { current: "range" | "day" }) {
  const tab =
    "rounded px-2 py-1 text-[11px] hover:bg-slate-800";
  const on = "bg-slate-800 text-slate-100";
  const off = "text-slate-400";
  return (
    <nav className="mt-1 flex gap-1">
      <Link href="/" className={`${tab} ${current === "range" ? on : off}`}>
        Multi-day
      </Link>
      <Link
        href={`/day/${DAY_DEMO}`}
        className={`${tab} ${current === "day" ? on : off}`}
      >
        Day demo · {DAY_DEMO}
      </Link>
    </nav>
  );
}
