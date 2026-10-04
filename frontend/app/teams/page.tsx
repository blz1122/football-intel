"use client";
// 球队列表：按联赛分组展示全部球队，点击进入球队详情页
import Link from "next/link";
import { useMemo, useState } from "react";
import { Panel, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

export default function TeamsPage() {
  const { data: leagues } = usePolling(() => api.leagues(), 600000);
  const { data: teams, loading } = usePolling(() => api.teamList(), 60000);
  const [leagueId, setLeagueId] = useState<number | "all">("all");

  const grouped = useMemo(() => {
    const list = teams ?? [];
    const byLeague = new Map<number, { name: string; teams: typeof list }>();
    for (const t of list) {
      if (leagueId !== "all" && t.league.id !== leagueId) continue;
      if (!byLeague.has(t.league.id)) {
        byLeague.set(t.league.id, { name: t.league.name, teams: [] });
      }
      byLeague.get(t.league.id)!.teams.push(t);
    }
    return Array.from(byLeague.values());
  }, [teams, leagueId]);

  return (
    <div className="page-in">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-xl font-black">🛡️ 球队中心</h1>
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
      </div>

      {loading && !teams ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map((g) => (
            <Panel key={g.name} title={g.name} tag={`${g.teams.length} 支球队`}>
              <div className="grid gap-2 px-4 py-4 sm:grid-cols-2 lg:grid-cols-3">
                {g.teams.map((t, i) => (
                  <Link
                    key={t.id}
                    href={`/team/?id=${t.id}`}
                    className="rise-in flex items-center gap-3 rounded-xl border border-line bg-panel2 px-3.5 py-3 transition-colors hover:border-[#28437f]"
                    style={{ animationDelay: `${Math.min(i, 12) * 35}ms` }}
                  >
                    <span
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-extrabold text-white"
                      style={{ background: t.color }}
                    >
                      {t.short_name}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-bold">{t.name}</span>
                      <span className="block truncate text-[11px] text-sub">
                        Elo {Math.round(t.elo_rating)} · {t.stadium ?? "—"}
                      </span>
                    </span>
                    {t.tpi !== null && (
                      <span className="text-right">
                        <span className="block text-lg font-black tabular-nums text-[#9db9ff]">{t.tpi}</span>
                        <span className="block text-[10px] font-semibold text-sub">TPI</span>
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            </Panel>
          ))}
          {grouped.length === 0 && (
            <div className="py-16 text-center text-sm text-sub">暂无球队数据</div>
          )}
        </div>
      )}
    </div>
  );
}
