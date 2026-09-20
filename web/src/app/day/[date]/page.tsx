"use client";

import Dashboard from "@/components/Dashboard";
import { DAY_DEMO } from "@/lib/api";
import { useParams } from "next/navigation";

export default function DayPage() {
  const params = useParams<{ date: string }>();
  const date = params.date;
  if (date !== DAY_DEMO) {
    return (
      <main className="mx-auto max-w-lg p-16 text-sm text-slate-300">
        <h1 className="mb-2 text-lg font-semibold text-slate-100">No day demo for {date}</h1>
        <p className="text-slate-400">
          The hour-by-hour demo is frozen for {DAY_DEMO} UTC only. Open that date, or go back
          to the multi-day labeled slice.
        </p>
      </main>
    );
  }
  return <Dashboard scope={{ kind: "day", date }} />;
}
