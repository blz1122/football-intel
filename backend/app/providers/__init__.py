"""Provider 工厂：按环境变量 DATA_PROVIDER 选择数据源。

    DATA_PROVIDER=mock            本地确定性模拟引擎（默认，零依赖演示）
    DATA_PROVIDER=api_football    真实数据（需 API_FOOTBALL_KEY）
"""
from app.core.config import settings
from app.providers.base import FootballDataProvider


def get_provider() -> FootballDataProvider:
    if settings.DATA_PROVIDER == "api_football":
        from app.providers.api_football_provider import ApiFootballProvider

        return ApiFootballProvider()
    from app.core.db import SessionLocal
    from app.providers.mock_provider import MockProvider

    return MockProvider(lambda: SessionLocal())
