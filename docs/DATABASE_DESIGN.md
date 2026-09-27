# 数据库设计（DATABASE_DESIGN）

> PostgreSQL 16 · 遵循第三范式，事实表适度反范式以便实时查询
> 完整 DDL 见 [`db/schema.sql`](../db/schema.sql)

## ER 概览

```
leagues 1──* seasons 1──* matches *──1 teams(Home/Away)
                              │
                              ├──* match_events     (进球/红黄牌/换人…)
                              ├──* match_statistics (分钟级统计)
                              ├──* win_probability_snapshots (胜率快照)
                              └──1 match_predictions (赛前预测)
teams 1──* team_match_stats   (球队单场技术统计)
teams 1──* team_ratings       (TPI 评级历史)
players *──1 teams
players 1──* player_match_stats (球员单场数据)
matches 1──* monte_carlo_results (模拟结果)
```

## 表清单

| 表 | 说明 | 关键字段 |
|----|------|----------|
| `leagues` | 联赛 | name, country, tier, logo_url |
| `seasons` | 赛季 | league_id, start/end date, is_current |
| `teams` | 球队 | name, short_name, logo_url, fifa_ranking, elo_rating |
| `players` | 球员 | team_id, position, preferred_foot, market_value, status(normal/injured/suspended) |
| `matches` | 比赛 | league_id, season_id, home/away_team_id, kickoff, status(scheduled/live/finished), minute, home/away_score |
| `match_events` | 比赛事件 | match_id, minute, type(goal/card/substitution/var…), team_id, player_id, detail |
| `match_statistics` | 分钟级统计 | match_id, minute, possession, shots, shots_on_target, corners, fouls, dangerous_attacks, xg_home/away |
| `team_match_stats` | 球队单场汇总 | match_id, team_id, 全量技术统计 + xG/xGA |
| `player_match_stats` | 球员单场数据 | match_id, player_id, rating, goals, assists, xg, xa, passes, tackles, interceptions |
| `match_predictions` | 赛前预测 | match_id, model_version, p_home/p_draw/p_away, lambda_home/away, confidence, feature_snapshot(JSONB) |
| `win_probability_snapshots` | 实时胜率快照 | match_id, minute, p_home/p_draw/p_away, trigger(event/minute) |
| `monte_carlo_results` | 模拟结果 | match_id, simulations, score_matrix(JSONB), over_under(JSONB), btts_p |
| `team_ratings` | TPI 历史 | team_id, computed_at, attack/defense/form/tpi(JSONB 各维度) |
| `head_to_head` | 交锋史缓存 | home/away team, matches, wins/draws/losses, goals |

## 设计要点

1. **JSONB 用于模型产物**：比分矩阵、特征快照等结构灵活的数据用 JSONB 存储，
   避免 10,000 次模拟逐行落库；核心标量（胜平负概率）仍单独成列便于索引查询。
2. **幂等键**：`match_events(provider, provider_event_id)` 唯一，防止重复拉取。
3. **时间序列索引**：`match_statistics(match_id, minute)`、
   `win_probability_snapshots(match_id, minute)` 复合主键，支持概率曲线直接按范围扫描。
4. **模型版本化**：`match_predictions.model_version` 记录模型版本，支持 A/B 与回溯评估。
5. **枚举用 TEXT + CHECK**：避免迁移时的枚举类型锁表问题。
6. **外键级联**：比赛删除时级联清理事件/统计/预测，保证数据一致性。
