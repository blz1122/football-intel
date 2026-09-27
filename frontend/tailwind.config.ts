import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0a0e17",
        base2: "#0f1523",
        panel: "#121a2b",
        panel2: "#182238",
        line: "#1e2a44",
        line2: "#263554",
        txt: "#e8eefc",
        sub: "#8b98b8",
        accent: "#2f6bff",
        accent2: "#38bdf8",
        live: "#ff6b81",
        gold: "#f5b342",
        home: "#2f6bff",
        away: "#ff7a45",
      },
      fontFamily: {
        sans: ["Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
