"""统一启动脚本。

    python run.py            # 默认 8000 端口
    python run.py 9000

说明：
1. 使用 websockets-sansio 实现（uvicorn 的旧版 websockets 实现已被标记废弃）。
2. WS 广播任务由首个 WebSocket 连接触发启动（见 app/ws.py
   ensure_broadcast_task）——lifespan 中创建的任务调用 send_text 会静默丢帧。
"""
import sys

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        ws="websockets-sansio",
    )
