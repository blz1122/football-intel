"use client";
// WebSocket 实时推送 hook —— Phase 4（直连后端 8000 端口，Next dev 代理不转发 WS）
// 协议见 backend/app/ws.py；断线自动重连（指数退避，上限 15s）。
import { useEffect, useRef, useState } from "react";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/v1/ws/matches";

// WebSocket 地址：
// 1. 显式配置 NEXT_PUBLIC_WS_URL 优先
// 2. 打包版（exe 同源托管/局域网 IP 访问）自动用当前页面的 host，避免系统代理劫持 localhost
// 3. 开发模式（3000 端口，Next 不转发 WS）回退直连 8000
function wsUrl(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (typeof window !== "undefined") {
    const { protocol, hostname, port } = window.location;
    if (port && port !== "3000") {
      return `${protocol === "https:" ? "wss" : "ws"}://${hostname}:${port}/api/v1/ws/matches`;
    }
  }
  return WS_URL;
}

export interface LiveSnapshot {
  match_id: number;
  status: string;
  period: string;
  minute: number | null;
  home_score: number;
  away_score: number;
  win_prob: { home: number; draw: number; away: number };
  stats: Record<string, number> | null;
}

export function useLiveSocket(subscribeAll = false, matchId?: number) {
  const [updates, setUpdates] = useState<Record<number, LiveSnapshot>>({});
  const [liveCount, setLiveCount] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  // 最近一帧服务端消息的时间戳：用来区分"连接正常但比分没变"和"链路已死"
  const [lastMsgAt, setLastMsgAt] = useState<number | null>(null);
  // 最近一次真正收到比分/分钟变化的时间（心跳帧不算）
  const [lastUpdateAt, setLastUpdateAt] = useState<number | null>(null);
  // 每秒自走一次，让"N 秒前刷新"能自己跳动
  const [tick, setTick] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        retryRef.current = 0;
        setConnected(true);
        ws.send(
          JSON.stringify(
            subscribeAll
              ? { action: "subscribe_all" }
              : { action: "subscribe", match_id: matchId }
          )
        );
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          setLastMsgAt(Date.now());
          if (msg.type === "live_update") {
            setUpdates((prev) => ({
              ...prev,
              [msg.match_id]: msg.data as LiveSnapshot,
            }));
            setLastUpdateAt(Date.now());
          } else if (msg.type === "live_count") {
            setLiveCount(msg.count);
          }
        } catch {
          /* 忽略坏帧 */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          const delay = Math.min(3000 * 2 ** retryRef.current, 15000);
          retryRef.current += 1;
          timer = setTimeout(connect, delay);
        }
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [subscribeAll, matchId]);

  return { updates, liveCount, connected, lastMsgAt, lastUpdateAt, tick };
}
