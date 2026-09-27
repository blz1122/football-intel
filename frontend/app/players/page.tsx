"use client";
// 球员列表：联赛/位置筛选 + AI 评分排行，点击进入球员详情页
import Link from "next/link";
import { useState } from "react";
import { Panel, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const POS_CN: Record<string, string> = { GK: "门将", DF: "后卫", MF: "中场", FW: "前锋" };
const POS_COLOR: Record<string, string> = {
  GK: "bg-[#2a2417] text-[#f5b342]",
  DF: "bg-[#16264d] text-[#9db9ff]",
  MF: "bg-[#1d3a2a] text-[#4ade80]",
  FW: "bg-[#3a1d24] text-[#ff7a85]",
};
const POSITIONS = ["FW", "MF", "DF", "GK"] as const;

export default function PlayersPage() {
  const { data: leagues } = usePolling(() => api.leagues(), 600000);
  const [leagueId, setLeagueId] = useState<number | "all">("all");
  const [position, setPosition] = useState<string | "all">("all");

  const params: { league_id?: number; position?: string } = {};
  if (leagueId !== "all") params.league_id = leagueId;
  if (position !== "all") params.position = position;
  const { data: players, loading } = usePolling(
    () => api.playerList(Object.keys(params).length ? params : undefined),
    60000,
  );

  return (
    <div className="page-in">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-xl font-black">👤 球员中心</h1>
        <button
          onClick={() => setLeagueId("all")}
          className={`rounded-lg border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
            leagueId === "all"
              ? "border-[#28437f] bg-[#16264d] text-[#9db9ff]"
              : "border-transparent bg-panel2 text-sub hover:text-txt"
          }`}
        >
          全部联赛
        </button>
        {(leagues ?? []).map((l) => (
          <button
            key={l.id}
            onClick={() => setLeagueId(l.id)}
            className={`rounded-lg border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              leagueId === l.id
                ? "border-[#28437f] bg-[#16264d] text-[#9db9ff]"
                : "border-transparent bg-panel2 text-sub hover:text-txt"
            }`}
          >
            {l.name}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-line" />
        <button
          onClick={() => setPosition("all")}
          className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
            position === "all"
              ? "border-[#28437f] bg-[#16264d] text-[#9db9ff]"
              : "border-transparent bg-panel2 text-sub hover:text-txt"
          }`}
        >
          全部位置
        </button>
        {POSITIONS.map((p) => (
          <button
            key={p}
            onClick={() => setPosition(p)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
              position === p
                ? "border-[#28437f] bg-[#16264d] text-[#9db9ff]"
                : "border-transparent bg-panel2 text-sub hover:text-txt"
            }`}
          >
            {POS_CN[p]}
          </button>
        ))}
      </div>

      <Panel
        title="⭐ AI Player Rating 排行"
        tag={players ? `${players.length} 名球员` : "加载中"}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-line text-sub">
              <tr>
                <th className="px-4 py-2.5 font-semibold">#</th>
                <th className="px-2 py-2.5 font-semibold">球员</th>
                <th className="px-2 py-2.5 font-semibold">球队</th>
                <th className="px-2 py-2.5 font-semibold">位置</th>
                <th className="px-2 py-2.5 font-semibold">号码</th>
                <th className="px-2 py-2.5 font-semibold">进球/助攻</th>
                <th className="px-2 py-2.5 text-right font-semibold">AI 评分</th>
              </tr>
            </thead>
            <tbody>
              {loading && !players
                ? Array.from({ length: 12 }, (_, i) => (
                    <tr key={i}>
                      <td colSpan={7} className="px-4 py-2">
                        <Skeleton className="h-5 w-full" />
                      </td>
                    </tr>
                  ))
                : (players ?? []).map((p, i) => (
                    <tr key={p.id} className="border-b border-line transition-colors last:border-b-0 hover:bg-panel2">
                      <td className={`px-4 py-2.5 tabular-nums font-extrabold ${i < 3 ? "text-gold" : "text-sub"}`}>
                        {i + 1}
                      </td>
                      <td className="px-2 py-2.5">
                        <Link href={`/player/${p.id}`} className="font-bold hover:text-accent2">
                          {p.name}
                        </Link>
                        <span className="ml-2 text-[10px] text-sub">{p.name_en}</span>
                      </td>
                      <td className="px-2 py-2.5">
                        <Link href={`/team/${p.team_id}`} className="flex items-center gap-1.5 font-semibold hover:text-accent2">
                          <span
                            className="flex h-5 w-5 items-center justify-center rounded-full text-[8px] font-extrabold text-white"
                            style={{ background: p.team_color }}
                          >
                            {p.team_short}
                          </span>
                          {p.team_name}
                        </Link>
                      </td>
                      <td className="px-2 py-2.5">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${POS_COLOR[p.position] ?? "bg-panel2 text-sub"}`}>
                          {POS_CN[p.position] ?? p.position}
                        </span>
                      </td>
                      <td className="px-2 py-2.5 tabular-nums text-sub">{p.number}</td>
                      <td className="px-2 py-2.5 tabular-nums">
                        {p.season_stats.goals ?? 0} / {p.season_stats.assists ?? 0}
                      </td>
                      <td className="px-2 py-2.5 text-right">
                        <span
                          className={`rounded px-2 py-0.5 font-extrabold tabular-nums ${
                            p.ai_rating >= 8
                              ? "bg-[#1d3a2a] text-[#4ade80]"
                              : p.ai_rating >= 7
                                ? "bg-[#16264d] text-[#9db9ff]"
                                : "bg-panel2 text-sub"
                          }`}
                        >
                          {p.ai_rating.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
              {players && players.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-sub">
                    该筛选条件下暂无球员
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
