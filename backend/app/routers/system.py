"""系统运行状态：数据源 Provider、缓存命中率、运行时长。"""
import time

from fastapi import APIRouter

from app.core.cache import cache
from app.core.config import settings
from app.providers import get_provider

router = APIRouter(prefix="/api/v1/system", tags=["system"])
_started = time.time()


def _data_source() -> dict:
    """当前实际数据来源：真实（ESPN）或模拟引擎，供前端如实展示。"""
    from app.core.db import SessionLocal
    from app.models import Match

    from app.ingest import espn

    db = SessionLocal()
    try:
        real = db.query(Match).filter(Match.provider == "espn").count()
        total = db.query(Match).count()
    finally:
        db.close()
    sync = espn.last_sync()
    if real:
        return {
            "mode": "real", "provider": "ESPN", "label": "真实数据 · ESPN",
            "real_matches": real, "total_matches": total,
            "last_sync": sync.get("at"), "sync_ok": sync.get("ok"),
        }
    return {
        "mode": "mock", "provider": "simulator", "label": "演示模式 · 模拟数据",
        "real_matches": 0, "total_matches": total,
        "last_sync": sync.get("at"), "sync_ok": sync.get("ok"),
        "sync_error": sync.get("error"),
    }


@router.get("/status")
def status():
    """运行状态总览（含数据源连通性检查）。"""
    from app import ws as ws_layer

    provider = get_provider()
    return {
        "version": settings.VERSION,
        "uptime_seconds": round(time.time() - _started),
        "ws": {
            "loop_alive_seconds_ago": (
                round(time.time() - ws_layer.manager.last_beat)
                if ws_layer.manager.last_beat
                else None
            ),
            "latest_snapshots": len(ws_layer.manager.latest),
            "clients": len(ws_layer.manager.active),
        },
        "data_provider": {
            "configured": settings.DATA_PROVIDER,
            "active": provider.name,
            "health": provider.healthcheck(),
        },
        "data_source": _data_source(),
        "cache": cache.stats(),
        "ws_push_interval": settings.WS_PUSH_INTERVAL,
        "llm_report": "enabled" if settings.OPENAI_API_KEY else "template-engine",
    }


@router.post("/ws-test")
async def ws_test():
    """诊断：从请求上下文向所有活跃 WS 客户端广播测试帧。"""
    from app import ws as ws_layer

    sent = 0
    for ws in list(ws_layer.manager.active):
        if await ws_layer.manager.send(ws, {"type": "test", "from": "rest"}):
            sent += 1
    return {"sent": sent, "clients": len(ws_layer.manager.active)}
