// 静态导出壳：球员 id 1..1300（64 队 × 18 人 = 1152）
export function generateStaticParams() {
  return Array.from({ length: 1300 }, (_, i) => ({ id: String(i + 1) }));
}

export default function PlayerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
