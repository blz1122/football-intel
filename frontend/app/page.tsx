"use client";
// Dashboard 首页：KPI + 状态分组比赛列表 + 联赛筛选 + AI 预测排行/热门赛事
// Phase 4: WebSocket 5s 实时推送 + 30s REST 兜底轮询
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import MatchRow from "@/components/MatchRow";
import DataSource, { useDataSource } from "@/components/DataSource";
import { MatchRowSkeleton, Panel, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { LeagueInfo, MatchListItem } from "@/lib/types";
import { useLiveSocket } from "@/lib/useLiveSocket";
import { usePolling } from "@/lib/usePolling";

const TABS = [
  { key: "live", label: "进行中" },
  { key: "scheduled", label: "即将开始" },
  { key: "all", label: "今日全部" },
  { key: "finished", label: "已结束" },
] as const;

// 55 个赛事源下"今日全部"可达上百场，分页渲染避免首屏卡顿
const PAGE_SIZE = 40;

function groupOf(m: MatchListItem) {
  if (m.status === "live" || m.status === "halftime") return "live";
  if (m.status === "finished") return "finished";
  return "scheduled";
}

export default function Dashboard() {
  const { data: matches, loading } = usePolling(() => api.matches(), 30000);
  const { data: kpis } = usePolling(() => api.kpis(), 30000);
  const { data: top } = usePolling(() => api.topPredictions(), 30000);
  const { data: leagues } = usePolling(() => api.leagues(), 300000);
  const { updates, liveCount, connected, lastMsgAt, lastUpdateAt, tick } = useLiveSocket(true);
  const ds = useDataSource();

  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("live");
  const [league, setLeague] = useState<number | "all">("all");
  const [compType, setCompType] = useState<"all" | "continental" | "national" | "domestic">("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [autoPicked, setAutoPicked] = useState(false);

  // 非比赛日（或数据源暂无进行中比赛）时自动切到有内容的分组，避免空白页
  useEffect(() => {
    if (autoPicked || !matches) return;
    const counts = {
      live: matches.filter((m) => groupOf(m) === "live").length,
      scheduled: matches.filter((m) => groupOf(m) === "scheduled").length,
      finished: matches.filter((m) => groupOf(m) === "finished").length,
    };
    if (counts.live > 0) {
      setAutoPicked(true);
      return;
    }
    setTab(counts.scheduled > 0 ? "scheduled" : counts.finished > 0 ? "finished" : "all");
    setAutoPicked(true);
  }, [matches, autoPicked]);

  // WebSocket 快照合并：分钟/比分/胜率/统计以 WS 推送为准
  const liveMatches = useMemo(() => {
    const base = matches ?? [];
    if (!Object.keys(updates).length) return base;
    return base.map((m) => {
      const u = updates[m.id];
      if (!u) return m;
      return {
        ...m,
        status: u.status as MatchListItem["status"],
        minute: u.minute,
        home_score: u.home_score,
        away_score: u.away_score,
        win_prob: u.win_prob,
        live_stats: u.stats
          ? ({ ...m.live_stats, ...u.stats } as MatchListItem["live_stats"])
          : m.live_stats,
      };
    });
  }, [matches, updates]);

  // 联赛按赛事类型（洲际/国家队/国内）分组，供筛选器使用
  const leagueById = useMemo(() => {
    const m = new Map<number, LeagueInfo>();
    (leagues ?? []).forEach((l) => m.set(l.id, l));
    return m;
  }, [leagues]);

  const visibleLeagues = useMemo(() => {
    const list = (leagues ?? []).filter(
      (l) => compType === "all" || l.competition_type === compType,
    );
    // 选中的联赛若被类型过滤掉，自动回退到全部
    return list;
  }, [leagues, compType]);

  const COMP_TABS = [
    { key: "all" as const, label: "全部赛事" },
    { key: "continental" as const, label: "洲际赛事" },
    { key: "national" as const, label: "国家队" },
    { key: "domestic" as const, label: "各国联赛" },
  ];

  const filtered = useMemo(() => {
    let list = liveMatches;
    if (league !== "all") list = list.filter((m) => m.league.id === league);
    else if (compType !== "all") {
      list = list.filter((m) => leagueById.get(m.league.id)?.competition_type === compType);
    }
    if (tab === "live") list = list.filter((m) => groupOf(m) === "live");
    if (tab === "scheduled") list = list.filter((m) => groupOf(m) === "scheduled");
    if (tab === "finished") list = list.filter((m) => groupOf(m) === "finished");
    if (tab === "finished") list = [...list].sort(
      (a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime(),
    );
    return list;
  }, [liveMatches, tab, league, compType, leagueById]);

  // 切换标签/筛选时回到第一页
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [tab, league, compType]);

  // tick 每秒自增，保证下面的"X 秒前"会自己走
  const ago = (t: number | null) =>
    t == null ? null : Math.max(0, Math.round((Date.now() - t) / 1000));
  const beatAgo = ago(lastMsgAt);
  const updAgo = ago(lastUpdateAt);
  void tick;
  // 心跳超过 45 秒没来 = 链路大概率断了（服务端 20s 一帧）
  const linkStale = connected && beatAgo != null && beatAgo > 45;
  const linkOk = connected && !linkStale;

  // 下一场开赛时间：没有直播时给用户一个"什么时候会动"的确定预期
  const nextKick = useMemo(() => {
    const now = Date.now();
    const ts = (matches ?? [])
      .filter((m) => m.status === "scheduled")
      .map((m) => new Date(m.kickoff_at).getTime())
      .filter((t) => t > now);
    return ts.length ? Math.min(...ts) : null;
  }, [matches, tick]);
  const cdSec = nextKick == null ? null : Math.max(0, Math.round((nextKick - Date.now()) / 1000));
  const fmtCd = (s: number) =>
    s >= 3600
      ? `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`
      : s >= 60
        ? `${Math.floor(s / 60)} 分 ${s % 60} 秒`
        : `${s} 秒`;

  const kpiCards = [
    { l: "今日比赛", v: kpis?.total_today ?? "—", t: `覆盖 ${leagues?.length ?? 0} 个赛事 · 实时` },
    { l: "AI 预测准确率 (7日)", v: kpis ? `${kpis.accuracy_7d}%` : "—", t: "胜平负方向命中" },
    { l: "模型 Brier Score", v: kpis?.brier_score ?? "—", t: "越低越好 · 优于随机 0.333" },
    {
      l: "进行中",
      v: liveCount ?? kpis?.live_now ?? "—",
      t: linkOk
        ? `实时推送中 · 心跳 ${beatAgo ?? "—"} 秒前`
        : connected
          ? "连接中，等待首帧…"
          : "REST 轮询兜底",
    },
  ];

  return (
    <div className="page-in">
      {/* KPI 行 */}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {kpiCards.map((k, i) => (
          <div
            key={k.l}
            className="rise-in rounded-xl border border-line bg-panel px-4 py-3.5 transition-colors hover:border-[#28437f]"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="mb-1.5 text-xs text-sub">{k.l}</div>
            <div className="text-2xl font-extrabold tabular-nums">{k.v}</div>
            <div className="mt-1 text-[11px] font-semibold text-sub">{k.t}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        {/* 比赛中心 */}
        <Panel
          title="⚡ 实时足球数据中心"
          tag={linkOk ? `实时推送 · 心跳 ${beatAgo ?? "—"}s` : connected ? "连接中…" : "REST 轮询"}
          dot={linkOk ? "#22c58b" : connected ? "#f5b342" : "#ff6b7a"}
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2 text-[11px] text-sub">
            <span className={`font-bold ${(liveCount ?? 0) > 0 ? "text-[#22c58b]" : "text-sub"}`}>
              {liveCount == null ? "统计中…" : liveCount > 0 ? `● ${liveCount} 场进行中` : "○ 当前无进行中比赛"}
            </span>
            <span>
              比分更新 {updAgo == null ? "—" : updAgo < 60 ? `${updAgo} 秒前` : `${Math.floor(updAgo / 60)} 分钟前`}
            </span>
            <span>
              链路心跳 {beatAgo == null ? "—" : `${beatAgo} 秒前`}
            </span>
            {liveCount === 0 && (
              <span className="font-bold text-[#9db9ff]">
                {nextKick == null
                  ? "● 暂无待开赛赛事"
                  : cdSec != null && cdSec < 900
                    ? `● 下一场 ${fmtCd(cdSec)}后开赛，届时自动进入实时推送`
                    : `● 下一场 ${new Date(nextKick).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })} 开赛`}
              </span>
            )}
            {linkStale && (
              <span className="font-bold text-[#ff6b7a]">● 心跳超时，正在重连…</span>
            )}
            <span className="ml-auto">后端每 20 秒刷一次进行中赛事 · 全量赛程 5 分钟</span>
          </div>
          <div id="scheduled" className="flex scroll-mt-20 flex-wrap gap-1.5 px-4 pt-3">
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
            <div className="ml-auto flex items-center gap-2">
              <div className="flex overflow-hidden rounded-lg border border-line2">
                {COMP_TABS.map((c) => (
                  <button
                    key={c.key}
                    onClick={() => {
                      setCompType(c.key);
                      setLeague("all");
                    }}
                    className={`px-2.5 py-1.5 text-[11px] font-bold transition ${
                      compType === c.key
                        ? "bg-[#28437f] text-[#9db9ff]"
                        : "bg-panel2 text-sub hover:text-txt"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              <select
                className="max-w-[190px] rounded-lg border border-line2 bg-panel2 px-3 py-1.5 text-xs font-semibold text-sub outline-none"
                value={league}
                onChange={(e) => {
                  setLeague(e.target.value === "all" ? "all" : Number(e.target.value));
                  const lg = (leagues ?? []).find(
                    (l) => l.id === Number(e.target.value),
                  );
                  if (lg) setCompType(lg.competition_type);
                }}
              >
                <option value="all">全部联赛（{visibleLeagues.length}）</option>
                {visibleLeagues.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                    {l.match_count > 0 ? ` (${l.match_count})` : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-3">
            {loading ? (
              <>
                {Array.from({ length: 6 }, (_, i) => (
                  <MatchRowSkeleton key={i} />
                ))}
              </>
            ) : filtered.length === 0 ? (
              <div className="px-4 py-12 text-center">
                <div className="mb-2 text-2xl opacity-40">🕳️</div>
                <div className="text-sm text-sub">
                  {tab === "live"
                    ? "当前没有进行中的比赛（真实数据源，未编造比赛）"
                    : "该筛选条件下暂无比赛"}
                </div>
                {tab === "live" && (
                  <div className="mt-2 text-xs text-sub">
                    {nextKick != null ? (
                      <>
                        下一场{" "}
                        <b className="text-[#9db9ff]">
                          {new Date(nextKick).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                        </b>{" "}
                        开赛（{cdSec != null ? fmtCd(cdSec) : "—"}后），开赛后比分每 20 秒刷新一次
                      </>
                    ) : (
                      "55 个赛事源当前均无在打的比赛，可切换到「即将开始」查看真实赛程"
                    )}
                  </div>
                )}
              </div>
            ) : (
              <>
                {filtered.slice(0, visibleCount).map((m, i) => (
                  <div key={m.id} className="rise-in" style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}>
                    <MatchRow m={m} />
                  </div>
                ))}
                {filtered.length > visibleCount && (
                  <button
                    onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                    className="w-full border-t border-line py-3 text-xs font-bold text-sub transition hover:bg-panel2 hover:text-txt"
                  >
                    显示更多（还有 {filtered.length - visibleCount} 场）· 已显示 {visibleCount}/{filtered.length}
                  </button>
                )}
              </>
            )}
          </div>
        </Panel>

        {/* 右栏 */}
        <div id="top" className="flex scroll-mt-20 flex-col gap-4">
          <Panel title="🤖 AI 预测排行" tag="今日置信度 TOP">
            {!top ? (
              <div className="space-y-3 px-4 py-4">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            ) : (
              <ul>
                {top.map((p, i) => (
                  <li key={p.match_id} className="border-b border-line last:border-b-0">
                    <Link href={`/match/?id=${p.match_id}`}
                      className="flex items-center gap-2.5 px-4 py-2.5 text-[13px] transition-colors hover:bg-panel2">
                      <span className={`w-5 text-center font-extrabold ${i < 3 ? "text-gold" : "text-sub"}`}>
                        {i + 1}
                      </span>
                      <span className="flex-1 truncate font-semibold">
                        {p.title} · {p.pick}
                      </span>
                      <span className="font-extrabold tabular-nums text-[#9db9ff]">
                        {Math.round(p.probability * 100)}%
                      </span>
                    </Link>
                  </li>
                ))}
                {top.length === 0 && (
                  <li className="px-4 py-8 text-center text-sm text-sub">今日暂无未开赛比赛</li>
                )}
              </ul>
            )}
          </Panel>

          <Panel title="🔥 热门赛事" tag="Elo 实力榜">
            <ul>
              {(matches ?? [])
                .filter((m) => m.is_hot)
                .slice(0, 6)
                .map((m) => (
                  <li key={m.id} className="border-b border-line last:border-b-0">
                    <Link href={`/match/?id=${m.id}`}
                      className="flex items-center gap-2.5 px-4 py-2.5 text-[13px] transition-colors hover:bg-panel2">
                      <span className="w-5 text-center">🔥</span>
                      <span className="flex-1 truncate font-semibold">
                        {m.home_team.short_name} vs {m.away_team.short_name}
                      </span>
                      <span className="text-sub tabular-nums">
                        {new Date(m.kickoff_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </Link>
                  </li>
                ))}
              {(matches ?? []).filter((m) => m.is_hot).length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-sub">暂无焦点战</li>
              )}
            </ul>
          </Panel>

          <Panel title="📡 数据链路">
            <div className="space-y-2 px-4 py-4 text-xs leading-relaxed text-sub">
              <div>
                数据源
                <span className={`float-right font-bold ${ds?.mode === "real" ? "text-[#22c58b]" : "text-[#f5b342]"}`}>
                  ● {ds?.label ?? "检测中…"}
                </span>
              </div>
              <div>
                真实比赛
                <span className="float-right font-bold text-txt">
                  {ds?.real_matches ?? 0} / {ds?.total_matches ?? 0} 场
                </span>
              </div>
              <div>Elo + Dixon-Coles + XGBoost <span className="float-right font-bold text-[#22c58b]">● 已加载</span></div>
              <div>
                WebSocket 推送 5s
                <span className={`float-right font-bold ${linkOk ? "text-[#22c58b]" : connected ? "text-[#f5b342]" : "text-[#ff6b7a]"}`}>
                  {linkOk ? `● 已连接 · 心跳 ${beatAgo ?? "—"}s` : connected ? "● 连接中…" : "● 未连接"}
                </span>
              </div>
              <div>
                直播快车道 20s
                <span className="float-right font-bold text-[#22c58b]">● 运行中</span>
              </div>
              <div>REST 兜底轮询 30s <span className="float-right font-bold text-[#22c58b]">● 运行中</span></div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
