"""数据库连接与会话管理。"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite 需要关闭同线程检查以配合 FastAPI 线程池
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 新增列（真实数据源支持）在既有库上需要 ALTER，SQLite/PostgreSQL 通用
_EXTRA_COLUMNS: dict[str, dict[str, str]] = {
    "matches": {
        "provider": "VARCHAR(16) DEFAULT 'mock'",
        "provider_event_id": "VARCHAR(40)",
        "status_override": "VARCHAR(12)",
        "minute_override": "SMALLINT",
        "score_home": "SMALLINT",
        "score_away": "SMALLINT",
        "stats_json": "JSON",
        "is_history": "BOOLEAN DEFAULT 0",
    },
    "teams": {
        "provider": "VARCHAR(16) DEFAULT 'mock'",
        "provider_team_id": "VARCHAR(40)",
    },
    "players": {
        "provider": "VARCHAR(16) DEFAULT 'mock'",
    },
    "leagues": {
        "competition_type": "VARCHAR(24) DEFAULT 'domestic'",
        "is_key": "BOOLEAN DEFAULT 0",
    },
}


def ensure_schema() -> None:
    """为已存在的库补齐新增列（幂等，缺失才 ALTER）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _EXTRA_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        # seasons 的 start/end_date 是 NOT NULL：历史遗留的空值补齐
        if "seasons" in tables:
            conn.execute(
                text(
                    "UPDATE seasons SET start_date='2026-07-01', end_date='2027-06-30' "
                    "WHERE start_date IS NULL OR end_date IS NULL"
                )
            )
