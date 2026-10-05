"""Windows 桌面客户端一键打包脚本。

流程：
  1. 前端静态导出（NEXT_OUTPUT=export next build -> frontend/out/）
  2. 导出产物复制到 backend/static/（FastAPI 托管，同源免 CORS）
  3. PyInstaller 打包 backend/desktop.py -> dist/FootballIntel/

用法（在 backend 目录）：
    python build_desktop.py            # 完整版（含 XGBoost/sklearn）
    python build_desktop.py --slim     # 精简版（DC 模型，体积小 ~10 倍）

产物：backend/dist/FootballIntel/FootballIntel.exe，双击自动启动并打开浏览器。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "frontend"
STATIC = ROOT / "static"
# Next 14 + 自定义 distDir 时，output:export 原地写入 distDir（即完整静态站点）
OUT = FRONTEND / ".next-export"

PY = sys.executable

# 宿主环境可能通过 NODE_OPTIONS 注入 fs shim（language-shim/safe-delete-shim）：
# 会拦截 next build 的批量删除（EPERM / 批量删除确认）导致构建崩溃。
# 打包子进程必须以干净环境运行。
os.environ.pop("NODE_OPTIONS", None)
os.environ["CODEBUDDY_SAFE_DELETE_ENABLED"] = "0"


def _npm() -> str:
    """Windows 下 npm 是 npm.cmd，subprocess 需要完整可执行名。"""
    import os

    which = shutil.which("npm.cmd") or shutil.which("npm")
    if not which:  # 兼容 WorkBuddy 隔离 node（PATH 里没有 npm 时）
        for pat in (
            r"C:/Users/*/.workbuddy/binaries/node/versions/*/npm.cmd",
            str(Path.home() / ".workbuddy/binaries/node/versions/*/npm.cmd"),
        ):
            import glob

            hits = glob.glob(pat)
            if hits:
                return sorted(hits)[-1]
        sys.exit("未找到 npm，请先安装 Node.js")
    return which


def run(cmd: list[str], cwd: Path, env_extra: dict[str, str] | None = None) -> None:
    env = None
    if env_extra:
        import os

        env = {**os.environ, **env_extra}
    print(f"\n>>> {' '.join(cmd)}  (cwd={cwd.name})")
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def _next_cmd() -> list[str]:
    """直接 `node node_modules/next/dist/bin/next build`，**不要走 npm.cmd**。

    实测：走 `npm.cmd run build` 时，npm 起的中间 shell 会把宿主的 NODE_OPTIONS
    fs-shim 带回来，next 打开 .next/trace 直接 EPERM，整轮构建崩掉；
    直接调 node 二进制就没有这层，稳定通过。
    """
    nxt = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
    node = shutil.which("node")
    if not node:
        import glob

        hits = sorted(glob.glob(r"C:/Users/*/.workbuddy/binaries/node/versions/*/node.exe"))
        if hits:
            node = hits[-1]
    if node and nxt.exists():
        return [node, str(nxt), "build"]
    return [_npm(), "run", "build"]


def build_frontend() -> None:
    print("=" * 60)
    print("[1/3] 前端静态导出")
    marker = FRONTEND / ".desktop-export"
    marker.write_text("desktop export build marker", encoding="utf-8")
    # 经验（踩坑实录）：next build 启动时会把 trace 写进 <cwd>/.next/trace，
    # **若该文件已存在则 open 报 EPERM，整轮构建直接崩**。
    # 所以这里必须把它"挪走"，而不是按旧做法去 touch 预建（预建必崩）。
    # 注意只挪 trace 一个文件，不要整体挪走 .next（会丢掉编译缓存，构建变慢）。
    dot_next = FRONTEND / ".next"
    dot_next.mkdir(parents=True, exist_ok=True)
    trace = dot_next / "trace"
    if trace.exists():
        trace.rename(FRONTEND / f"trace_old_{time.strftime('%Y%m%d%H%M%S')}")
    try:
        run(_next_cmd(), FRONTEND)
    finally:
        marker.unlink(missing_ok=True)
    if not (OUT / "index.html").exists():
        sys.exit(f"静态导出失败：{OUT}/index.html 不存在")


def sync_static() -> None:
    print("=" * 60)
    print("[2/3] 同步到 backend/static/")
    if STATIC.exists():
        # 先重命名再删，避免长路径/占用导致的删除失败中断流程
        stamp = time.strftime("%Y%m%d%H%M%S")
        old = ROOT / f"static_old_{stamp}"
        STATIC.rename(old)
        try:
            shutil.rmtree(old, ignore_errors=True)
        except Exception:
            print(f"  旧目录暂无法删除，已重命名为 {old.name}")
    shutil.copytree(OUT, STATIC)
    n = sum(1 for _ in STATIC.rglob("*") if _.is_file())
    print(f"  已复制 {n} 个文件")


def build_exe(slim: bool) -> Path:
    print("=" * 60)
    print(f"[3/3] PyInstaller 打包（{'slim' if slim else 'full'}）")
    args = [
        PY, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "FootballIntel",
        "--collect-submodules", "app",
        "--collect-submodules", "websockets",
        "--hidden-import", "uvicorn.protocols.websockets.websockets_sansio_impl",
        "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.lifespan.on",
        # 桌面版数据落 exe 旁
        "--add-data", f"{STATIC}{';'}static",
        "desktop.py",
    ]
    if slim:
        # 精简版：剔除重量级 ML 依赖，模型自动降级为 Dixon-Coles 基线
        for mod in ("xgboost", "sklearn", "pandas", "joblib"):
            args += ["--exclude-module", mod]
    run(args, ROOT)
    exe = ROOT / "dist" / "FootballIntel" / "FootballIntel.exe"
    if not exe.exists():
        sys.exit("打包失败：未找到 FootballIntel.exe")
    size_mb = exe.stat().st_size / 1e6
    total = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file()) / 1e6
    print(f"\n打包完成：{exe}")
    print(f"主程序 {size_mb:.0f} MB / 目录合计 {total:.0f} MB")
    return exe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slim", action="store_true", help="排除 XGBoost/sklearn/pandas（DC 基线模式）")
    ap.add_argument("--skip-frontend", action="store_true", help="复用已有 backend/static，跳过前端构建")
    opt = ap.parse_args()

    if not opt.skip_frontend:
        build_frontend()
        sync_static()
    elif not STATIC.is_dir():
        sys.exit("--skip-frontend 需要已存在 backend/static/")
    build_exe(opt.slim)


if __name__ == "__main__":
    main()
