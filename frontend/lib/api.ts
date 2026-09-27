// REST 客户端：开发环境走 next.config.mjs 的 rewrite 代理到 FastAPI
const BASE = "/api/v1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  matches: (status?: string) =>
    get<import("./types").MatchListItem[]>(
      `/matches${status ? `?status=${status}` : ""}`
    ),
  matchDetail: (id: number) => get<import("./types").MatchDetail>(`/matches/${id}`),
  statsSeries: (id: number) => get<Record<string, number>[]>(`/matches/${id}/statistics`),
  winProbCurve: (id: number) => get<import("./types").CurvePoint[]>(`/matches/${id}/win-probability/curve`),
  shotMap: (id: number) => get<import("./types").ShotMap>(`/matches/${id}/shotmap`),
  kpis: () => get<import("./types").Kpis>(`/meta/kpis`),
  topPredictions: () => get<import("./types").PredictionRankItem[]>(`/meta/predictions/top`),
  leagues: () => get<{ id: number; name: string; short_name: string }[]>(`/meta/leagues`),
  monteCarlo: (id: number, n = 10000) =>
    get<import("./types").MonteCarloOut>(`/matches/${id}/monte-carlo?simulations=${n}`),
  teamProfile: (id: number) => get<import("./types").TeamProfile>(`/teams/${id}`),
  playerProfile: (id: number) => get<import("./types").PlayerProfile>(`/players/${id}`),
  tpiLeaderboard: (leagueId?: number) =>
    get<Record<string, unknown>[]>(`/leaderboard/tpi${leagueId ? `?league_id=${leagueId}` : ""}`),
};
