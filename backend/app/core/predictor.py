"""预测模型（Phase 2 轻量版）：
- 赛前：Elo 差 -> 进球强度 λ -> 泊松比分矩阵 -> 胜平负概率
- 实时：剩余时间强度缩放 + 当前比分 -> 动态胜率
Phase 3 将升级为 Dixon-Coles 修正 + XGBoost 融合（见 docs/ARCHITECTURE.md §3）。
"""
import math

import numpy as np

TOTAL_GOALS_BASE = 2.65  # 联赛场均总进球先验
GRID = 8  # 单队最大进球数


def _poisson_pmf(lam: float, n: int = GRID) -> np.ndarray:
    """手写泊松 pmf，避免引入 scipy。"""
    p = np.empty(n + 1)
    p[0] = math.exp(-lam)
    for k in range(1, n + 1):
        p[k] = p[k - 1] * lam / k
    return p / p.sum()


def _grid_probs(lh: float, la: float) -> tuple[float, float, float, str, dict]:
    ph = _poisson_pmf(lh)
    pa = _poisson_pmf(la)
    m = np.outer(ph, pa)  # m[i][j] = 主队进i球 客队进j球
    p_home = float(np.tril(m, -1).sum())  # i > j
    p_draw = float(np.trace(m))
    p_away = float(np.triu(m, 1).sum())
    i, j = np.unravel_index(np.argmax(m), m.shape)
    matrix = {
        f"{a}-{b}": round(float(m[a][b]), 4)
        for a in range(5)
        for b in range(5)
        if m[a][b] >= 0.005
    }
    return p_home, p_draw, p_away, f"{i}-{j}", matrix


def prematch(
    elo_home: float, elo_away: float, home_advantage: float = 65.0
) -> dict:
    """Elo -> 期望进球强度 -> 胜平负概率与比分矩阵。"""
    diff = (elo_home + home_advantage - elo_away) / 400.0
    # 胜率期望映射到进球强度分配：强队分走更多期望进球
    share = 1 / (1 + math.exp(-diff * 4.0))  # 0.5 中性
    lam_home = TOTAL_GOALS_BASE * share
    lam_away = TOTAL_GOALS_BASE * (1 - share)
    p_home, p_draw, p_away, exp_score, matrix = _grid_probs(lam_home, lam_away)
    top = max(p_home, p_draw, p_away)
    confidence = round(
        min(0.95, 0.4 + (top - 1 / 3) * 1.6), 3
    )  # 置信度启发式
    return {
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
        "lambda_home": round(lam_home, 2),
        "lambda_away": round(lam_away, 2),
        "confidence": confidence,
        "expected_score": exp_score,
        "score_matrix": matrix,
    }


def inmatch(
    minute: int,
    home_score: int,
    away_score: int,
    lam_home_full: float,
    lam_away_full: float,
    total_minutes: int = 90,
) -> dict:
    """动态胜率：以剩余时间缩放强度，剩余进球与当前比分叠加后查比分矩阵。"""
    rem = max(total_minutes - minute, 0)
    if rem == 0:
        if home_score > away_score:
            return {"p_home": 1.0, "p_draw": 0.0, "p_away": 0.0}
        if home_score < away_score:
            return {"p_home": 0.0, "p_draw": 0.0, "p_away": 1.0}
        return {"p_home": 0.0, "p_draw": 1.0, "p_away": 0.0}
    frac = rem / total_minutes
    lh = max(lam_home_full * frac, 0.02)
    la = max(lam_away_full * frac, 0.02)
    ph = _poisson_pmf(lh)
    pa = _poisson_pmf(la)
    m = np.outer(ph, pa)
    n = m.shape[0]
    p_home = p_draw = p_away = 0.0
    for i in range(n):
        for j in range(n):
            f, a = home_score + i, away_score + j
            if f > a:
                p_home += m[i][j]
            elif f == a:
                p_draw += m[i][j]
            else:
                p_away += m[i][j]
    return {
        "p_home": round(float(p_home), 4),
        "p_draw": round(float(p_draw), 4),
        "p_away": round(float(p_away), 4),
    }
