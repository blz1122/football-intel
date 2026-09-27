"""Windows 桌面客户端入口。

将前端静态导出（backend/static/）与 FastAPI 合体为单进程应用：
启动本地服务 -> 自动打开系统默认浏览器。

    python desktop.py            # 默认 127.0.0.1:8000
    python desktop.py 8123

PyInstaller 打包见 build_desktop.py；打包后的 exe 双击即用，
无需安装 Python / Node / 任何依赖。
"""
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
HOST = "127.0.0.1"


def _wait_and_open() -> None:
    """轮询健康检查，服务就绪后打开浏览器。"""
    import urllib.request

    url = f"http://{HOST}:{PORT}/api/v1/health"
    for _ in range(120):  # 最长等 60 秒（含 ML 模型训练）
        try:
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(f"http://{HOST}:{PORT}/")


def main() -> None:
    # PyInstaller 冻结环境下保证相对路径可用（SQLite 库文件落在 exe 旁）
    if getattr(sys, "frozen", False):
        import os

        os.chdir(Path(sys.executable).parent)

    threading.Thread(target=_wait_and_open, daemon=True).start()
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        ws="websockets-sansio",
        log_level="warning",
    )


if __name__ == "__main__":
    main()
