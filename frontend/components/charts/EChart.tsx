"use client";
// ECharts 通用封装：init / resize / dispose + 主题常量
import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export const CHART_COLORS = {
  home: "#2f6bff",
  draw: "#5a6780",
  away: "#ff7a45",
  axis: "#263554",
  label: "#8b98b8",
  gold: "#f5b342",
  bg: "transparent",
};

export const baseOption: echarts.EChartsOption = {
  backgroundColor: CHART_COLORS.bg,
  textStyle: { color: CHART_COLORS.label, fontFamily: "Segoe UI, sans-serif" },
  grid: { left: 40, right: 16, top: 24, bottom: 28 },
  tooltip: {
    backgroundColor: "#182238",
    borderColor: "#263554",
    textStyle: { color: "#e8eefc", fontSize: 12 },
  },
};

export default function EChart({
  option,
  height = 240,
}: {
  option: echarts.EChartsOption;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }
    chartRef.current.setOption(option, true);
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, [option]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
