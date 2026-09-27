# ⚽ Football Intelligence Platform

**AI 驱动的专业级足球数据分析与实时胜率预测平台**

对标 SofaScore / Opta Football Analytics / ESPN Match Analytics 的设计理念，
融合 **实时数据 + 历史数据 + 机器学习 + 数据可视化**，提供比赛追踪、AI 胜率预测、
xG 高阶分析、Monte Carlo 比赛模拟与 AI 赛后报告的完整能力。

> 本项目定位为 **商业级体育数据分析产品**，而非普通比分查询网站。

---

## ✨ 核心功能

| 模块 | 能力 |
|------|------|
| 🏠 实时数据中心 | 今日 / 进行中 / 即将开始 / 历史比赛，联赛、比分、状态一站式看板 |
| 📡 实时比赛追踪 | 比分、比赛分钟、控球率、射门、角球、犯规、红黄牌、换人；定时刷新 + WebSocket 推送 |
| 🤖 AI 赛前预测 | Elo / FIFA Ranking / 近10场 / 主客场 / 交锋史 / 伤停阵容 → 胜平负概率 |
| 📈 实时动态胜率 | 基于比分、时间、射门、xG、危险进攻、红牌的动态贝叶斯概率更新 + 概率变化曲线 |
| 🔬 高阶数据分析 | xG / xGA / 射门质量、射门地图、进攻区域、传球路线、防守成功率 / 抢断 / 拦截 / 压迫 |
| 🎲 Monte Carlo 模拟 | 10,000 次比赛模拟 → 比分概率矩阵、胜平负、进球数、走势预测 |
| 🛡️ 球队分析 | Team Power Index：攻击 / 防守 / 状态三维评估，近10场趋势与主客场表现 |
| 👤 球员分析 | 球员数据库：评分、xG/xA、射门效率、传球、防守贡献 → AI Player Rating |
| 📝 AI 比赛报告 | 自动生成赛前/赛后分析：关键点、战术（中场控制/边路/防守漏洞）、风险提醒 |

---

## 🧱 技术架构

```
足球数据 API（真实 / 模拟）
        │
        ▼
FastAPI 后端（Python）
  ├─ 数据接入层  Provider 适配（football-data.org / API-Football / Understat / 模拟器）
  ├─ 数据处理模块 Pandas / NumPy 清洗与聚合
  ├─ AI 预测模型  Scikit-learn / XGBoost / Poisson-DixonColes / Monte Carlo
  └─ 实时推送     WebSocket / SSE
        │
        ▼
PostgreSQL（球队 / 球员 / 比赛历史 / 实时数据 / 预测结果）
        │
        ▼
Next.js 前端（React + TypeScript + Tailwind CSS + ECharts）
```

**前端**：Next.js 14 · React 18 · TypeScript · Tailwind CSS · ECharts · 响应式（桌面 + 移动）
**后端**：Python 3.12 · FastAPI · Pandas · NumPy · Scikit-learn · XGBoost · SQLAlchemy
**数据库**：PostgreSQL 16
**实时通信**：WebSocket（比赛分钟级事件推送）+ REST（历史与聚合数据）

---

## 📁 项目结构

```
football-intel/
├── docs/                    # 设计与开发文档
│   ├── ARCHITECTURE.md      # 系统架构设计
│   ├── DATABASE_DESIGN.md   # 数据库设计
│   ├── API_DESIGN.md        # API 接口设计
│   └── ROADMAP.md           # 开发路线图
├── db/
│   └── schema.sql           # PostgreSQL DDL
├── design/
│   └── ui-prototype.html    # 高保真 UI 原型（深色科技风）
├── backend/                 # FastAPI（Phase 2+）
│   ├── app/api/             # 路由
│   ├── app/core/            # 配置与依赖
│   ├── app/models/          # ORM
│   ├── app/services/        # 数据处理 / Provider
│   └── app/ml/              # 预测模型 / 模拟器
├── frontend/                # Next.js（Phase 2+）
│   ├── app/                 # App Router 页面
│   ├── components/          # UI 组件
│   └── lib/                 # API 客户端 / 类型
└── README.md
```

---

## 🚀 快速开始（Phase 1 阶段）

当前为 **Phase 1：架构设计 + 数据库设计 + UI 原型**。

1. 查看 `design/ui-prototype.html` 预览 Dashboard 视觉方案
2. 查看 `docs/` 了解架构、数据库与 API 设计
3. `db/schema.sql` 可直接在 PostgreSQL 中执行建表

## 🗺️ 开发阶段

- **Phase 1** ✅ 产品架构设计 · 仓库初始化 · 数据库设计 · UI 原型
- **Phase 2** ⏳ Dashboard · 比赛数据模块 · 数据接口
- **Phase 3** ⏳ AI 预测模型 · xG 分析 · Monte Carlo 模拟
- **Phase 4** ⏳ 真实数据接入 · WebSocket · 性能优化
- **Phase 5** ⏳ UI 升级 · 部署 · Windows 客户端打包

详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 📚 方法论参考（仅学习思想，代码原创）

- [penaltyblog](https://github.com/martineastwood/penaltyblog) — Poisson / Dixon-Coles 比分模型、Elo/Massey 评级思路
- [livescoreFootball](https://github.com/rezarahiminia/livescoreFootball) — 足球 REST API 资源划分方式
- [eddwebster/football_analytics](https://github.com/eddwebster/football_analytics) — 数据管线与公开数据源索引
- [awesome-football-analytics](https://github.com/diegopastor/awesome-football-analytics) — 领域资源合集

## 📄 License

MIT
