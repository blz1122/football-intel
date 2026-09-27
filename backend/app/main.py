"""FastAPI 应用入口。

启动:
    uvicorn app.main:app --reload --port 8000
首次启动自动建表并注入模拟种子数据（无比赛时）。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.routers import matches, meta
from app.simulator import seed_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seeded = seed_all(db)
        print(f"[boot] seed executed: {seeded}")
    finally:
        db.close()
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(meta.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": settings.VERSION}
