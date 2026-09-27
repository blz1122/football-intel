"""WebSocket 实时推送：连接管理 + 周期广播。

协议（JSON）:
    服务端 -> 客户端
        {"type": "hello", "interval": 5}
        {"type": "live_update", "match_id": 2, "data": {...}}   # 单场实时快照
        {"type": "live_count", "count": 12}                     # 全局进行中数量
        {"type": "pong"}

    客户端 -> 服务端
        {"action": "subscribe", "match_id": 2}   # 订阅单场
        {"action": "subscribe_all"}              # 订阅全局（实时计数 + 全部进行中）
        {"action": "unsubscribe", "match_id": 2}
        {"action": "ping"}

推送循环每 WS_PUSH_INTERVAL 秒（默认 5s）重算进行中比赛的快照，
快照内容变化时才发送，避免无效帧。
"""
import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        # websocket -> 订阅的 match_id 集合；None 表示订阅全局
        self.subs: dict[WebSocket, set[int] | None] = {}
        # 广播循环维护的最近快照与实时场次计数（供新订阅者立即获取当前状态）
        self.latest: dict[int, dict] = {}
        self.last_count: int | None = None
        # 诊断：广播循环最近一次迭代的时间戳（system/status 暴露）
        import time as _time

        self.last_beat: float = 0.0

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        self.subs[ws] = set()

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        self.subs.pop(ws, None)

    def subscribe_match(self, ws: WebSocket, match_id: int) -> None:
        cur = self.subs.get(ws)
        if cur is not None:
            cur.add(match_id)

    def subscribe_all(self, ws: WebSocket) -> None:
        if ws in self.subs:
            self.subs[ws] = None  # None = 全局

    def unsubscribe(self, ws: WebSocket, match_id: int) -> None:
        cur = self.subs.get(ws)
        if cur:
            cur.discard(match_id)

    def interested(self, ws: WebSocket, match_id: int) -> bool:
        cur = self.subs.get(ws)
        return cur is None or match_id in cur

    async def send(self, ws: WebSocket, payload: dict) -> bool:
        """发送；失败视为死连接并清理，避免阻塞广播循环。"""
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception:
            self.disconnect(ws)
            return False

    async def push_current(self, ws: WebSocket) -> None:
        """订阅成功后立即下发当前最新快照（不再等下一轮分钟跳变）。"""
        for mid, snap in manager.latest.items():
            if manager.interested(ws, mid):
                await self.send(ws, {"type": "live_update", "match_id": mid, "data": snap})
        if self.subs.get(ws) is None and self.last_count is not None:
            await self.send(ws, {"type": "live_count", "count": self.last_count})


manager = ConnectionManager()


def _topup_matches() -> None:
    """滚动补赛（仅模拟数据源）；已接入真实数据时跳过，避免编造比赛。"""
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import Match
    from app.simulator import ensure_upcoming_matches

    db = SessionLocal()
    try:
        if db.query(Match).filter(Match.provider == "espn").count() > 0:
            return
        settings_data_real = getattr(settings, "REAL_DATA", False)
        if settings_data_real:
            return
        ensure_upcoming_matches(db)
    finally:
        db.close()


def _live_snapshots() -> list[dict]:
    """在工作线程中计算进行中比赛的实时快照（避免阻塞事件循环）。"""
    from datetime import datetime, timedelta, timezone

    from app.core.db import SessionLocal
    from app.routers.matches import _to_item, effective_state

    db = SessionLocal()
    try:
        from app.models import Match, TeamRating

        now = datetime.now(timezone.utc)
        rows = (
            db.query(Match)
            .filter(
                Match.kickoff_at <= now + timedelta(hours=1),
                Match.kickoff_at >= now - timedelta(hours=6),
            )
            .order_by(Match.kickoff_at)
            .all()
        )
        ratings = {r.team_id: r for r in db.query(TeamRating).all()}
        snaps = []
        for m in rows:
            st = effective_state(m)
            if st["status"] not in ("live", "halftime"):
                continue
            item = _to_item(m, st, False, ratings)
            snaps.append({
                "match_id": m.id,
                "status": item.status, "period": item.period,
                "minute": item.minute,
                "home_score": item.home_score, "away_score": item.away_score,
                "win_prob": item.win_prob.model_dump(),
                "stats": item.live_stats.model_dump() if item.live_stats else None,
            })
        return snaps
    finally:
        db.close()


async def _broadcast_loop() -> None:
    last_payloads: dict[int, str] = {}
    last_count: int | None = None
    beats = 0
    while True:
        try:
            beats += 1
            # 滚动补赛：每 12 轮（约 1 分钟）检查一次，未完赛场次不足时自动补一轮
            if beats % 12 == 0:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(_topup_matches)
            snaps = await asyncio.to_thread(_live_snapshots)
            live_ids = {s["match_id"] for s in snaps}
            manager.latest = {s["match_id"]: s for s in snaps}
            sent = 0

            # 变更判定每轮只做一次（不能放进客户端循环——否则第一个客户端
            # 会"消费"掉变更标记，后续客户端永远收不到）
            changed: list[dict] = []
            for s in snaps:
                mid = s["match_id"]
                raw = json.dumps(s, ensure_ascii=False, sort_keys=True)
                if last_payloads.get(mid) != raw:
                    changed.append(s)
                last_payloads[mid] = raw
            for mid in list(last_payloads):
                if mid not in live_ids:
                    del last_payloads[mid]

            for ws in list(manager.active):
                alive = True
                for s in changed:
                    if not manager.interested(ws, s["match_id"]):
                        continue
                    if not await manager.send(
                        ws, {"type": "live_update",
                             "match_id": s["match_id"], "data": s}
                    ):
                        alive = False
                        break
                    sent += 1
                # 全局订阅者：仅在实时场次数变化时推送
                if (
                    alive
                    and manager.subs.get(ws) is None
                    and len(live_ids) != last_count
                ):
                    alive = await manager.send(
                        ws, {"type": "live_count", "count": len(live_ids)}
                    )
                # 诊断心跳：每 6 轮（约 30s）一帧，验证环路可达
                if alive and beats % 6 == 0 and manager.subs.get(ws) is None:
                    alive = await manager.send(ws, {"type": "heartbeat", "beat": beats})
                if not alive:
                    manager.disconnect(ws)
            last_count = len(live_ids)
            manager.last_count = last_count
            import time as _time

            manager.last_beat = _time.time()
        except Exception as e:  # 推送循环永不退出
            print(f"[ws] broadcast error: {e}")
        await asyncio.sleep(settings.WS_PUSH_INTERVAL)


@router.websocket("/api/v1/ws/matches")
async def ws_matches(ws: WebSocket):
    ensure_broadcast_task()
    await manager.connect(ws)
    await manager.send(ws, {"type": "hello", "interval": settings.WS_PUSH_INTERVAL})
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            action = msg.get("action")
            if action == "subscribe":
                manager.subscribe_match(ws, int(msg["match_id"]))
                await manager.push_current(ws)
            elif action == "subscribe_all":
                manager.subscribe_all(ws)
                await manager.push_current(ws)
            elif action == "unsubscribe":
                manager.unsubscribe(ws, int(msg.get("match_id", 0)))
            elif action == "ping":
                await manager.send(ws, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


def start_broadcast_task() -> asyncio.Task:
    return asyncio.create_task(_broadcast_loop())


_broadcast_task: asyncio.Task | None = None


def ensure_broadcast_task() -> None:
    """在首个 WS 连接（handler 上下文）时启动广播任务。

    注意：uvicorn 0.5x 下从 lifespan 创建的任务调用 send_text 会静默丢帧
    （原因未明，REST/handler 上下文均正常），因此改由首个连接触发启动。
    """
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_loop())


def stop_broadcast_task(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        pass
