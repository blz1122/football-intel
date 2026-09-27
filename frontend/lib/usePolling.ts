"use client";
// 定时轮询 hook —— Phase 2 的"定时刷新"模式（Phase 4 将升级为 WebSocket）
import { useEffect, useRef, useState } from "react";

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 10000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setInterval>;

    const run = async () => {
      try {
        const d = await fetcherRef.current();
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "请求失败");
      } finally {
        if (alive) setLoading(false);
      }
    };

    run();
    timer = setInterval(run, intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { data, error, loading };
}
