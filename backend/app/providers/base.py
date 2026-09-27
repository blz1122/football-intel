"""数据源 Provider 抽象接口。

Phase 1-3 的本地模拟引擎封装为 MockProvider；真实足球 API（api-football 等）
通过实现同一接口接入，路由层不感知数据来源，切换只需环境变量 DATA_PROVIDER。
"""
from abc import ABC, abstractmethod
from typing import Any


class FootballDataProvider(ABC):
    """足球数据源统一接口（v1：比赛 / 事件 / 实时统计）。"""

    name: str = "abstract"

    @abstractmethod
    def fixtures(self, days: int = 3) -> list[dict[str, Any]]:
        """近 N 日比赛列表（含进行中）。"""

    @abstractmethod
    def events(self, match_id: int) -> list[dict[str, Any]]:
        """比赛事件（进球/红黄牌/换人）。"""

    @abstractmethod
    def statistics(self, match_id: int) -> dict[str, Any] | None:
        """当前累计技术统计；未开赛返回 None。"""

    def healthcheck(self) -> dict[str, Any]:
        """数据源连通性/状态检查。"""
        return {"provider": self.name, "ok": True}
