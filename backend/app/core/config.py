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


settings = Settings()
