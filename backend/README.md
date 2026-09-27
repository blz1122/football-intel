# Backend · FastAPI

## 环境

依赖安装在 WorkBuddy 隔离 venv：`C:/Users/31471/.workbuddy/binaries/python/envs/default`

## 启动

```bash
cd backend
C:/Users/31471/.workbuddy/binaries/python/envs/default/Scripts/python.exe run.py
# 等价于：python -m uvicorn app.main:app --port 8000 --ws websockets-sansio
```

- **务必使用 `run.py` 或带 `--ws websockets-sansio`**（uvicorn 旧版 websockets 实现已废弃）
- WS 广播任务由首个 WebSocket 连接触发启动（lifespan 创建的任务 send_text 会静默丢帧，已规避）
- 首次启动自动建表（SQLite `backend/football_intel.db`）、训练/加载 XGBoost 模型并注入模拟种子数据
- 任何时候启动都有进行中的比赛（kickoff 相对当前时间生成）
- API 文档：http://127.0.0.1:8000/docs

## WebSocket 实时推送

端点 `ws://localhost:8000/api/v1/ws/matches`，协议（JSON）：

| 方向 | 消息 | 说明 |
|------|------|------|
| 服务端→客户端 | `hello` | 连接确认，含推送间隔 |
| 服务端→客户端 | `live_update` | 单场实时快照（分钟/比分/胜率/统计），变更才推送 |
| 服务端→客户端 | `live_count` | 全局进行中场次数（变更才推送） |
| 服务端→客户端 | `heartbeat` | 每 30s 一帧，连接保活 |
| 客户端→服务端 | `subscribe_all` / `subscribe` / `unsubscribe` / `ping` | 订阅控制 |

订阅成功立即下发当前全部快照（`push_current`），无需等待下一次分钟跳变。

## 数据源 Provider

环境变量 `DATA_PROVIDER` 切换：

- `mock`（默认）：本地确定性模拟引擎，零依赖演示
- `api_football`：真实数据源 api-football.com，需设置 `API_FOOTBALL_KEY`（见 `.env.example`）

运行状态（含 Provider 健康检查、缓存命中率、WS 循环探针）：`GET /api/v1/system/status`

## 模块

| 路径 | 职责 |
|------|------|
| `app/core/config.py` | 配置（数据库 URL / CORS / Provider / LLM / WS 间隔） |
| `app/core/db.py` | engine / SessionLocal / get_db |
| `app/core/cache.py` | 进程内 TTL 缓存（命中率统计，可平替 Redis） |
| `app/core/predictor.py` | Dixon-Coles + XGBoost 融合预测 + 动态胜率 |
| `app/core/report.py` | AI 比赛报告：数据驱动模板引擎 + 可选 LLM |
| `app/core/llm` 亦可经 report.py 调用 | OpenAI 兼容接口（未配置自动回退模板） |
| `app/models.py` | SQLAlchemy 模型（与 db/schema.sql 对齐） |
| `app/schemas.py` | Pydantic 响应契约 |
| `app/simulator.py` | 模拟数据引擎：种子数据 / 事件生成 / 分钟级统计（确定性、可重放） |
| `app/providers/` | 数据源抽象：MockProvider / ApiFootballProvider / 工厂 |
| `app/ws.py` | WebSocket 连接管理 + 变更检测广播循环 |
| `app/ml/` | XGBoost 训练管线 / Monte Carlo 模拟 |
| `app/routers/matches.py` | 比赛列表/详情/事件/统计/曲线/射门地图/AI 报告 |
| `app/routers/meta.py` | KPI / 预测排行 / 联赛 |
| `app/routers/system.py` | 系统状态 / 诊断 |

## 重置数据

删除 `backend/football_intel.db` 后重启即可重新种子。
