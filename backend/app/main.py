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
from app.core.db import Base, SessionLocal, engine, ensure_schema
from app.models import Match
from app.routers import matches, meta, system, teams
from app.simulator import seed_all
from app import ws as ws_layer


def rebuild_predictions(db, include_history: bool = False) -> dict:
    """Elo 更新后重算预测。

    只算界面可见的比赛（is_history=False）：历史样本库有 2 万场，
    但它们只用于 Elo 反推与模型训练，不进列表，全量算要 80 秒。
    include_history=True 仅在需要为历史样本补预测时使用。
    """
    from datetime import datetime, timezone

    from app.core.predictor import prematch
    from app.models import MatchPrediction

    q = db.query(Match).filter(Match.provider == "espn")
    if not include_history:
        q = q.filter(Match.is_history.is_(False))
    rows = q.all()
    n = 0
    for m in rows:
        if m.home_team is None or m.away_team is None:
            continue
        pred = prematch(m.home_team.elo_rating, m.away_team.elo_rating)
        try:
            from app.ml.train import blend, predict_proba

            pred = blend(
                pred,
                predict_proba(m.home_team.elo_rating - m.away_team.elo_rating, 0.5, 0.5),
            )
        except Exception:
            pred["model_version"] = "dc-only-v0.1"
        if m.prediction is None:
            db.add(MatchPrediction(match_id=m.id, **pred))
        else:
            for k, v in pred.items():
                setattr(m.prediction, k, v)
        n += 1
    db.commit()
    return {"recomputed": n}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()   # 为既有库补齐真实数据源新增列
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
    # 真实数据源（ESPN，无需 key）：后台线程周期同步，失败不影响模拟数据兜底
    if settings.REAL_DATA:
        import threading

        def _sync_loop():
            from app.ingest import elo, espn

            # 1) 历史赛果（仅首次，用于 Elo 反推与模型训练；耗时较久）
            db0 = SessionLocal()
            try:
                need_hist = db0.query(Match).filter(
                    Match.provider == "espn", Match.score_home.isnot(None)
                ).count() < 2000
            except Exception:
                need_hist = True
            finally:
                db0.close()
            if need_hist:
                dbh = SessionLocal()
                try:
                    print(f"[boot] history sync: {espn.sync_history(dbh)}", flush=True)
                except Exception as e:
                    print(f"[boot] history sync failed: {e}", flush=True)
                finally:
                    dbh.close()
                # 2) 用真实赛果反推 Elo（否则新球队全是 1500，预测退化为均匀分布）
                dbe = SessionLocal()
                try:
                    print(f"[boot] Elo: {elo.recompute_elo(dbe)}", flush=True)
                except Exception as e:
                    print(f"[boot] Elo failed: {e}", flush=True)
                finally:
                    dbe.close()

            # 3) 启动首轮：拉全量赛程 + 详情（事件/统计/比赛名单）
            db2 = SessionLocal()
            try:
                print(f"[boot] ESPN sync: {espn.sync(db2, with_details=True)}", flush=True)
            finally:
                db2.close()
            # 3.5) 清掉模拟数据残留 + 拉真实球队名单（位置/号码/年龄/赛季数据）
            dbm = SessionLocal()
            try:
                print(f"[boot] purge mock: {espn.purge_mock_data(dbm)}", flush=True)
                print(f"[boot] rosters: {espn.sync_rosters(dbm)}", flush=True)
            except Exception as e:
                print(f"[boot] roster sync failed: {e}", flush=True)
            finally:
                dbm.close()
            # 4) Elo 更新后重算预测（否则胜率还是旧的均匀分布）
            dbp = SessionLocal()
            try:
                print(f"[boot] repredict: {rebuild_predictions(dbp)}", flush=True)
            finally:
                dbp.close()

            # 5) 周期轮询
            n = 0
            while True:
                time.sleep(settings.REAL_SYNC_INTERVAL)
                n += 1
                db3 = SessionLocal()
                try:
                    ret = espn.sync(db3, with_details=True)
                except Exception as e:
                    print(f"[espn] sync failed: {e}", flush=True)
                    ret = {}
                finally:
                    db3.close()
                # 每 12 轮（1 小时）用累积的真实赛果重算 Elo，
                # 否则整个赛季的强度都不会更新
                if n % 12 == 1:
                    dbe2 = SessionLocal()
                    try:
                        e2 = elo.recompute_elo(dbe2)
                    except Exception as e:
                        print(f"[elo] failed: {e}", flush=True)
                        e2 = {}
                    finally:
                        dbe2.close()
                    print(f"[elo] #{n}: {e2}", flush=True)
                try:
                    if ret.get("matches") or n % 12 == 1:
                        dbp2 = SessionLocal()
                        try:
                            rep = rebuild_predictions(dbp2)
                        finally:
                            dbp2.close()
                        if n % 5 == 0:
                            print(f"[espn] repredict#{n}: {rep}", flush=True)
                except Exception as e:
                    print(f"[espn] repredict failed: {e}", flush=True)
                if ret.get("matches") and n % 10 == 0:
                    print(f"[espn] sync#{n}: {ret}", flush=True)
                # 每 24 轮（2 小时）刷新一次球队名单：转会/号码变动不频繁，
                # 只刷少量重点球队，避免每轮打几百个请求
                if n % 24 == 5:
                    dbr = SessionLocal()
                    try:
                        rr = espn.sync_rosters(dbr, budget=60)
                    except Exception as e:
                        print(f"[espn] roster sync failed: {e}", flush=True)
                        rr = {}
                    finally:
                        dbr.close()
                    print(f"[espn] rosters#{n}: {rr}", flush=True)

        def _live_loop():
            """直播快车道：只刷进行中/即将开赛的比赛，20 秒一轮。

            全量 sync() 要拉 55 个源（约 25 秒），只能 5 分钟跑一次；
            比分靠它更新的话，看直播等于没有实时。这里只拉涉及的少数联赛，
            配合 5 秒一轮的 WS 广播，比分才会真的跳。
            """
            from app.ingest import espn

            time.sleep(15)  # 让首轮全量同步先跑
            while True:
                try:
                    time.sleep(settings.LIVE_SYNC_INTERVAL)
                    dbl = SessionLocal()
                    try:
                        r = espn.sync_live(dbl)
                    finally:
                        dbl.close()
                    if r.get("live") or r.get("error"):
                        print(f"[live] {r}", flush=True)
                except Exception as e:
                    print(f"[live] failed: {e}", flush=True)
                    time.sleep(30)

        threading.Thread(target=_sync_loop, daemon=True).start()
        threading.Thread(target=_live_loop, daemon=True).start()
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
