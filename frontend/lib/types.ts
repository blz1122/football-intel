// API 类型定义 —— 与 backend/app/schemas.py 对齐

export interface TeamRadar {
  attack: number;
  defense: number;
  possession: number;
  pressing: number;
  efficiency: number;
  form: number;
}

export interface TeamBrief {
  id: number;
  name: string;
  name_en: string;
  short_name: string;
  color: string;
  elo_rating: number;
  tpi: number | null;
  radar: TeamRadar | null;
}

export interface LeagueBrief {
  id: number;
  name: string;
  short_name: string;
}

/** /meta/leagues 返回的完整联赛信息（支持洲际/国家队/国内分组） */
export interface LeagueInfo {
  id: number;
  name: string;
  short_name: string;
  name_en: string;
  country: string;
  competition_type: "continental" | "national" | "domestic";
  type_label: string;
  is_key: boolean;
  match_count: number;
}

export interface WinProb {
  home: number;
  draw: number;
  away: number;
}

export interface LiveStats {
  minute: number;
  possession_home: number;
  shots_home: number;
  shots_away: number;
  shots_on_target_home: number;
  shots_on_target_away: number;
  corners_home: number;
  corners_away: number;
  fouls_home: number;
  fouls_away: number;
  yellow_home: number;
  yellow_away: number;
  red_home: number;
  red_away: number;
  dangerous_home: number;
  dangerous_away: number;
  xg_home: number;
  xg_away: number;
}

export interface MatchListItem {
  id: number;
  league: LeagueBrief;
  round: string | null;
  kickoff_at: string;
  status: "scheduled" | "live" | "halftime" | "finished";
  period: string | null;
  minute: number | null;
  home_score: number;
  away_score: number;
  home_team: TeamBrief;
  away_team: TeamBrief;
  win_prob: WinProb;
  live_stats: LiveStats | null;
  is_hot: boolean;
}

export interface EventOut {
  minute: number;
  side: "home" | "away";
  type: "goal" | "yellow_card" | "red_card" | "substitution";
  player_id: number | null;
  player: string | null;
  related_player_id: number | null;
  related_player: string | null;
  detail: string | null;
  detail_cn?: string | null;
}

export interface PredictionOut {
  model_version: string;
  p_home: number;
  p_draw: number;
  p_away: number;
  lambda_home: number;
  lambda_away: number;
  confidence: number;
  expected_score: string;
  score_matrix: Record<string, number>;
}

export interface MatchDetail {
  match: MatchListItem;
  events: EventOut[];
  prediction: PredictionOut | null;
}

export interface CurvePoint {
  minute: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  trigger: string;
}

export interface ShotOut {
  x: number;
  y: number;
  xg: number;
  goal: boolean;
}

export interface ShotMap {
  home: ShotOut[];
  away: ShotOut[];
}

export interface Kpis {
  total_today: number;
  live_now: number;
  finished_today: number;
  accuracy_7d: number;
  brier_score: number;
}

export interface PredictionRankItem {
  match_id: number;
  title: string;
  pick: string;
  probability: number;
  kickoff_at: string;
}

// ---------------- Phase 3 ----------------

export interface MonteCarloOut {
  match_id: number;
  simulations: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  score_matrix: Record<string, number>;
  over_under: Record<string, number>;
  btts: number;
  model_version: string;
}

export interface PlayerBrief {
  id: number;
  name: string;
  name_en: string;
  position: string;
  number: number;
  ai_rating: number;
  season_stats: Record<string, number>;
}

export interface TeamProfile {
  id: number;
  name: string;
  name_en: string;
  short_name: string;
  color: string;
  league: LeagueBrief;
  elo_rating: number;
  stadium: string | null;
  tpi: number;
  radar: TeamRadar;
  breakdown: {
    form_last10?: string[];
    season?: Record<string, number>;
  };
  squad: PlayerBrief[];
}

export interface PlayerProfile {
  id: number;
  name: string;
  name_en: string;
  position: string;
  number: number;
  age: number;
  team: TeamBrief;
  ai_rating: number;
  season_stats: Record<string, number>;
}

// ---------------- 列表页 ----------------

export interface TeamListItem {
  id: number;
  name: string;
  name_en: string;
  short_name: string;
  color: string;
  elo_rating: number;
  stadium: string | null;
  league: LeagueBrief;
  tpi: number | null;
}

export interface PlayerListItem {
  id: number;
  name: string;
  name_en: string;
  position: string;
  number: number;
  age: number;
  ai_rating: number;
  season_stats: Record<string, number>;
  team_id: number;
  team_name: string;
  team_short: string;
  team_color: string;
  league_short: string;
}
