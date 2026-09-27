"use client";
// 比赛行卡片 —— Dashboard 列表复用
import Link from "next/link";
import type { MatchListItem } from "@/lib/types";
import { ProbBar, StatusTag, TeamBadge } from "./ui";

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export default function MatchRow({ m }: { m: MatchListItem }) {
  const live = m.status === "live" || m.status === "halftime";
  return (
    <Link
      href={`/match/${m.id}`}
      className="grid grid-cols-[130px_1fr_auto] items-center gap-3 border-b border-line px-4 py-3 transition-colors last:border-b-0 hover:bg-panel2 md:grid-cols-[150px_1fr_200px_130px]"
    >
      <div>
        <div className="flex items-center gap-2 text-xs text-sub">
          <span className="rounded bg-panel2 px-1.5 py-0.5 text-[10px] font-extrabold text-[#9db9ff]">
            {m.league.short_name}
          </span>
          {m.round?.split(" - ")[1] && `第${m.round.split(" - ")[1]}轮`}
        </div>
        <div className={`mt-1 text-sm font-bold tabular-nums ${live ? "text-live" : "text-txt"}`}>
          {live ? `LIVE ${m.minute}'` : m.status === "finished" ? "完赛" : fmtTime(m.kickoff_at)}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <TeamBadge team={m.home_team} />
          <span className="truncate">{m.home_team.name}</span>
        </div>
        <div className="flex items-center gap-2 text-sm font-semibold">
          <TeamBadge team={m.away_team} />
          <span className="truncate">{m.away_team.name}</span>
        </div>
      </div>

      <div className="hidden justify-end md:flex">
        {m.status === "scheduled" ? (
          <span className="text-xs text-sub">vs</span>
        ) : (
          <div className="flex gap-2 tabular-nums">
            <span className={`min-w-7 rounded border px-2 py-0.5 text-center text-base font-extrabold ${m.home_score >= m.away_score ? "border-[#4d3d1c] text-gold" : "border-line2 text-txt"} bg-base2`}>
              {m.home_score}
            </span>
            <span className={`min-w-7 rounded border px-2 py-0.5 text-center text-base font-extrabold ${m.away_score >= m.home_score ? "border-[#4d3d1c] text-gold" : "border-line2 text-txt"} bg-base2`}>
              {m.away_score}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-col items-end gap-1.5">
        <StatusTag status={m.status} period={m.period} />
        <div className="hidden w-40 md:block">
          <ProbBar p={m.win_prob} />
        </div>
      </div>
    </Link>
  );
}
