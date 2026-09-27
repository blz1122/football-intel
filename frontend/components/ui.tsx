// 通用小组件：比赛队徽圆标、状态标签、概率条
import type { TeamBrief } from "@/lib/types";

export function TeamBadge({ team, size = 20 }: { team: TeamBrief; size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-full font-extrabold text-white flex-none"
      style={{ background: team.color, width: size, height: size, fontSize: size * 0.42 }}
    >
      {team.short_name.slice(0, 3)}
    </span>
  );
}

export function StatusTag({ status, period }: { status: string; period: string | null }) {
  if (status === "live")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#20111a] border border-[#4a2030] px-2.5 py-0.5 text-[11px] font-bold text-live">
        <span className="h-1.5 w-1.5 rounded-full bg-live animate-pulse" />LIVE {period}
      </span>
    );
  if (status === "halftime")
    return (
      <span className="rounded-full bg-[#20111a] border border-[#4a2030] px-2.5 py-0.5 text-[11px] font-bold text-live">
        中场 HT
      </span>
    );
  if (status === "finished")
    return (
      <span className="rounded-full bg-panel2 px-2.5 py-0.5 text-[11px] font-bold text-sub">完赛 FT</span>
    );
  return (
    <span className="rounded-full bg-[#16264d] border border-[#28437f] px-2.5 py-0.5 text-[11px] font-bold text-[#9db9ff]">
      未开始
    </span>
  );
}

export function ProbBar({ p }: { p: { home: number; draw: number; away: number } }) {
  const total = p.home + p.draw + p.away || 1;
  const segments = [
    { v: p.home, c: "#2f6bff" },
    { v: p.draw, c: "#5a6780" },
    { v: p.away, c: "#ff7a45" },
  ];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex h-1.5 w-full overflow-hidden rounded bg-base2">
        {segments.map((s, i) => (
          <i key={i} style={{ width: `${(s.v / total) * 100}%`, background: s.c }} />
        ))}
      </div>
      <div className="flex justify-between text-[10.5px] text-sub tabular-nums">
        <span>主 {Math.round(p.home * 100)}%</span>
        <span>平 {Math.round(p.draw * 100)}%</span>
        <span>客 {Math.round(p.away * 100)}%</span>
      </div>
    </div>
  );
}

export function Panel({
  title,
  tag,
  children,
  className = "",
}: {
  title?: string;
  tag?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`overflow-hidden rounded-xl border border-line bg-panel ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold">{title}</h3>
          {tag && <span className="rounded-full bg-panel2 px-2.5 py-0.5 text-[11px] text-sub">{tag}</span>}
        </header>
      )}
      {children}
    </section>
  );
}
