"""FastAPI 应用入口。

启动:
    uvicorn app.main:app --reload --port 8000
首次启动自动建表并注入模拟种子数据（无比赛时）。
"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.routers import matches, meta, system, teams
from app.simulator import seed_all
from app import ws as ws_layer


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # 训练/加载 XGBoost 模型（缺失时自动训练，依赖缺失自动降级）
    try:
        from app.ml.train import ensure_model

        print(f"[boot] ML model: {ensure_model()}")
    except Exception as e:
        print(f"[boot] ML model unavailable, DC-only mode: {e}")
    db = SessionLocal()
    try:
        seeded = seed_all(db)
        print(f"[boot] seed executed: {seeded}")
    finally:
        db.close()
    # Phase 4: WebSocket 广播循环改为在首个 WS 连接时启动（见 ws.ensure_broadcast_task）
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def process_time_header(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return resp


app.include_router(matches.router)
app.include_router(meta.router)
app.include_router(teams.router)
app.include_router(system.router)
app.include_router(ws_layer.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": settings.VERSION}


# ---------------- Phase 5: 桌面版静态前端托管 ----------------
# build_desktop.py 会把 Next 静态导出产物放入 backend/static/；
# 目录存在时 FastAPI 直接托管（同源访问 API + WS，零 CORS）。
from pathlib import Path

from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")
