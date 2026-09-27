import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 桌面版打包检测：build_desktop.py 会在构建前放置标记文件（比环境变量跨 shell 更可靠）
const EXPORT_MARKER = path.join(__dirname, ".desktop-export");
const isExport = fs.existsSync(EXPORT_MARKER);
const isStandalone = process.env.NEXT_OUTPUT === "standalone";

const nextConfig = {
  reactStrictMode: true,
  // Phase 5: standalone=Docker 生产；export=Windows 桌面静态导出（FastAPI 托管）
  output: isStandalone ? "standalone" : isExport ? "export" : undefined,
  ...(isExport
    ? {
        // 独立 distDir + 目录式输出（/match/2/index.html），配合 FastAPI StaticFiles
        distDir: ".next-export",
        trailingSlash: true,
      }
    : {
        async rewrites() {
          // 开发/生产通用：后端地址通过环境变量注入（Docker 中为 http://backend:8000）
          const backend = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
          return [
            { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
          ];
        },
      }),
};

export default nextConfig;
