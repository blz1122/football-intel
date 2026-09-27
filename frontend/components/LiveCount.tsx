"use client";
// 顶栏进行中比赛计数（30s 轮询）
import { useEffect, useState } from "react";

export default function LiveCount() {
  const [live, setLive] = useState<number | null>(null);

  useEffect(() => {
    const run = () =>
      fetch("/api/v1/meta/kpis", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setLive(d.live_now))
        .catch(() => {});
    run();
    const t = setInterval(run, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <span className="hidden items-center gap-1.5 rounded-full border border-[#4a2030] bg-[#20111a] px-3 py-1 text-xs font-bold text-live sm:inline-flex">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ff4d5e]" />
      {live === null ? "连接中…" : `${live} 场进行中`}
    </span>
  );
}
