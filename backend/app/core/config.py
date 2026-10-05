"""应用配置。开发环境默认 SQLite，生产可切换 PostgreSQL（见 docs/DATABASE_DESIGN.md）。"""
import os


class Settings:
    APP_NAME: str = "Football Intelligence API"
    VERSION: str = "0.2.0"

    # 开发默认 SQLite；生产: postgresql+psycopg://user:pass@host:5432/football_intel
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./football_intel.db"
    )

    # 前端开发地址
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")

    # 比赛实时参数（分钟 -> 现实分钟映射：中场休息压缩为 15 分钟）
    HALF_MINUTES: int = 45
    HALFTIME_BREAK: int = 15
    FULL_MINUTES: int = 90
    HOME_ADVANTAGE_ELO: float = 65.0

    # ---------------- Phase 4 ----------------
    # 数据源: mock（本地模拟引擎）| api_football（真实 API，需 API key）
    DATA_PROVIDER: str = os.getenv("DATA_PROVIDER", "mock")
    API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
    API_FOOTBALL_BASE: str = "https://v3.football.api-sports.io"

    # 真实数据接入（ESPN 公开接口，无需 API key）：开启后同步真实赛程/比分/统计
    REAL_DATA: bool = os.getenv("REAL_DATA", "1").lower() in ("1", "true", "yes")
    REAL_SYNC_INTERVAL: int = int(os.getenv("REAL_SYNC_INTERVAL", "300"))  # 秒
    # 直播快车道：只刷「进行中/即将开赛」的少数联赛，秒级跳动靠它
    LIVE_SYNC_INTERVAL: int = int(os.getenv("LIVE_SYNC_INTERVAL", "20"))  # 秒
    # 比赛列表的未来窗口（天）。欧冠/世预赛等常在 10 天后开赛，窗口太小会漏。
    MATCH_WINDOW_DAYS: int = int(os.getenv("MATCH_WINDOW_DAYS", "14"))
    # 单轮同步拉取比赛详情（summary）的数量上限
    ESPN_DETAIL_BUDGET: int = int(os.getenv("ESPN_DETAIL_BUDGET", "80"))
    # 启动/周期同步时拉取完整球队名单的球队数上限
    ESPN_ROSTER_BUDGET: int = int(os.getenv("ESPN_ROSTER_BUDGET", "180"))

    # WebSocket 推送间隔（秒）
    WS_PUSH_INTERVAL: float = float(os.getenv("WS_PUSH_INTERVAL", "5"))

    # 可选 LLM（OpenAI 兼容接口），未配置时 AI 报告使用内置数据驱动模板引擎
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


settings = Settings()
