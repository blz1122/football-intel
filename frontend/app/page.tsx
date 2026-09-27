"use client";
// Dashboard 首页：KPI + 状态分组比赛列表 + 联赛筛选 + AI 预测排行/热门赛事
import { useMemo, useState } from "react";
import MatchRow from "@/components/MatchRow";
import { Panel } from "@/components/ui";
import { api } from "@/lib/api";
import type { MatchListItem } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

const TABS = [
  { key: "live", label: "进行中" },
  { key: "scheduled", label: "即将开始" },
  { key: "all", label: "今日全部" },
  { key: "finished", label: "已结束" },
] as const;

function groupOf(m: MatchListItem) {
  if (m.status === "live" || m.status === "halftime") return "live";
  if (m.status === "finished") return "finished";
  return "scheduled";
}

export default function Dashboard() {
  const { data: matches } = usePolling(() => api.matches(), 10000);
  const { data: kpis } = usePolling(() => api.kpis(), 30000);
  const { data: top } = usePolling(() => api.topPredictions(), 30000);
  const { data: leagues } = usePolling(() => api.leagues(), 300000);

  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("live");
  const [league, setLeague] = useState<number | "all">("all");

  const filtered = useMemo(() => {
    let list = matches ?? [];
    if (league !== "all") list = list.filter((m) => m.league.id === league);
    if (tab === "live") list = list.filter((m) => groupOf(m) === "live");
    if (tab === "scheduled") list = list.filter((m) => groupOf(m) === "scheduled");
    if (tab === "finished") list = list.filter((m) => groupOf(m) === "finished");
    return list;
  }, [matches, tab, league]);

  const kpiCards = [
    { l: "今日比赛", v: kpis?.total_today ?? "—", t: "5 大联赛 · 实时" },
    { l: "AI 预测准确率 (7日)", v: kpis ? `${kpis.accuracy_7d}%` : "—", t: "胜平负方向命中" },
    { l: "模型 Brier Score", v: kpis?.brier_score ?? "—", t: "越低越好 · 优于随机 0.333" },
    { l: "进行中", v: kpis?.live_now ?? "—", t: "10s 定时刷新" },
  ];

  return (
    <div>
      {/* KPI 行 */}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {kpiCards.map((k) => (
          <div key={k.l} className="rounded-xl border border-line bg-panel px-4 py-3.5">
            <div className="mb-1.5 text-xs text-sub">{k.l}</div>
            <div className="text-2xl font-extrabold tabular-nums">{k.v}</div>
            <div className="mt-1 text-[11px] font-semibold text-sub">{k.t}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        {/* 比赛中心 */}
        <Panel title="⚡ 实时足球数据中心" tag="10s 自动刷新">
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {TABS.map((t) => {
              const count =
                t.key === "all"
                  ? (matches ?? []).length
                  : (matches ?? []).filter((m) => groupOf(m) === t.key).length;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`rounded-lg border px-4 py-1.5 text-xs font-semibold transition-colors ${
                    tab === t.key
                      ? "border-[#28437f] bg-[#16264d] text-[#9db9ff]"
                      : "border-transparent bg-panel2 text-sub hover:text-txt"
                  }`}
                >
                  {t.label} ({count})
                </button>
              );
            })}
            <select
              className="ml-auto rounded-lg border border-line2 bg-panel2 px-3 py-1.5 text-xs font-semibold text-sub outline-none"
              value={league}
              onChange={(e) => setLeague(e.target.value === "all" ? "all" : Number(e.target.value))}
            >
              <option value="all">全部联赛</option>
              {(leagues ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-3">
            {filtered.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-sub">该筛选条件下暂无比赛</div>
            ) : (
              filtered.map((m) => <MatchRow key={m.id} m={m} />)
            )}
          </div>
        </Panel>

        {/* 右栏 */}
        <div className="flex flex-col gap-4">
          <Panel title="🤖 AI 预测排行" tag="今日置信度 TOP">
            <ul>
              {(top ?? []).map((p, i) => (
                <li key={p.match_id} className="flex items-center gap-2.5 border-b border-line px-4 py-2.5 text-[13px] last:border-b-0">
                  <span className={`w-5 text-center font-extrabold ${i < 3 ? "text-gold" : "text-sub"}`}>
                    {i + 1}
                  </span>
                  <span className="flex-1 truncate font-semibold">
                    {p.title} · {p.pick}
                  </span>
                  <span className="font-extrabold tabular-nums text-[#9db9ff]">
                    {Math.round(p.probability * 100)}%
                  </span>
                </li>
              ))}
              {top?.length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-sub">今日暂无未开赛比赛</li>
              )}
            </ul>
          </Panel>

          <Panel title="🔥 热门赛事" tag="Elo 实力榜">
            <ul>
              {(matches ?? [])
                .filter((m) => m.is_hot)
                .slice(0, 6)
                .map((m) => (
                  <li key={m.id} className="flex items-center gap-2.5 border-b border-line px-4 py-2.5 text-[13px] last:border-b-0">
                    <span className="w-5 text-center">🔥</span>
                    <span className="flex-1 truncate font-semibold">
                      {m.home_team.short_name} vs {m.away_team.short_name}
                    </span>
                    <span className="text-sub tabular-nums">
                      {new Date(m.kickoff_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </li>
                ))}
              {(matches ?? []).filter((m) => m.is_hot).length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-sub">暂无焦点战</li>
              )}
            </ul>
          </Panel>

          <Panel title="📡 数据链路">
            <div className="space-y-2 px-4 py-4 text-xs leading-relaxed text-sub">
              <div>模拟数据引擎 <span className="float-right font-bold text-[#22c58b]">● 运行中</span></div>
              <div>Elo-Poisson 预测模型 v0.1 <span className="float-right font-bold text-[#22c58b]">● 已加载</span></div>
              <div>REST 轮询刷新 10s <span className="float-right font-bold text-[#f5b342]">● Phase 4 升级 WebSocket</span></div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
