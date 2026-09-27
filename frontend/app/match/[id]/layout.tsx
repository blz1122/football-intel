// 静态导出壳：桌面版 next build（output=export）需要动态段预生成参数。
// 页面本身是客户端组件、按 URL 参数拉数据，这里仅声明参数域。
export function generateStaticParams() {
  // 种子比赛 id 为自增整数，1..300 覆盖充足；导出的是纯加载壳（几 KB/页）
  return Array.from({ length: 300 }, (_, i) => ({ id: String(i + 1) }));
}

export default function MatchLayout({ children }: { children: React.ReactNode }) {
  return children;
}
