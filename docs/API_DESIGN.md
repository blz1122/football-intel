# API 接口设计（API_DESIGN）

> Base URL: `/api/v1` · REST JSON · 认证（Phase 5 引入 JWT）

## 1. 比赛

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/matches?date=2026-09-27&status=live&league_id=` | 比赛列表（今日/进行中/即将开始/历史，`status` 与 `date` 组合过滤） |
| GET | `/matches/{id}` | 比赛详情（含实时统计） |
| GET | `/matches/{id}/events` | 事件时间线 |
| GET | `/matches/{id}/statistics?minute=` | 分钟级统计（不传 minute 返回全序列） |
| GET | `/matches/{id}/lineups` | 首发与伤停 |

**响应示例** `GET /matches?status=live`：

```json
{
  "items": [{
    "id": 1024, "league": {"id": 1, "name": "Premier League", "logo_url": "..."},
    "kickoff_at": "2026-09-27T15:00:00Z", "status": "live", "minute": 65,
    "home_team": {"id": 10, "name": "Liverpool", "short_name": "LIV", "logo_url": "..."},
    "away_team": {"id": 11, "name": "Chelsea", "short_name": "CHE", "logo_url": "..."},
    "home_score": 1, "away_score": 0,
    "live_stats": {"possession_home": 58, "shots_home": 14, "shots_away": 7}
  }],
  "total": 1
}
```

## 2. 预测与模拟

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/predictions/{match_id}` | 赛前预测（胜平负概率 + λ + 置信度） |
| GET | `/predictions/{match_id}/history` | 预测回溯（多模型版本对比） |
| POST | `/simulate/{match_id}?simulations=10000` | 触发 Monte Carlo 模拟（幂等，返回缓存） |
| GET | `/win-probability/{match_id}/curve` | 实时胜率曲线点集 |

**响应示例** `GET /predictions/1024`：

```json
{
  "match_id": 1024, "model_version": "dc-xgb-v0.1",
  "p_home": 0.45, "p_draw": 0.30, "p_away": 0.25,
  "lambda_home": 1.82, "lambda_away": 1.10,
  "confidence": 0.72, "expected_score": "2-1",
  "factors": {"elo_diff": 42, "form_home": "WWDWW", "form_away": "WDWLW",
               "h2h": {"home_wins": 5, "draws": 2, "away_wins": 3}}
}
```

## 3. 球队 / 球员

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/teams/{id}` | 球队资料 + TPI 评级 |
| GET | `/teams/{id}/form?last=10` | 近 N 场趋势 |
| GET | `/teams/{id}/stats?season_id=` | 赛季汇总（xG/xGA/进攻防守分项） |
| GET | `/players/{id}` | 球员资料 + AI Rating |
| GET | `/players/{id}/stats?season_id=` | 球员赛季数据 |
| GET | `/search?q=manchester` | 全局搜索（球队/球员） |

## 4. 高阶分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/analytics/{match_id}/shotmap` | 射门地图（坐标 + xG 值） |
| GET | `/analytics/{match_id}/pass-network` | 传球网络 |
| GET | `/analytics/{match_id}/zones` | 进攻/压迫区域热力 |
| GET | `/analytics/teams/{id}/defense` | 防守成功率/抢断/拦截/压迫 |

## 5. AI 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/reports/{match_id}/preview` | 赛前 AI 报告（关键点/战术/风险） |
| GET | `/reports/{match_id}/review` | 赛后 AI 复盘 |

## 6. WebSocket

**连接**：`ws://<host>/ws/live`

**订阅协议**（JSON 文本帧）：

```json
{"action": "subscribe",   "match_ids": [1024, 1025]}
{"action": "unsubscribe", "match_ids": [1025]}
```

**推送类型**：

```json
{"type": "score",   "match_id": 1024, "minute": 66, "home_score": 2, "away_score": 0}
{"type": "event",   "match_id": 1024, "event": {"minute": 66, "type": "goal", "player": "..."}}
{"type": "winprob", "match_id": 1024, "minute": 66,
 "p_home": 0.91, "p_draw": 0.07, "p_away": 0.02, "trigger": "goal"}
{"type": "stats",   "match_id": 1024, "minute": 66, "stats": {"possession_home": 60}}
```

- 服务端每分钟推送 `winprob`；进球/红牌等事件即时触发重算推送
- 客户端心跳 `{"action":"ping"}` → `{"type":"pong"}`；断线自动重连（指数退避）

## 7. 错误格式

```json
{"error": {"code": "MATCH_NOT_FOUND", "message": "match 9999 not found", "status": 404}}
```

通用错误码：`MATCH_NOT_FOUND` / `MODEL_NOT_READY` / `PROVIDER_UNAVAILABLE` / `VALIDATION_ERROR`
