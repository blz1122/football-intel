# Frontend · Next.js

## 启动

```bash
cd frontend
npm install        # 首次
npm run dev        # http://localhost:3000
```

`next.config.mjs` 已配置 rewrite：`/api/v1/*` → `http://127.0.0.1:8000/api/v1/*`，
开发时无需处理 CORS（先启动后端）。

## 结构

| 路径 | 职责 |
|------|------|
| `app/page.tsx` | Dashboard：KPI、状态 Tab、联赛筛选、AI 预测排行、热门赛事 |
| `app/match/[id]/page.tsx` | 比赛详情：胜率曲线(ECharts)、技术统计、时间线、射门地图、赛前预测、AI 报告 |
| `components/charts/EChart.tsx` | ECharts 通用封装 + 深色主题常量 |
| `components/MatchRow.tsx` | 比赛行卡片 |
| `components/ui.tsx` | TeamBadge / StatusTag / ProbBar / Panel |
| `lib/api.ts` | REST 客户端 |
| `lib/types.ts` | 与后端 schemas.py 对齐的 TS 类型 |
| `lib/usePolling.ts` | 定时轮询 hook（Phase 4 升级 WebSocket） |

刷新策略：比赛列表 10s、曲线 15s、射门地图 20s、KPI 30s。
