# ⚽ Football Intelligence Platform

**AI 驱动的专业级足球数据分析与实时胜率预测平台**

对标 SofaScore / Opta Football Analytics / ESPN Match Analytics 的设计理念，
融合 **实时数据 + 历史数据 + 机器学习 + 数据可视化**，提供比赛追踪、AI 胜率预测、
xG 高阶分析、Monte Carlo 比赛模拟与 AI 赛后报告的完整能力。

> 本项目定位为 **商业级体育数据分析产品**，而非普通比分查询网站。

---

## 🌍 数据源：ESPN 公开接口（无需 API key）

平台默认接入 **ESPN 公开接口** 的真实赛程、比分、状态、进球/红黄牌事件与技术统计，
并在此之上运行自研的 Dixon-Coles + XGBoost 预测模型。

**覆盖 55 个赛事源，分三类：**

| 类别 | 赛事 |
|------|------|
| 🌍 洲际俱乐部赛事 | 欧冠、欧联、欧协联、亚冠、非冠、中北美联杯 |
| 🌐 国家队赛事 | 世界杯、欧洲杯、亚洲杯、非洲杯、欧国联、国际友谊赛、各大洲世预赛 |
| 🏠 各国联赛 | 五大联赛、荷甲、葡超、比甲、土超、瑞士超、丹麦超、瑞典超、挪超、希腊超、罗甲、俄超、苏超/苏冠，以及中超、J联赛、K联赛、澳超、美职业、墨西哥超、巴甲、阿甲、哥甲、乌拉圭甲、秘鲁甲、智利甲、南非超、尼日利亚超等 37 项 |

- 比赛列表窗口：近 7 天 + 未来 14 天（`MATCH_WINDOW_DAYS`）
- 同步频率：每 5 分钟（`REAL_SYNC_INTERVAL`），启动时立即全量同步
- 单轮详情拉取上限：80 场（`ESPN_DETAIL_BUDGET`），按「进行中 > 近 24h 完赛 > 重点赛事」优先级分配
- 714 条球队中文名映射，界面以中文显示（含「阿根廷 vs 布基纳法索」这类国家队）

**球队名单（真实阵容）**

球队页的阵容来自 ESPN 的 **`/teams/{id}/roster`** 接口（一线队全员，非单场名单）：

- 字段：号码、位置、年龄、国籍、赛季真实产出（出场/进球/助攻/射门/射正/扑救/红黄牌）
- 位置归一：ESPN 给出的是细粒度缩写（CD-L / DM / LB / RB …），平台统一映射到 GK/DF/MF/FW
- AI Player Rating 由真实产出推算（每场进球/助攻/射正 + 扑救率 + 球队强度微调），不再全员 6.5
- 启动/每 2 小时刷新一次，覆盖上限 `ESPN_ROSTER_BUDGET`（默认 180 支球队）
- 近 300 条知名球员中文译名；未收录的自动回退英文名

**Elo 实力评级（自研）**

ESPN 不提供球队排名，因此平台用**近 400 天真实赛果批量反推 Elo**：

- 首次启动自动拉取 2025+2026 两年历史赛程（约 2 万场，仅入库比分不拉详情，~20s）
- 俱乐部与国家队**分开评估**（尺度不同），同一球队跨赛事共享评级
- 每小时随新赛果重算一次，评级结果符合现实（巴黎/曼城/皇马/巴萨/拜仁居前）
- Elo 同时驱动 TPI 球队实力指数与全部 AI 胜率预测

因此预测不再退化成「45%/29%/26%」的均匀分布 —— 强队主胜可达 94%，弱队 2%。

**切换数据源**（环境变量）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `REAL_DATA` | `1` | 设为 `0` 退回内置模拟引擎 |
| `REAL_SYNC_INTERVAL` | `300` | 同步间隔（秒） |
| `MATCH_WINDOW_DAYS` | `14` | 列表未来窗口（天） |
| `ESPN_DETAIL_BUDGET` | `80` | 单轮拉取比赛详情上限 |

---

## ✨ 核心功能

| 模块 | 能力 |
|------|------|
| 🏠 实时数据中心 | 今日 / 进行中 / 即将开始 / 历史比赛，联赛、比分、状态一站式看板；按「洲际赛事 / 国家队 / 各国联赛」分组筛选 |
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
├── deploy/
│   └── docker-compose.yml   # 生产部署（PostgreSQL + backend + frontend）
├── design/
│   └── ui-prototype.html    # 高保真 UI 原型（深色科技风）
├── backend/                 # FastAPI（Phase 2+）
│   ├── app/core/            # 配置 / DB / 缓存 / 预测 / AI 报告引擎
│   ├── app/providers/       # 数据源 Provider（Mock / api-football 适配）
│   ├── app/routers/         # 路由（比赛 / 元数据 / 球队 / 系统）
│   ├── app/ws.py            # WebSocket 连接管理与广播
│   ├── app/ml/              # XGBoost 训练 / Monte Carlo
│   ├── run.py               # Web 启动脚本
│   ├── desktop.py           # 桌面版入口（静态前端 + FastAPI 单进程）
│   └── build_desktop.py     # Windows 客户端一键打包
├── frontend/                # Next.js（Phase 2+）
│   ├── app/                 # App Router 页面
│   ├── components/          # UI 组件
│   └── lib/                 # API 客户端 / 类型 / WS hook
└── README.md
```

---

## 🚀 快速开始

**后端**（FastAPI，含模拟数据引擎，首次启动自动建表 + 训练模型 + 注入种子）：

```bash
cd backend
pip install -r requirements.txt
python run.py        # http://127.0.0.1:8000 ，API 文档 /docs
```

**前端**（Next.js Dashboard）：

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

打开 Dashboard 即可看到实时比赛、AI 预测排行与 WebSocket 实时推送。

## 🐳 Docker 生产部署

```bash
cd deploy
docker compose up -d --build
# frontend  -> http://localhost:3000
# backend   -> http://localhost:8000/docs
# PostgreSQL 16（数据持久化卷 pgdata，首次启动自动执行 db/schema.sql）
```

可选环境变量（写入 `deploy/.env`）：`POSTGRES_PASSWORD`、`DATA_PROVIDER=api_football`、
`API_FOOTBALL_KEY`、`OPENAI_API_KEY`；跨机访问时把 `NEXT_PUBLIC_WS_URL` 改为
`ws://<宿主IP>:8000/api/v1/ws/matches` 后重新 build frontend。

## 🖥️ Windows 桌面客户端（单进程，免安装依赖）

前端静态导出与 FastAPI 合体打包为 exe，双击自动启动并打开浏览器：

```bash
cd backend
python build_desktop.py          # 完整版（含 XGBoost / sklearn）
python build_desktop.py --slim   # 精简版（Dixon-Coles 基线，体积约 1/10）
```

产物：`backend/dist/FootballIntel/FootballIntel.exe`。

## 🗺️ 开发阶段

- **Phase 1** ✅ 产品架构设计 · 仓库初始化 · 数据库设计 · UI 原型
- **Phase 2** ✅ Dashboard · 比赛数据模块 · 数据接口（FastAPI + Next.js + 模拟引擎）
- **Phase 3** ✅ Dixon-Coles + XGBoost 融合 · Monte Carlo · TPI/球员评分 · 全站中文化
- **Phase 4** ✅ Provider 适配层（可接真实 API） · WebSocket 实时推送 · 缓存/压缩优化 · AI 报告引擎
- **Phase 5** ✅ UI 升级（骨架屏/动效/移动端） · Docker 部署 · Windows 客户端打包

详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 📚 方法论参考（仅学习思想，代码原创）

- [penaltyblog](https://github.com/martineastwood/penaltyblog) — Poisson / Dixon-Coles 比分模型、Elo/Massey 评级思路
- [livescoreFootball](https://github.com/rezarahiminia/livescoreFootball) — 足球 REST API 资源划分方式
- [eddwebster/football_analytics](https://github.com/eddwebster/football_analytics) — 数据管线与公开数据源索引
- [awesome-football-analytics](https://github.com/diegopastor/awesome-football-analytics) — 领域资源合集

## 📄 License

MIT
