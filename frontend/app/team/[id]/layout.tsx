// 静态导出壳：球队 id 1..64（5 联赛 × 64 队）
export function generateStaticParams() {
  return Array.from({ length: 64 }, (_, i) => ({ id: String(i + 1) }));
}

export default function TeamLayout({ children }: { children: React.ReactNode }) {
  return children;
}
