"use client";
// 球员 Profile：AI 评分 / 赛季数据 / 所属球队
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const POS_CN: Record<string, string> = { GK: "门将", DF: "后卫", MF: "中场", FW: "前锋" };

function PlayerPageInner() {
  const params = useSearchParams();
  const id = Number(params.get("id"));
  const { data: p, error } = usePolling(() => api.playerProfile(id), 60000);

  if (!p) {
    return <div className="py-24 text-center text-sub">{error ?? "加载中…"}</div>;
  }

  const s = p.season_stats;
  const ratingColor =
    p.ai_rating >= 8.5 ? "#4ade80" : p.ai_rating >= 7.5 ? "#9db9ff" : p.ai_rating >= 6.5 ? "#f5b342" : "#8b98b8";

  // ESPN 提供的真实赛季产出（没有 xG/xA/传球等细项，用实际可得的字段）
  const stats = [
    { l: "出场", v: s.appearances },
    { l: "进球", v: s.goals },
    { l: "助攻", v: s.assists },
    { l: "射门", v: s.shots },
    { l: "射正", v: s.shots_on_target },
    { l: "黄牌", v: s.yellow_cards },
    { l: "红牌", v: s.red_cards },
    { l: "扑救", v: s.saves },
    { l: "失球", v: s.goals_conceded },
  ];

  return (
    <div>
      <div className="mb-3 flex gap-4 text-xs font-semibold text-sub">
        <Link href="/players" className="hover:text-txt">← 返回球员列表</Link>
        <Link href={`/team/?id=${p.team.id}`} className="hover:text-txt">← 返回 {p.team.name}</Link>
      </div>

      <section className="flex items-center gap-6 rounded-xl border border-line px-6 py-6"
        style={{ background: "linear-gradient(180deg,#131d33,#101728)" }}>
        <span className="flex h-20 w-20 items-center justify-center rounded-full text-2xl font-black text-white"
          style={{ background: p.team.color }}>{p.number || POS_CN[p.position]}</span>
        <div className="flex-1">
          <h1 className="text-2xl font-black">
            {p.name}
            {p.name_en && p.name_en !== p.name && (
              <span className="ml-3 text-sm font-semibold text-sub">{p.name_en}</span>
            )}
          </h1>
          <div className="mt-1 text-sm text-sub">
            {POS_CN[p.position]}{p.age ? ` · ${p.age} 岁` : ""} · {p.team.name}
          </div>
        </div>
        <div className="text-center">
          <div className="text-5xl font-black tabular-nums" style={{ color: ratingColor }}>
            {p.ai_rating.toFixed(1)}
          </div>
          <div className="mt-1 text-xs font-bold text-sub">AI PLAYER RATING</div>
        </div>
      </section>

      <div className="mt-4">
        <Panel title="📅 赛季数据" tag="2026/27">
          <div className="grid grid-cols-3 gap-2 px-4 py-4 text-center sm:grid-cols-5 lg:grid-cols-9">
            {stats.map((x) => (
              <div key={x.l} className="rounded-lg bg-panel2 px-2 py-3">
                <div className="text-lg font-extrabold tabular-nums">{x.v ?? "—"}</div>
                <div className="mt-0.5 text-[11px] text-sub">{x.l}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

export default function PlayerPage() {
  return (
    <Suspense fallback={
      <div className="grid min-h-[60vh] place-items-center text-sm text-sub">加载球员详情…</div>
    }>
      <PlayerPageInner />
    </Suspense>
  );
}
