"use client";
// 全局布局：顶栏（Bloomberg 终端式导航）+ 深色主题
import Link from "next/link";
import LiveCount from "@/components/LiveCount";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-base font-sans text-txt antialiased">
        <header className="sticky top-0 z-10 flex h-14 items-center gap-6 border-b border-line bg-base2 px-6">
          <Link href="/" className="flex items-center gap-2.5 text-base font-extrabold tracking-wide">
            <span className="flex h-7 w-7 items-center justify-center rounded-full text-sm" style={{ background: "radial-gradient(circle at 30% 30%, #4d8dff, #1d3f9e)" }}>
              ⚽
            </span>
            FOOT<span className="text-accent2">INTEL</span>
          </Link>
          <nav className="hidden flex-1 gap-1 md:flex">
            {["Dashboard", "比赛", "球队", "球员", "AI 预测", "模拟器"].map((t, i) => (
              <Link
                key={t}
                href={i === 0 ? "/" : "#"}
                className={`rounded-md px-3.5 py-2 text-sm font-semibold ${i === 0 ? "bg-panel2 text-txt" : "text-sub hover:bg-panel2 hover:text-txt"}`}
              >
                {t}
              </Link>
            ))}
          </nav>
          <LiveCount />
        </header>
        <main className="mx-auto max-w-[1360px] px-6 pb-16 pt-5">{children}</main>
      </body>
    </html>
  );
}
