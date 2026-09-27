# 开发路线图（ROADMAP）

> 按软件工程流程分 5 个 Phase，每个 Phase 结束产出可运行、可演示的增量。

## Phase 1 — 架构与设计基线 ✅

- [x] 产品定位与功能范围定义
- [x] 系统架构设计（`docs/ARCHITECTURE.md`）
- [x] PostgreSQL 数据库设计（`db/schema.sql` + 设计文档）
- [x] REST / WebSocket API 接口设计（`docs/API_DESIGN.md`）
- [x] 高保真 UI 原型（`design/ui-prototype.html`，深色科技风）
- [x] GitHub 仓库初始化、README、Git 版本管理

## Phase 2 — 数据基座与 Dashboard ⏳

- [ ] FastAPI 工程骨架（分层：api/models/schemas/services）
- [ ] SQLAlchemy ORM + Alembic 迁移
- [ ] **模拟数据引擎**：联赛/球队/球员/赛程生成器 + 比赛分钟级事件模拟器
- [ ] 比赛列表 / 比赛详情 REST 接口
- [ ] Next.js 前端骨架（App Router + Tailwind + 主题系统）
- [ ] Dashboard 首页：比赛卡片、状态分组、联赛筛选
- [ ] 比赛详情页：技术统计、事件时间线
- [ ] ECharts 组件库封装（含中国式红涨绿跌配色规范）

## Phase 3 — AI 预测与分析 ⏳

- [ ] 数据特征工程（Elo、近10场、主客场、交锋、伤停）
- [ ] Dixon-Coles 基线模型（λ_home/λ_away）
- [ ] XGBoost 胜平负多分类 + logistic stacking 融合
- [ ] 赛前预测接口 + 概率展示组件
- [ ] 实时动态胜率（贝叶斯分钟级更新）+ 概率曲线
- [ ] Monte Carlo 模拟（10,000 次）+ 比分矩阵热力图
- [ ] xG 分析：射门地图、Shot Quality
- [ ] Team Power Index 与 AI Player Rating 计算管线
- [ ] 球队/球员 Profile 页面

## Phase 4 — 实时化与性能 ⏳

- [ ] Provider 适配器：接入真实 API（API-Football / football-data.org）
- [ ] xG 数据源接入（Understat）
- [ ] WebSocket 实时推送（事件 + 胜率）
- [ ] Redis 热数据缓存、接口分页与查询优化
- [ ] 数据回填脚本与 ETL 调度
- [ ] AI 比赛报告生成（赛前 preview / 赛后 review）

## Phase 5 — 打磨与交付 ⏳

- [ ] UI 升级：动效、骨架屏、暗/亮主题、移动端适配
- [ ] 部署：Docker Compose（PostgreSQL + FastAPI + Next.js）
- [ ] Windows 客户端打包（Tauri / Electron 评估）
- [ ] 监控与日志（结构化日志 + 健康检查）
- [ ] 模型评估看板（Brier Score、校准曲线）
- [ ] 作品展示文档与 Demo 数据集

## 里程碑验收标准

| Phase | 演示标准 |
|-------|----------|
| 2 | 打开 Dashboard 可见模拟实时比赛滚动更新 |
| 3 | 输入任一比赛可给出赛前概率 + 实时曲线 + 比分矩阵 |
| 4 | 真实 API 数据接入，WebSocket 秒级推送 |
| 5 | 一键部署 + Windows 可执行包 |
