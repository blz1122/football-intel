"use client";
// 球队 Profile：TPI 评分 / 能力雷达 / 近10场走势 / 赛季数据 / 阵容 AI 评分表
import Link from "next/link";
import { useParams } from "next/navigation";
import EChart, { CHART_COLORS, baseOption } from "@/components/charts/EChart";
import { Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const POS_CN: Record<string, string> = { GK: "门将", DF: "后卫", MF: "中场", FW: "前锋" };
const FORM_CN: Record<string, string> = { W: "胜", D: "平", L: "负" };
const FORM_COLOR: Record<string, string> = {
  W: "bg-[#1d3a2a] text-[#4ade80] border-[#2c5a40]",
  D: "bg-[#2a2a1d] text-[#eab308] border-[#4d4a20]",
  L: "bg-[#3a1d24] text-[#f87171] border-[#5a2c36]",
};

export default function TeamPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data: t, error } = usePolling(() => api.teamProfile(id), 60000);

  if (!t) {
    return <div className="py-24 text-center text-sub">{error ?? "加载中…"}</div>;
  }

  const season = t.breakdown.season ?? {};
  const radarOption = {
    ...baseOption,
    grid: undefined,
    radar: {
      indicator: [
        { name: "攻击", max: 100 }, { name: "防守", max: 100 }, { name: "控球", max: 100 },
        { name: "压迫", max: 100 }, { name: "效率", max: 100 }, { name: "状态", max: 100 },
      ],
      radius: "65%", center: ["50%", "52%"],
      axisName: { color: CHART_COLORS.label, fontSize: 12 },
      splitLine: { lineStyle: { color: CHART_COLORS.axis } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: CHART_COLORS.axis } },
    },
    series: [{
      type: "radar" as const,
      data: [{
        value: [t.radar.attack, t.radar.defense, t.radar.possession, t.radar.pressing, t.radar.efficiency, t.radar.form],
        name: t.name,
        lineStyle: { color: "#4d8dff", width: 2 },
        areaStyle: { opacity: 0.2, color: "#4d8dff" },
        itemStyle: { color: "#4d8dff" },
      }],
    }],
  };

  const tpiBars = [
    { l: "攻击力", v: t.radar.attack, c: "#ff7a45" },
    { l: "防守力", v: t.radar.defense, c: "#4d8dff" },
    { l: "近期状态", v: t.radar.form, c: "#f5b342" },
    { l: "控球", v: t.radar.possession, c: "#38bdf8" },
    { l: "压迫强度", v: t.radar.pressing, c: "#a78bfa" },
    { l: "射门效率", v: t.radar.efficiency, c: "#22c58b" },
  ];

  return (
    <div>
      <div className="mb-3 flex gap-4 text-xs font-semibold text-sub">
        <Link href="/teams" className="hover:text-txt">← 返回球队列表</Link>
        <Link href="/" className="hover:text-txt">← 返回 Dashboard</Link>
      </div>

      {/* 头部 */}
      <section className="flex items-center gap-6 rounded-xl border border-line px-6 py-6"
        style={{ background: "linear-gradient(180deg,#131d33,#101728)" }}>
        <span className="flex h-20 w-20 items-center justify-center rounded-full text-lg font-black text-white"
          style={{ background: t.color }}>{t.short_name}</span>
        <div className="flex-1">
          <h1 className="text-2xl font-black">{t.name} <span className="text-sm font-semibold text-sub">{t.name_en}</span></h1>
          <div className="mt-1 text-sm text-sub">
            {t.league.name} · {t.stadium} · Elo {Math.round(t.elo_rating)}
          </div>
          <div className="mt-3 flex gap-1.5">
            {(t.breakdown.form_last10 ?? []).map((f, i) => (
              <span key={i} className={`flex h-6 w-6 items-center justify-center rounded border text-[11px] font-extrabold ${FORM_COLOR[f]}`}>
                {FORM_CN[f]}
              </span>
            ))}
          </div>
        </div>
        <div className="text-center">
          <div className="text-5xl font-black tabular-nums" style={{ color: "#9db9ff" }}>{t.tpi}</div>
          <div className="mt-1 text-xs font-bold text-sub">TEAM POWER INDEX</div>
        </div>
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Panel title="🕸️ 球队能力雷达">
            <div className="px-2 pb-2"><EChart option={radarOption} height={260} /></div>
          </Panel>

          <Panel title="📊 TPI 分项拆解" tag={`综合 ${t.tpi}`}>
            <div className="space-y-3 px-4 py-4">
              {tpiBars.map((b) => (
                <div key={b.l}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-sub">{b.l}</span>
                    <span className="font-bold tabular-nums">{b.v}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded bg-base2">
                    <i className="block h-full rounded" style={{ width: `${b.v}%`, background: b.c }} />
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          <Panel title="📅 赛季数据" tag="2026/27">
            <div className="grid grid-cols-3 gap-2 px-4 py-4 text-center">
              {[
                { l: "进球", v: season.goals_for },
                { l: "失球", v: season.goals_against },
                { l: "xG", v: season.xg },
                { l: "xGA", v: season.xga },
                { l: "胜场(近10×2)", v: season.wins },
                { l: "样本场次", v: season.matches },
              ].map((s) => (
                <div key={s.l} className="rounded-lg bg-panel2 px-2 py-3">
                  <div className="text-lg font-extrabold tabular-nums">{s.v ?? "—"}</div>
                  <div className="mt-0.5 text-[11px] text-sub">{s.l}</div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="👥 阵容 · AI Player Rating" tag={`${t.squad.length} 人`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-line text-sub">
                  <tr>
                    <th className="px-4 py-2 font-semibold">球员</th>
                    <th className="px-2 py-2 font-semibold">位置</th>
                    <th className="px-2 py-2 font-semibold">号码</th>
                    <th className="px-2 py-2 font-semibold">进球/助攻</th>
                    <th className="px-2 py-2 font-semibold">xG+xA</th>
                    <th className="px-2 py-2 text-right font-semibold">AI 评分</th>
                  </tr>
                </thead>
                <tbody>
                  {t.squad.map((p) => (
                    <tr key={p.id} className="border-b border-line last:border-b-0 hover:bg-panel2">
                      <td className="px-4 py-2.5">
                        <Link href={`/player/${p.id}`} className="font-bold hover:text-accent2">
                          {p.name}
                        </Link>
                        <span className="ml-2 text-[10px] text-sub">{p.name_en}</span>
                      </td>
                      <td className="px-2 py-2.5 text-sub">{POS_CN[p.position]}</td>
                      <td className="px-2 py-2.5 tabular-nums text-sub">{p.number}</td>
                      <td className="px-2 py-2.5 tabular-nums">
                        {p.season_stats.goals ?? 0} / {p.season_stats.assists ?? 0}
                      </td>
                      <td className="px-2 py-2.5 tabular-nums text-sub">
                        {((p.season_stats.xg ?? 0) + (p.season_stats.xa ?? 0)).toFixed(1)}
                      </td>
                      <td className="px-2 py-2.5 text-right">
                        <span className={`rounded px-2 py-0.5 font-extrabold tabular-nums ${p.ai_rating >= 8 ? "bg-[#1d3a2a] text-[#4ade80]" : p.ai_rating >= 7 ? "bg-[#16264d] text-[#9db9ff]" : "bg-panel2 text-sub"}`}>
                          {p.ai_rating.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
