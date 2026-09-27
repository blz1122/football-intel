"""进程内 TTL 缓存：线程安全、带命中率统计。

用于热点接口（比赛列表 / Monte Carlo / 报告）的短周期缓存，
降低模拟引擎的重复计算；生产可平滑替换为 Redis（接口一致）。
"""
import threading
import time


class TTLCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires, value = item
            if expires < time.monotonic():
                del self._data[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value, ttl: float) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._data),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
            }


cache = TTLCache()


def cached(key: str, ttl: float, producer):
    """读取缓存；未命中时调用 producer() 生成并写入。"""
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = producer()
    cache.set(key, value, ttl)
    return value
