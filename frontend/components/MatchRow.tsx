"use client";
// 比赛行卡片 —— Dashboard 列表复用
// 整行点击进比赛详情；队徽/队名点击进球队详情页（阻止冒泡）
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MatchListItem } from "@/lib/types";
import { ProbBar, StatusTag, TeamBadge } from "./ui";

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export default function MatchRow({ m }: { m: MatchListItem }) {
  const router = useRouter();
  const live = m.status === "live" || m.status === "halftime";

  const teamLink = (team: MatchListItem["home_team"]) => (
    <Link
      href={`/team/${team.id}`}
      onClick={(e) => e.stopPropagation()}
      className="flex min-w-0 items-center gap-2 text-sm font-semibold hover:text-accent2"
      title={`查看 ${team.name} 球队页`}
    >
      <TeamBadge team={team} />
      <span className="truncate">{team.name}</span>
    </Link>
  );

  return (
    <div
      onClick={() => router.push(`/match/${m.id}`)}
      className="grid cursor-pointer grid-cols-[130px_1fr_auto] items-center gap-3 border-b border-line px-4 py-3 transition-colors last:border-b-0 hover:bg-panel2 md:grid-cols-[150px_1fr_200px_130px]"
      title="查看比赛详情"
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
        <div className="flex items-center">{teamLink(m.home_team)}</div>
        <div className="flex items-center">{teamLink(m.away_team)}</div>
      </div>

      <div className="hidden justify-end md:flex">
        {m.status === "scheduled" ? (
          <span className="text-xs text-sub">vs</span>
        ) : (
          <div className="flex gap-2 tabular-nums">
            {/* key 含比分值：比分变化时重新挂载触发 scoreFlash 动画 */}
            <span
              key={m.home_score}
              className={`score-flash min-w-7 rounded border px-2 py-0.5 text-center text-base font-extrabold ${
                m.home_score >= m.away_score ? "border-[#4d3d1c] text-gold" : "border-line2 text-txt"
              } bg-base2`}
            >
              {m.home_score}
            </span>
            <span
              key={m.away_score}
              className={`score-flash min-w-7 rounded border px-2 py-0.5 text-center text-base font-extrabold ${
                m.away_score >= m.home_score ? "border-[#4d3d1c] text-gold" : "border-line2 text-txt"
              } bg-base2`}
            >
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
    </div>
  );
}
