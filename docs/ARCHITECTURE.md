# 系统架构设计（ARCHITECTURE）

> AI Football Intelligence Platform · v0.1 · Phase 1

## 1. 总体架构

系统采用 **前后端分离 + 实时事件驱动** 的四层架构：

```
┌─────────────────────────────────────────────────────────────┐
│                     数据源层 (Data Sources)                   │
│  模拟数据引擎(Phase 2) │ API-Football │ football-data.org     │
│                        │ Understat(xG) │ Club Elo            │
└──────────────┬──────────────────────────────────────────────┘
               │ REST / 定时抓取
┌──────────────▼──────────────────────────────────────────────┐
│                     服务层 (FastAPI)                          │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────────────┐  │
│  │ Provider 适配│→│ 数据处理模块  │→│ AI 推理引擎            │  │
│  │ (统一数据模型)│ │ (清洗/聚合)  │ │ 预测·xG·MonteCarlo    │  │
│  └─────────────┘ └──────┬──────┘ └──────────┬────────────┘  │
│                         │                   │               │
│  ┌──────────────────────▼───────────────────▼────────────┐  │
│  │         API 网关：REST + WebSocket + 任务调度           │  │
│  └──────────────────────────┬────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    存储层 (PostgreSQL)                        │
│  维度数据(联赛/球队/球员) │ 事实数据(比赛/事件/统计)              │
│  模型产物(预测/模拟/评级) │ 实时缓存(Redis 可选, Phase 4)        │
└─────────────────────────────┬───────────────────────────────┘
                              │ REST JSON / WS 推送
┌─────────────────────────────▼───────────────────────────────┐
│                  展示层 (Next.js + ECharts)                   │
│  Dashboard │ 比赛详情(概率曲线/雷达/热力图) │ 球队/球员 Profile │
└─────────────────────────────────────────────────────────────┘
```

## 2. 实时数据流

```
足球API → FastAPI(Provider适配) → 数据处理模块 → AI预测模型 → WebSocket → React Dashboard
```

- **轮询刷新**：非比赛时段 60s 拉取赛程；比赛进行中 10s 拉取实时统计
- **WebSocket 推送**：后端检测到数据变更 → 推送增量事件（进球/红牌/换人）与重新计算的胜率
- **幂等与去重**：所有外部数据以 `(provider, provider_event_id)` 唯一键去重入库

## 3. AI 模型体系

### 3.1 赛前预测（Pre-match Prediction）

| 特征组 | 特征 |
|--------|------|
| 实力 | Elo Rating、FIFA Ranking、Team Power Index |
| 状态 | 近10场胜平负、近10场 xG/xGA、进球失球趋势 |
| 环境 | 主客场表现差、主场优势系数、赛程密度（近14天比赛数） |
| 对位 | 历史交锋战绩、风格克制（控球 vs 反击） |
| 阵容 | 核心球员在/伤停（加权身价与出场时间）、首发评分 |

**模型方案（两阶段）**：
1. **基线模型**：Dixon-Coles 双泊松模型 → 得到两队进球强度 λ_home / λ_away，推出胜平负与比分矩阵（可解释、小样本稳健）
2. **机器学习模型**：XGBoost 多分类（Home/Draw/Away）+ 特征重要性输出
3. **融合**：logistic stacking 融合基线与 ML 输出，输出校准概率

### 3.2 实时动态胜率（In-match Dynamic Win Probability）

输入：当前比分、比赛分钟、射门/射正、xG 累计、控球率、危险进攻、红牌。

方法：以 Dixon-Coles 剩余时间进球强度为先验，按分钟衰减 λ(t)，结合
贝叶斯更新（当前状态作为证据修正强度），每分钟输出 Home/Draw/Away 三概率。
输出存入 `win_probability_snapshots` 表，前端绘制概率曲线。

### 3.3 Monte Carlo 模拟

以 λ_home / λ_away（含实时修正）对 10,000 场比赛做泊松采样 →
比分概率矩阵、胜平负概率、大小球（Over/Under 2.5）、双方进球（BTTS）。

### 3.4 Team Power Index（TPI）

`TPI = 0.35·攻击分 + 0.35·防守分 + 0.20·状态分 + 0.10·主客修正`
攻击分由 xG/射门效率归一化，防守分由 xGA/防守成功率反向归一化，0–100 分。

### 3.5 AI Player Rating

加权：进攻贡献（进球/xG/xA）、传球、防守贡献（抢断/拦截）、出场结果影响，
使用 Z-score 按位置分组归一化后映射到 0–10 分。

## 4. 后端模块划分

```
backend/app/
├── api/            # 路由层：matches / teams / players / predictions / live(ws)
├── core/           # 配置、数据库连接、依赖注入
├── models/         # SQLAlchemy ORM 模型（对应 db/schema.sql）
├── schemas/        # Pydantic 请求/响应模型
├── services/
│   ├── providers/  # 数据源适配器：simulator / apifootball / understat
│   ├── ingest/     # 拉取、清洗、入库
│   └── analytics/  # 统计聚合（xG、控球、进攻区域）
└── ml/
    ├── prematch/   # Dixon-Coles + XGBoost + 融合
    ├── inmatch/    # 动态胜率贝叶斯更新
    ├── simulate/   # Monte Carlo
    └── rating/     # TPI / Player Rating
```

## 5. 前端模块划分

```
frontend/
├── app/
│   ├── page.tsx                  # Dashboard 首页
│   ├── match/[id]/page.tsx       # 比赛详情（概率曲线/雷达/热力图/AI报告）
│   ├── team/[id]/page.tsx        # 球队 Profile（TPI）
│   └── player/[id]/page.tsx      # 球员 Profile
├── components/
│   ├── match/    # 比赛卡片、比分条、技术统计
│   ├── charts/   # WinProbChart / RadarChart / ShotMap / Heatmap（ECharts 封装）
│   └── layout/   # 侧边栏、顶栏（Bloomberg 终端式导航）
└── lib/
    ├── api.ts                    # REST 客户端
    ├── ws.ts                     # WebSocket 客户端（自动重连）
    └── types/                    # 与后端 schemas 对齐的 TS 类型
```

## 6. 关键设计决策

| 决策 | 理由 |
|------|------|
| Provider 适配器模式 | Phase 2 用模拟器，Phase 4 无缝切换真实 API，前端零改动 |
| Dixon-Coles 作为基线 | 比分模型成熟、样本需求低、天然输出 Monte Carlo 参数 |
| 概率快照落库 | 概率曲线需要历史点，避免前端重算 |
| WebSocket 只推增量 | 事件（进球/红牌）+ 胜率点，带宽友好 |
| REST 为主 + WS 增强 | 保证弱网降级可用 |

## 7. 部署形态

- **Web**：Next.js（Vercel/自托管）+ FastAPI（Docker）+ PostgreSQL
- **Windows 客户端（Phase 5）**：Tauri 打包（前端壳）+ 内嵌 FastAPI 本地服务，或 Electron 方案二选一
