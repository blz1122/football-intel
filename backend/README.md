# Backend · FastAPI

## 环境

依赖安装在 WorkBuddy 隔离 venv：`C:/Users/31471/.workbuddy/binaries/python/envs/default`

## 启动

```bash
cd backend
C:/Users/31471/.workbuddy/binaries/python/envs/default/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- 首次启动自动建表（SQLite `backend/football_intel.db`）并注入模拟种子数据
- 任何时候启动都有进行中的比赛（kickoff 相对当前时间生成）
- API 文档：http://127.0.0.1:8000/docs

## 模块

| 路径 | 职责 |
|------|------|
| `app/core/config.py` | 配置（数据库 URL / CORS / 比赛时钟参数） |
| `app/core/db.py` | engine / SessionLocal / get_db |
| `app/core/predictor.py` | Elo-Poisson 赛前预测 + 动态胜率（Phase 3 升级 Dixon-Coles + XGBoost） |
| `app/models.py` | SQLAlchemy 模型（与 db/schema.sql 对齐） |
| `app/schemas.py` | Pydantic 响应契约 |
| `app/simulator.py` | 模拟数据引擎：种子数据 / 事件生成 / 分钟级统计（确定性、可重放） |
| `app/routers/matches.py` | 比赛列表/详情/事件/统计/胜率曲线/射门地图 |
| `app/routers/meta.py` | KPI（真实计算的准确率与 Brier Score）/ 预测排行 / 联赛 |

## 重置数据

删除 `backend/football_intel.db` 后重启即可重新种子。
