"""系统运行状态：数据源 Provider、缓存命中率、运行时长。"""
import time

from fastapi import APIRouter

from app.core.cache import cache
from app.core.config import settings
from app.providers import get_provider

router = APIRouter(prefix="/api/v1/system", tags=["system"])
_started = time.time()


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
