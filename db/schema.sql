-- ============================================================
-- AI Football Intelligence Platform · PostgreSQL Schema v0.1
-- Phase 1 · 数据库设计
-- 执行: psql -U postgres -d football_intel -f schema.sql
-- ============================================================

-- CREATE DATABASE football_intel;  -- 如需单独建库请先执行

-- ---------- 维度表 ----------

CREATE TABLE IF NOT EXISTS leagues (
    id            BIGSERIAL PRIMARY KEY,
    provider      TEXT NOT NULL DEFAULT 'internal',
    provider_id   TEXT,
    name          TEXT NOT NULL,
    country       TEXT NOT NULL,
    tier          SMALLINT NOT NULL DEFAULT 1,
    logo_url      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_id)
);

CREATE TABLE IF NOT EXISTS seasons (
    id            BIGSERIAL PRIMARY KEY,
    league_id     BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,                -- 例: 2025/26
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    is_current    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS teams (
    id            BIGSERIAL PRIMARY KEY,
    provider      TEXT NOT NULL DEFAULT 'internal',
    provider_id   TEXT,
    name          TEXT NOT NULL,
    short_name    TEXT,                         -- 例: MCI
    country       TEXT,
    logo_url      TEXT,
    stadium       TEXT,
    fifa_ranking  SMALLINT,
    elo_rating    NUMERIC(7,1),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_id)
);

CREATE TABLE IF NOT EXISTS players (
    id              BIGSERIAL PRIMARY KEY,
    team_id         BIGINT REFERENCES teams(id) ON DELETE SET NULL,
    provider        TEXT NOT NULL DEFAULT 'internal',
    provider_id     TEXT,
    name            TEXT NOT NULL,
    position        TEXT CHECK (position IN ('GK','DF','MF','FW')),
    nationality     TEXT,
    birth_date      DATE,
    preferred_foot  TEXT CHECK (preferred_foot IN ('left','right','both')),
    height_cm       SMALLINT,
    market_value    NUMERIC(14,2),
    status          TEXT NOT NULL DEFAULT 'normal'
                    CHECK (status IN ('normal','injured','suspended')),
    injury_note     TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_id)
);

-- ---------- 比赛（事实）表 ----------

CREATE TABLE IF NOT EXISTS matches (
    id              BIGSERIAL PRIMARY KEY,
    provider        TEXT NOT NULL DEFAULT 'internal',
    provider_id     TEXT,
    league_id       BIGINT NOT NULL REFERENCES leagues(id),
    season_id       BIGINT NOT NULL REFERENCES seasons(id),
    home_team_id    BIGINT NOT NULL REFERENCES teams(id),
    away_team_id    BIGINT NOT NULL REFERENCES teams(id),
    kickoff_at      TIMESTAMPTZ NOT NULL,
    venue           TEXT,
    status          TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled','live','halftime','finished','postponed','cancelled')),
    minute          SMALLINT,                   -- 进行中分钟数(含伤停补时标记)
    period          TEXT CHECK (period IN ('1H','2H','HT','FT','ET','PEN')),
    home_score      SMALLINT NOT NULL DEFAULT 0,
    away_score      SMALLINT NOT NULL DEFAULT 0,
    round           TEXT,                       -- 例: Regular Season - 8
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_id)
);
CREATE INDEX IF NOT EXISTS idx_matches_kickoff ON matches (kickoff_at);
CREATE INDEX IF NOT EXISTS idx_matches_status  ON matches (status);
CREATE INDEX IF NOT EXISTS idx_matches_teams   ON matches (home_team_id, away_team_id);

CREATE TABLE IF NOT EXISTS match_events (
    id                BIGSERIAL PRIMARY KEY,
    match_id          BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL DEFAULT 'internal',
    provider_event_id TEXT,
    minute            SMALLINT NOT NULL,
    extra_minute      SMALLINT,                 -- 补时分钟
    team_id           BIGINT REFERENCES teams(id),
    player_id         BIGINT REFERENCES players(id),
    related_player_id BIGINT REFERENCES players(id),  -- 换人: 被换下者; 助攻者等
    type              TEXT NOT NULL CHECK (type IN
                      ('goal','own_goal','penalty_goal','missed_penalty',
                       'yellow_card','red_card','yellow_red','substitution',
                       'var','period_start','period_end')),
    detail            TEXT,                     -- 例: "左脚远射", assist 信息
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS idx_events_match ON match_events (match_id, minute);

-- 分钟级实时统计（一条 = 某分钟的统计快照）
CREATE TABLE IF NOT EXISTS match_statistics (
    match_id          BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    minute            SMALLINT NOT NULL,
    possession_home   SMALLINT CHECK (possession_home BETWEEN 0 AND 100),
    shots_home        SMALLINT, shots_away        SMALLINT,
    shots_on_target_home SMALLINT, shots_on_target_away SMALLINT,
    corners_home      SMALLINT, corners_away      SMALLINT,
    fouls_home        SMALLINT, fouls_away        SMALLINT,
    yellow_cards_home SMALLINT, yellow_cards_away SMALLINT,
    red_cards_home    SMALLINT, red_cards_away    SMALLINT,
    dangerous_attacks_home SMALLINT, dangerous_attacks_away SMALLINT,
    xg_home           NUMERIC(5,2), xg_away       NUMERIC(5,2),
    PRIMARY KEY (match_id, minute)
);

-- 球队单场汇总（赛后定稿）
CREATE TABLE IF NOT EXISTS team_match_stats (
    id                  BIGSERIAL PRIMARY KEY,
    match_id            BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id             BIGINT NOT NULL REFERENCES teams(id),
    possession          SMALLINT,
    shots               SMALLINT,
    shots_on_target     SMALLINT,
    shots_inside_box    SMALLINT,
    shots_outside_box   SMALLINT,
    corners             SMALLINT,
    fouls               SMALLINT,
    yellow_cards        SMALLINT,
    red_cards           SMALLINT,
    offsides            SMALLINT,
    passes              SMALLINT,
    pass_accuracy       NUMERIC(5,2),
    tackles             SMALLINT,
    interceptions       SMALLINT,
    duels_won           SMALLINT,
    saves               SMALLINT,
    xg                  NUMERIC(5,2),
    xga                 NUMERIC(5,2),
    UNIQUE (match_id, team_id)
);

-- 球员单场数据
CREATE TABLE IF NOT EXISTS player_match_stats (
    id              BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id       BIGINT NOT NULL REFERENCES players(id),
    team_id         BIGINT NOT NULL REFERENCES teams(id),
    started         BOOLEAN NOT NULL DEFAULT FALSE,
    minutes_played  SMALLINT,
    rating          NUMERIC(4,1),               -- 平台评分 0-10
    goals           SMALLINT DEFAULT 0,
    assists         SMALLINT DEFAULT 0,
    shots           SMALLINT DEFAULT 0,
    shots_on_target SMALLINT DEFAULT 0,
    xg              NUMERIC(4,2),
    xa              NUMERIC(4,2),
    passes          SMALLINT DEFAULT 0,
    pass_accuracy   NUMERIC(5,2),
    key_passes      SMALLINT DEFAULT 0,
    tackles         SMALLINT DEFAULT 0,
    interceptions   SMALLINT DEFAULT 0,
    duels_won       SMALLINT DEFAULT 0,
    yellow_cards    SMALLINT DEFAULT 0,
    red_cards       SMALLINT DEFAULT 0,
    UNIQUE (match_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_pms_player ON player_match_stats (player_id);

-- ---------- 模型产物表 ----------

CREATE TABLE IF NOT EXISTS match_predictions (
    id               BIGSERIAL PRIMARY KEY,
    match_id         BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    model_version    TEXT NOT NULL,             -- 例: dc-xgb-v0.1
    p_home           NUMERIC(5,4) NOT NULL,
    p_draw           NUMERIC(5,4) NOT NULL,
    p_away           NUMERIC(5,4) NOT NULL,
    lambda_home      NUMERIC(5,2),              -- 泊松强度
    lambda_away      NUMERIC(5,2),
    confidence       NUMERIC(4,3),              -- 模型置信度 0-1
    expected_score   TEXT,                      -- 例: 2-1
    feature_snapshot JSONB,                     -- 特征留档用于回溯
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, model_version)
);

-- 实时胜率快照（概率曲线数据源）
CREATE TABLE IF NOT EXISTS win_probability_snapshots (
    match_id   BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    minute     SMALLINT NOT NULL,
    p_home     NUMERIC(5,4) NOT NULL,
    p_draw     NUMERIC(5,4) NOT NULL,
    p_away     NUMERIC(5,4) NOT NULL,
    trigger    TEXT NOT NULL DEFAULT 'minute'
               CHECK (trigger IN ('minute','goal','card','substitution','xg')),
    model_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (match_id, minute)
);

CREATE TABLE IF NOT EXISTS monte_carlo_results (
    id            BIGSERIAL PRIMARY KEY,
    match_id      BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    simulations   INTEGER NOT NULL DEFAULT 10000,
    score_matrix  JSONB NOT NULL,               -- {"1-0":0.23,"1-1":0.18,...}
    p_home        NUMERIC(5,4) NOT NULL,
    p_draw        NUMERIC(5,4) NOT NULL,
    p_away        NUMERIC(5,4) NOT NULL,
    over_under    JSONB,                        -- {"0.5":..., "1.5":..., "2.5":...}
    btts          NUMERIC(5,4),                 -- 双方均进球概率
    model_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, model_version)
);

-- Team Power Index 历史
CREATE TABLE IF NOT EXISTS team_ratings (
    id          BIGSERIAL PRIMARY KEY,
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tpi         NUMERIC(5,2) NOT NULL,          -- 综合分 0-100
    attack      NUMERIC(5,2),
    defense     NUMERIC(5,2),
    form        NUMERIC(5,2),                   -- 近10场状态
    home_bonus  NUMERIC(5,2),
    breakdown   JSONB                           -- 明细: 进球/xG/射门效率…
);

-- 交锋史缓存
CREATE TABLE IF NOT EXISTS head_to_head (
    id            BIGSERIAL PRIMARY KEY,
    team_a_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    team_b_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    total_matches INTEGER NOT NULL DEFAULT 0,
    a_wins        INTEGER NOT NULL DEFAULT 0,
    draws         INTEGER NOT NULL DEFAULT 0,
    b_wins        INTEGER NOT NULL DEFAULT 0,
    a_goals       INTEGER NOT NULL DEFAULT 0,
    b_goals       INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_a_id, team_b_id)
);

COMMENT ON TABLE match_predictions           IS '赛前预测: Dixon-Coles + XGBoost 融合输出';
COMMENT ON TABLE win_probability_snapshots   IS '比赛中动态胜率, 每分钟/关键事件一行, 供概率曲线';
COMMENT ON TABLE monte_carlo_results.score_matrix IS '10k次模拟的比分概率分布(JSONB)';
