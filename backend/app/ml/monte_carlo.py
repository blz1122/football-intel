"""Monte Carlo 比赛模拟（Phase 3）：从 Dixon-Coles 比分矩阵采样。"""
import numpy as np


def simulate(score_grid: dict[str, float], n: int = 10000, seed: int = 7) -> dict:
    """按比分概率分布采样 n 次，输出胜平负/比分矩阵/大小球/BTTS。"""
    rng = np.random.RandomState(seed)
    scores = list(score_grid.keys())
    probs = np.array([score_grid[s] for s in scores], dtype=float)
    probs /= probs.sum()

    picks = rng.choice(len(scores), size=n, p=probs)
    gh = np.zeros(n, dtype=int)
    ga = np.zeros(n, dtype=int)
    for idx, s in enumerate(scores):
        h, a = s.split("-")
        gh[picks == idx] = int(h)
        ga[picks == idx] = int(a)

    p_home = float((gh > ga).mean())
    p_draw = float((gh == ga).mean())
    p_away = float((gh < ga).mean())
    total = gh + ga
    over_under = {
        f"{x}": round(float((total > x).mean()), 4) for x in (0.5, 1.5, 2.5, 3.5, 4.5)
    }
    btts = float(((gh > 0) & (ga > 0)).mean())

    # 比分概率矩阵（模拟频率）
    uniq, cnt = np.unique(
        np.column_stack([gh, ga]), axis=0, return_counts=True
    )
    matrix = {
        f"{h}-{a}": round(float(c / n), 4)
        for (h, a), c in sorted(zip(uniq.tolist(), cnt.tolist()),
                                key=lambda kv: -kv[1])
        if c / n >= 0.01
    }
    return {
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
        "score_matrix": matrix,
        "over_under": over_under,
        "btts": round(btts, 4),
    }
