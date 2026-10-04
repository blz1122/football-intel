"use client";
// 比赛详情页：比分头 + 实时胜率曲线 + 技术统计 + 事件时间线 + 射门地图 + 赛前预测
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Fragment, Suspense, useMemo } from "react";
import EChart, { CHART_COLORS, baseOption } from "@/components/charts/EChart";
import { Panel, StatusTag, TeamBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { CurvePoint, EventOut, ShotMap } from "@/lib/types";
import { useLiveSocket } from "@/lib/useLiveSocket";
import { usePolling } from "@/lib/usePolling";

function StatRow({ label, h, a }: { label: string; h: number | string; a: number | string }) {
  const hv = typeof h === "number" ? h : parseFloat(String(h)) || 0;
  const av = typeof a === "number" ? a : parseFloat(String(a)) || 0;
  const total = hv + av || 1;
  return (
    <div className="mb-3 grid grid-cols-[52px_1fr_84px_1fr_52px] items-center gap-2.5 text-xs tabular-nums">
      <span className="text-sub">{h}</span>
      <span className="relative h-1.5 overflow-hidden rounded bg-base2">
        <i className="absolute inset-y-0 right-0 bg-home" style={{ width: `${(hv / total) * 100}%` }} />
      </span>
      <span className="text-center font-semibold">{label}</span>
      <span className="relative h-1.5 overflow-hidden rounded bg-base2">
        <i className="absolute inset-y-0 left-0 bg-away" style={{ width: `${(av / total) * 100}%` }} />
      </span>
      <span className="text-right text-sub">{a}</span>
    </div>
  );
}

const EVENT_ICON: Record<string, string> = {
  goal: "⚽", yellow_card: "🟨", red_card: "🟥", substitution: "🔁",
};

function Timeline({ events, homeColor, awayColor }: { events: EventOut[]; homeColor: string; awayColor: string }) {
  if (!events.length) return <div className="py-8 text-center text-sm text-sub">暂无事件</div>;
  return (
    <div className="relative px-4 py-3">
      <div className="absolute inset-y-3 left-1/2 w-px bg-line" />
      {events.map((e, i) => (
        <div key={i} className={`flex items-center ${e.side === "home" ? "flex-row" : "flex-row-reverse"} mb-2.5`}>
          <div className={`flex w-1/2 items-center gap-2 ${e.side === "home" ? "justify-end pr-4" : "justify-start pl-4"}`}>
            {e.side === "away" && <span>{EVENT_ICON[e.type] ?? "•"}</span>}
            <div className={`text-right ${e.side === "away" ? "text-left" : ""}`}>
              <div className="text-xs font-bold">
                {e.player && (
                  e.player_id ? (
                    <Link href={`/player/?id=${e.player_id}`} className="hover:text-accent2">{e.player}</Link>
                  ) : e.player
                )}
                {e.related_player && (
                  <>
                    {" (换下 "}
                    {e.related_player_id ? (
                      <Link href={`/player/?id=${e.related_player_id}`} className="hover:text-accent2">{e.related_player}</Link>
                    ) : e.related_player}
                    {")"}
                  </>
                )}
              </div>
              <div className="text-[10.5px] text-sub">{e.detail ?? e.type}</div>
            </div>
            {e.side === "home" && <span>{EVENT_ICON[e.type] ?? "•"}</span>}
          </div>
          <span
            className="relative z-10 min-w-9 rounded-full border-2 px-1.5 py-0.5 text-center text-[10px] font-extrabold tabular-nums"
            style={{ borderColor: e.side === "home" ? homeColor : awayColor, background: "#0f1523" }}
          >
            {e.minute}'
          </span>
          <div className="w-1/2" />
        </div>
      ))}
    </div>
  );
}

function ShotMapChart({ map }: { map: ShotMap }) {
  const r = (xg: number) => 4 + xg * 26;
  return (
    <svg viewBox="0 0 640 300" className="w-full rounded-lg bg-[#0d3b2e]">
      <rect x="20" y="40" width="600" height="220" fill="none" stroke="#2f7d5f" strokeWidth="2" />
      <line x1="320" y1="40" x2="320" y2="260" stroke="#2f7d5f" strokeWidth="1.5" />
      <rect x="20" y="105" width="90" height="90" fill="none" stroke="#2f7d5f" />
      <rect x="530" y="105" width="90" height="90" fill="none" stroke="#2f7d5f" />
      <rect x="20" y="140" width="40" height="20" fill="none" stroke="#2f7d5f" />
      <rect x="580" y="140" width="40" height="20" fill="none" stroke="#2f7d5f" />
      {map.home.map((s, i) => (
        <circle key={`h${i}`} cx={s.x * 640} cy={s.y * 300} r={r(s.xg)}
          fill={s.goal ? "#ffd166" : "#4d8dff"} fillOpacity="0.55" stroke={s.goal ? "#ffd166" : "#4d8dff"} />
      ))}
      {map.away.map((s, i) => (
        <circle key={`a${i}`} cx={s.x * 640} cy={s.y * 300} r={r(s.xg)}
          fill={s.goal ? "#ffd166" : "#ff7a45"} fillOpacity="0.55" stroke={s.goal ? "#ffd166" : "#ff7a45"} />
      ))}
    </svg>
  );
}

function MonteCarloGrid({ matrix }: { matrix: Record<string, number> }) {
  const rows = 5, cols = 5;
  const grid: (number | undefined)[][] = Array.from({ length: rows }, () => Array(cols).fill(undefined));
  Object.entries(matrix).forEach(([k, v]) => {
    const [h, a] = k.split("-").map(Number);
    if (h < rows && a < cols) grid[h][a] = v;
  });
  const color = (p: number) => {
    const levels = ["#16264d", "#1e3a6e", "#2850a8", "#3566cf", "#4d8dff", "#7aa9ff"];
    return levels[Math.min(5, Math.floor((p * 100) / 4))];
  };
  return (
    <div className="grid text-center text-[11px]" style={{ gridTemplateColumns: `auto repeat(${cols}, 1fr)`, gap: 3 }}>
      <div />
      {Array.from({ length: cols }, (_, a) => (
        <div key={`h${a}`} className="flex items-center justify-center text-[11px] font-semibold text-sub">{a}</div>
      ))}
      {grid.map((row, h) => (
        <Fragment key={`r${h}`}>
          <div className="flex items-center justify-center text-[11px] font-semibold text-sub">{h}</div>
          {row.map((p, a) => (
            <div key={`${h}-${a}`} className="rounded-md px-1 py-2 font-bold tabular-nums text-[#dfe8ff]"
              style={{ background: p !== undefined ? color(p) : "#101728" }}>
              {p !== undefined && p >= 0.01 ? `${Math.round(p * 100)}%` : ""}
            </div>
          ))}
        </Fragment>
      ))}
    </div>
  );
}

function MatchPageInner() {
  const params = useSearchParams();
  const id = Number(params.get("id"));
  if (!Number.isFinite(id) || id <= 0) {
    return (
      <div className="py-24 text-center text-sm text-sub">
        缺少比赛 ID，请从比赛列表进入。<br />
        <Link href="/" className="mt-3 inline-block font-semibold text-accent2">← 返回 Dashboard</Link>
      </div>
    );
  }
  const { data } = usePolling(() => api.matchDetail(id), 20000);
  const { data: curve } = usePolling(() => api.winProbCurve(id), 15000);
  const { data: shots } = usePolling(() => api.shotMap(id), 20000);
  const { data: mc } = usePolling(() => api.monteCarlo(id), 60000);
  const { data: report } = usePolling(() => api.report(id), 20000);
  const { updates, connected } = useLiveSocket(false, id);

  // WebSocket 快照合并：分钟/比分/概率实时覆盖
  const m = useMemo(() => {
    if (!data) return null;
    const u = updates[id];
    if (!u) return data.match;
    return {
      ...data.match,
      status: u.status as typeof data.match.status,
      minute: u.minute,
      home_score: u.home_score,
      away_score: u.away_score,
      win_prob: u.win_prob,
      live_stats: u.stats
        ? ({ ...data.match.live_stats, ...u.stats } as typeof data.match.live_stats)
        : data.match.live_stats,
    };
  }, [data, updates, id]);
  const s = m?.live_stats ?? null;

  const curveOption = useMemo(() => {
    const pts = curve ?? [];
    return {
      ...baseOption,
      grid: { left: 44, right: 16, top: 20, bottom: 30 },
      xAxis: {
        type: "category" as const,
        data: pts.map((p) => `${p.minute}'`),
        axisLine: { lineStyle: { color: CHART_COLORS.axis } },
        axisLabel: { color: CHART_COLORS.label, interval: Math.max(Math.floor(pts.length / 9) - 1, 0) },
      },
      yAxis: {
        type: "value" as const, min: 0, max: 1,
        axisLabel: { color: CHART_COLORS.label, formatter: (v: number) => `${Math.round(v * 100)}%` },
        splitLine: { lineStyle: { color: CHART_COLORS.axis } },
      },
      legend: { data: ["主胜", "平局", "客胜"], textStyle: { color: CHART_COLORS.label }, top: 0, icon: "roundRect", itemWidth: 12 },
      series: (["p_home", "p_draw", "p_away"] as const).map((k, i) => ({
        name: ["主胜", "平局", "客胜"][i],
        type: "line" as const,
        smooth: true,
        showSymbol: false,
        data: pts.map((p) => p[k]),
        lineStyle: { width: 2, color: [CHART_COLORS.home, CHART_COLORS.draw, CHART_COLORS.away][i] },
        itemStyle: { color: [CHART_COLORS.home, CHART_COLORS.draw, CHART_COLORS.away][i] },
        areaStyle: i === 0 ? { opacity: 0.08, color: CHART_COLORS.home } : undefined,
        markPoint: i === 0 ? {
          symbolSize: 34,
          data: pts.filter((p) => p.trigger === "goal").map((p) => ({ name: "goal", coord: [`${p.minute}'`, p[k]], value: "⚽" })),
          label: { formatter: "⚽", fontSize: 12, color: CHART_COLORS.gold },
          itemStyle: { color: "transparent" },
        } : undefined,
      })),
    };
  }, [curve]);

  if (!data || !m) {
    return <div className="py-24 text-center text-sub">加载中…（确认后端 uvicorn 已启动）</div>;
  }

  const { events, prediction } = data;
  const live = m && (m.status === "live" || m.status === "halftime");

  return (
    <div>
      <Link href="/" className="mb-3 inline-block text-xs font-semibold text-sub hover:text-txt">← 返回 Dashboard</Link>

      {/* 比分头 */}
      <section className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-xl border border-line px-6 py-6"
        style={{ background: "linear-gradient(180deg,#131d33,#101728)" }}>
        <Link href={`/team/?id=${m.home_team.id}`} className="group flex flex-col items-center gap-2" title="查看球队详情">
          <span className="flex h-14 w-14 items-center justify-center rounded-full text-base font-extrabold text-white" style={{ background: m.home_team.color }}>
            {m.home_team.short_name}
          </span>
          <div className="text-[15px] font-extrabold transition-colors group-hover:text-accent2">{m.home_team.name}</div>
          <div className="text-[11.5px] text-sub">Elo {Math.round(m.home_team.elo_rating)} · TPI {m.home_team.tpi ?? "—"} · 主场</div>
        </Link>
        <div className="text-center">
          <div className="mb-1.5 text-xs text-sub">{m.league.name} · {m.round}</div>
          <div className="text-4xl font-black tabular-nums tracking-widest">
            {m.status === "scheduled" ? "vs" : `${m.home_score} - ${m.away_score}`}
          </div>
          <div className="mt-2 flex justify-center"><StatusTag status={m.status} period={m.period} /></div>
        </div>
        <Link href={`/team/?id=${m.away_team.id}`} className="group flex flex-col items-center gap-2" title="查看球队详情">
          <span className="flex h-14 w-14 items-center justify-center rounded-full text-base font-extrabold text-white" style={{ background: m.away_team.color }}>
            {m.away_team.short_name}
          </span>
          <div className="text-[15px] font-extrabold transition-colors group-hover:text-accent2">{m.away_team.name}</div>
          <div className="text-[11.5px] text-sub">Elo {Math.round(m.away_team.elo_rating)} · TPI {m.away_team.tpi ?? "—"} · 客场</div>
        </Link>
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex flex-col gap-4">
          {/* 胜率曲线 */}
          <Panel title="📈 实时胜率变化曲线" tag={live ? `LIVE ${m.minute}'` : m.status === "finished" ? "全场" : "未开始"}>
            {curve && curve.length > 0 ? (
              <div className="px-3 pb-2"><EChart option={curveOption} height={250} /></div>
            ) : (
              <div className="px-4 py-14 text-center text-sm text-sub">
                {m.status === "scheduled" ? "比赛开始后生成实时胜率曲线" : "曲线加载中…"}
              </div>
            )}
            {curve && curve.length > 0 && (
              <div className="flex justify-between border-t border-line px-4 py-2.5 text-xs text-sub">
                <span>当前主胜 <b className="text-home">{Math.round(curve[curve.length - 1].p_home * 100)}%</b></span>
                <span>平 <b>{Math.round(curve[curve.length - 1].p_draw * 100)}%</b></span>
                <span>客胜 <b className="text-away">{Math.round(curve[curve.length - 1].p_away * 100)}%</b></span>
              </div>
            )}
          </Panel>

          {/* 技术统计 */}
          <Panel title="📊 技术统计" tag={s ? `实时 ${s.minute}'` : "未开始"}>
            <div className="px-4 py-4">
              {s ? (
                <>
                  <StatRow label="控球率" h={`${s.possession_home}%`} a={`${100 - s.possession_home}%`} />
                  <StatRow label="射门" h={s.shots_home} a={s.shots_away} />
                  <StatRow label="射正" h={s.shots_on_target_home} a={s.shots_on_target_away} />
                  <StatRow label="xG" h={s.xg_home.toFixed(2)} a={s.xg_away.toFixed(2)} />
                  <StatRow label="危险进攻" h={s.dangerous_home} a={s.dangerous_away} />
                  <StatRow label="角球" h={s.corners_home} a={s.corners_away} />
                  <StatRow label="犯规" h={s.fouls_home} a={s.fouls_away} />
                  <StatRow label="红黄牌" h={`${s.yellow_home}🟨${s.red_home}🟥`} a={`${s.yellow_away}🟨${s.red_away}🟥`} />
                </>
              ) : (
                <div className="py-8 text-center text-sm text-sub">比赛开始后展示实时统计</div>
              )}
            </div>
          </Panel>

          {/* 射门地图 */}
          <Panel title="🎯 射门地图（xG）" tag="圆大小 ∝ xG">
            <div className="px-4 py-4">
              {shots && (shots.home.length || shots.away.length) ? (
                <>
                  <ShotMapChart map={shots} />
                  <div className="mt-2.5 flex gap-4 text-xs text-sub">
                    <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#4d8dff" }} />{m.home_team.short_name} 射门</span>
                    <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#ff7a45" }} />{m.away_team.short_name} 射门</span>
                    <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#ffd166" }} />进球</span>
                  </div>
                </>
              ) : (
                <div className="py-8 text-center text-sm text-sub">比赛开始后生成射门数据</div>
              )}
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          {/* 赛前预测 */}
          {prediction && (
            <Panel title="🤖 AI 赛前预测" tag={prediction.model_version}>
              <div className="px-4 py-4">
                <div className="mb-3 flex justify-between text-center text-sm">
                  <div><div className="text-xl font-extrabold text-home">{Math.round(prediction.p_home * 100)}%</div><div className="text-[11px] text-sub">主胜</div></div>
                  <div><div className="text-xl font-extrabold text-sub">{Math.round(prediction.p_draw * 100)}%</div><div className="text-[11px] text-sub">平局</div></div>
                  <div><div className="text-xl font-extrabold text-away">{Math.round(prediction.p_away * 100)}%</div><div className="text-[11px] text-sub">客胜</div></div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-sub">
                  <div className="rounded-lg bg-panel2 px-3 py-2">预期比分 <b className="float-right text-txt">{prediction.expected_score}</b></div>
                  <div className="rounded-lg bg-panel2 px-3 py-2">置信度 <b className="float-right text-txt">{Math.round(prediction.confidence * 100)}%</b></div>
                  <div className="rounded-lg bg-panel2 px-3 py-2">λ 主队 <b className="float-right text-txt">{prediction.lambda_home}</b></div>
                  <div className="rounded-lg bg-panel2 px-3 py-2">λ 客队 <b className="float-right text-txt">{prediction.lambda_away}</b></div>
                </div>
              </div>
            </Panel>
          )}

          {/* Monte Carlo 模拟 */}
          {mc && (
            <Panel title="🎲 Monte Carlo 模拟" tag={`${mc.simulations.toLocaleString()} 次 · ${mc.model_version}`}>
              <div className="px-4 py-4">
                <div className="mb-3 text-xs text-sub">比分概率矩阵（行=主队进球，列=客队进球，TOP5 比分: {Object.entries(mc.score_matrix).slice(0, 5).map(([s, p]) => `${s} ${Math.round(p * 100)}%`).join(" / ")}）</div>
                <MonteCarloGrid matrix={mc.score_matrix} />
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-panel2 px-2 py-2">大2.5球 <b className="ml-1 text-txt">{Math.round((mc.over_under["2.5"] ?? 0) * 100)}%</b></div>
                  <div className="rounded-lg bg-panel2 px-2 py-2">双方进球 <b className="ml-1 text-txt">{Math.round(mc.btts * 100)}%</b></div>
                  <div className="rounded-lg bg-panel2 px-2 py-2">净胜2球+ <b className="ml-1 text-txt">—</b></div>
                </div>
              </div>
            </Panel>
          )}

          {/* 球队能力雷达 */}
          {m.home_team.radar && m.away_team.radar && (
            <Panel title="🕸️ 球队能力对比（TPI 分项）" tag={`TPI ${m.home_team.tpi} : ${m.away_team.tpi}`}>
              <div className="px-2 pb-2">
                <EChart height={230} option={{
                  ...baseOption,
                  grid: undefined,
                  radar: {
                    indicator: [
                      { name: "攻击", max: 100 }, { name: "防守", max: 100 },
                      { name: "控球", max: 100 }, { name: "压迫", max: 100 },
                      { name: "效率", max: 100 }, { name: "状态", max: 100 },
                    ],
                    radius: "62%", center: ["50%", "52%"],
                    axisName: { color: CHART_COLORS.label, fontSize: 11 },
                    splitLine: { lineStyle: { color: CHART_COLORS.axis } },
                    splitArea: { show: false },
                    axisLine: { lineStyle: { color: CHART_COLORS.axis } },
                  },
                  legend: { data: [m.home_team.name, m.away_team.name], textStyle: { color: CHART_COLORS.label }, bottom: 0, icon: "roundRect", itemWidth: 12 },
                  series: [{
                    type: "radar" as const,
                    data: [
                      { value: [m.home_team.radar.attack, m.home_team.radar.defense, m.home_team.radar.possession, m.home_team.radar.pressing, m.home_team.radar.efficiency, m.home_team.radar.form], name: m.home_team.name, lineStyle: { color: "#4d8dff", width: 2 }, itemStyle: { color: "#4d8dff" }, areaStyle: { opacity: 0.18, color: "#4d8dff" } },
                      { value: [m.away_team.radar.attack, m.away_team.radar.defense, m.away_team.radar.possession, m.away_team.radar.pressing, m.away_team.radar.efficiency, m.away_team.radar.form], name: m.away_team.name, lineStyle: { color: "#ff7a45", width: 2 }, itemStyle: { color: "#ff7a45" }, areaStyle: { opacity: 0.15, color: "#ff7a45" } },
                    ],
                  }],
                }} />
              </div>
            </Panel>
          )}

          {/* 事件时间线 */}
          <Panel title="⏱️ 事件时间线">
            <Timeline events={events} homeColor={m.home_team.color} awayColor={m.away_team.color} />
          </Panel>

          {/* AI 报告：数据驱动模板引擎，可配置 LLM 生成 */}
          <Panel
            title="📝 AI 比赛报告"
            tag={
              report
                ? report.generated_by === "llm"
                  ? "LLM 生成"
                  : "数据驱动模板引擎"
                : "生成中…"
            }
          >
            {report ? (
              <div className="space-y-3 px-4 py-4 text-[13px] leading-relaxed text-[#c6d2ec]">
                {report.sections.map((sec, i) => (
                  <p key={i}>
                    <b className="text-txt">{sec.icon} {sec.title}：</b>
                    {sec.body}
                  </p>
                ))}
              </div>
            ) : (
              <div className="px-4 py-8 text-center text-sm text-sub">报告生成中…</div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

export default function MatchPage() {
  return (
    <Suspense fallback={
      <div className="grid min-h-[60vh] place-items-center text-sm text-sub">加载比赛详情…</div>
    }>
      <MatchPageInner />
    </Suspense>
  );
}
