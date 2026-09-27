"use client";
// 全局布局：顶栏（Bloomberg 终端式导航）+ 移动端底部导航 + 深色主题
import Link from "next/link";
import { usePathname } from "next/navigation";
import LiveCount from "@/components/LiveCount";
import DataSource from "@/components/DataSource";
import "./globals.css";

const NAV = [
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/#scheduled", label: "比赛", icon: "⚽" },
  { href: "/teams", label: "球队", icon: "🛡️" },
  { href: "/players", label: "球员", icon: "👤" },
  { href: "/#top", label: "AI 预测", icon: "🤖" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-base font-sans text-txt antialiased">
        <header className="sticky top-0 z-10 flex h-14 items-center gap-6 border-b border-line bg-base2 px-4 md:px-6">
          <Link href="/" className="flex items-center gap-2.5 text-base font-extrabold tracking-wide">
            <span className="flex h-7 w-7 items-center justify-center rounded-full text-sm" style={{ background: "radial-gradient(circle at 30% 30%, #4d8dff, #1d3f9e)" }}>
              ⚽
            </span>
            FOOT<span className="text-accent2">INTEL</span>
          </Link>
          <nav className="hidden flex-1 gap-1 md:flex">
            {NAV.map((n, i) => {
              const active =
                (i === 0 && pathname === "/") ||
                (n.href !== "/" && !n.href.startsWith("/#") && pathname.startsWith(n.href));
              return (
                <Link
                  key={n.label}
                  href={n.href}
                  className={`rounded-md px-3.5 py-2 text-sm font-semibold transition-colors ${
                    active ? "bg-panel2 text-txt" : "text-sub hover:bg-panel2 hover:text-txt"
                  }`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <DataSource />
          <LiveCount />
        </header>
        <main className="mx-auto max-w-[1360px] px-3 pb-24 pt-5 md:px-6 md:pb-16">{children}</main>
        <footer className="hidden border-t border-line py-6 text-center text-[11px] text-sub md:block">
          <DataSource variant="footer" />
        </footer>

        {/* 移动端底部导航 */}
        <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-base2/95 backdrop-blur md:hidden">
          {NAV.map((n) => (
            <Link
              key={n.label}
              href={n.href}
              className="tap-target flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-semibold text-sub"
            >
              <span className="text-base leading-none">{n.icon}</span>
              {n.label}
            </Link>
          ))}
        </nav>
      </body>
    </html>
  );
}
