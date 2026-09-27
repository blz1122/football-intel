"use client";
// 数据来源标识：明确显示当前是真实数据（ESPN）还是模拟演示数据
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface DataSourceInfo {
  mode?: string;
  provider?: string;
  label?: string;
  real_matches?: number;
  total_matches?: number;
  last_sync?: string | null;
  sync_ok?: boolean | null;
}

export function useDataSource() {
  const [info, setInfo] = useState<DataSourceInfo | null>(null);

  useEffect(() => {
    const run = () =>
      api
        .systemStatus()
        .then((d) => setInfo((d as { data_source?: DataSourceInfo }).data_source ?? null))
        .catch(() => setInfo(null));
    run();
    const t = setInterval(run, 60000);
    return () => clearInterval(t);
  }, []);

  return info;
}

export default function DataSource({ variant = "badge" }: { variant?: "badge" | "footer" }) {
  const info = useDataSource();

  const real = info?.mode === "real";
  const label = info?.label ?? "数据源检测中…";

  if (variant === "footer") {
    return (
      <span>
        FOOTINTEL · AI Football Intelligence Platform · 数据来源：
        <b className={real ? "text-[#22c58b]" : "text-[#f5b342]"}>{label}</b>
        {info?.last_sync && (
          <span className="text-sub">
            {" "}
            · 同步于 {new Date(info.last_sync).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
        {" · 模型：Dixon-Coles + XGBoost"}
      </span>
    );
  }

  return (
    <span
      className={`hidden items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold sm:inline-flex ${
        real
          ? "border-[#1d3a2a] bg-[#12241a] text-[#4ade80]"
          : "border-[#4a3c1d] bg-[#221c11] text-[#f5b342]"
      }`}
      title={
        info
          ? `真实比赛 ${info.real_matches ?? 0} 场 / 共 ${info.total_matches ?? 0} 场` +
            (info.last_sync ? ` · 上次同步 ${info.last_sync}` : "")
          : ""
      }
    >
      <span className={`h-1.5 w-1.5 rounded-full ${real ? "bg-[#22c58b]" : "animate-pulse bg-[#f5b342]"}`} />
      {label}
    </span>
  );
}
