"""XGBoost 比赛结果模型（Phase 3）。

训练数据：由模拟引擎生成的合成历史比赛（特征含 Elo 差、近期状态、赛程密度）。
Phase 4 接入真实 API 数据后用同一管线重训。模型文件缓存在 backend/ml_models/。
依赖缺失时自动降级：xgboost -> sklearn HistGradientBoosting -> numpy softmax 回归。
"""
import json
import os

import numpy as np

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "xgb_match_outcome.json")
META_PATH = os.path.join(MODEL_DIR, "meta.json")
FEATURES = ["elo_diff", "form_home", "form_away", "rest_home", "rest_away", "is_neutral"]

_engine = None  # 惰性加载的模型对象


def _make_dataset(n: int, seed: int = 42):
    """合成训练集：与 simulator 的数据生成逻辑同分布。"""
    rng = np.random.RandomState(seed)
    elo_diff = rng.normal(0, 90, n)  # 主-客 Elo 差（含主场优势）
    form_home = rng.uniform(0.1, 0.9, n)
    form_away = rng.uniform(0.1, 0.9, n)
    rest_home = rng.randint(2, 8, n).astype(float)
    rest_away = rng.randint(2, 8, n).astype(float)
    is_neutral = rng.randint(0, 2, n).astype(float)

    base = 2.65
    share = 1 / (1 + np.exp(-(elo_diff / 400.0) * 4.0))
    lam_h = base * share * (1 + (form_home - 0.5) * 0.44) \
        * np.clip(1 + (rest_away - 4) * 0.015, 0.9, 1.1)
    lam_a = base * (1 - share) * (1 + (form_away - 0.5) * 0.44) \
        * np.clip(1 + (rest_home - 4) * 0.015, 0.9, 1.1)
    lam_h = lam_h * (1 - 0.15 * is_neutral) + 0.05
    lam_a = lam_a + 0.05
    gh = rng.poisson(lam_h)
    ga = rng.poisson(lam_a)
    y = (gh > ga).astype(int) * 0 + (gh == ga).astype(int) * 1 + (gh < ga).astype(int) * 2
    X = np.column_stack([elo_diff, form_home, form_away, rest_home, rest_away, is_neutral])
    return X, y


def _train_xgboost(X, y):
    from xgboost import XGBClassifier

    model = XGBClassifier(
        n_estimators=220, max_depth=4, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9,
        objective="multi:softprob", num_class=3,
        eval_metric="mlogloss", verbosity=0,
    )
    model.fit(X, y)
    return model


def _train_sklearn(X, y):
    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(max_iter=220, max_depth=4, learning_rate=0.08)
    model.fit(X, y)
    return model


def _train_numpy(X, y):
    """兜底：多项 logistic 回归（纯 numpy，梯度下降）。"""
    n, d = X.shape
    Xb = np.column_stack([X / np.array([400, 1, 1, 8, 8, 1]), np.ones(n)])
    W = np.zeros((d + 1, 3))
    Y = np.eye(3)[y]
    for _ in range(1500):
        p = np.exp(Xb @ W - Xb @ W.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        W -= 0.05 * Xb.T @ (p - Y) / n
    return ("numpy", W)


def ensure_model() -> str:
    """确保模型存在并加载，返回使用的引擎描述。"""
    global _engine
    if _engine is not None:
        return _engine_desc()

    os.makedirs(MODEL_DIR, exist_ok=True)
    if not (os.path.exists(MODEL_PATH) and os.path.exists(META_PATH)):
        X, y = _make_dataset(6000)
        try:
            model = _train_xgboost(X, y)
            engine = "xgboost"
            model.save_model(MODEL_PATH)
        except Exception:
            try:
                model = _train_sklearn(X, y)
                engine = "sklearn-hgb"
                import joblib

                joblib.dump(model, MODEL_PATH)
            except Exception:
                engine, W = _train_numpy(X, y)
                model = W
                with open(MODEL_PATH, "wb") as f:  # np.save 会追加 .npy，这里直接存字节
                    np.save(f, W)
        meta = {
            "engine": engine, "features": FEATURES,
            "train_size": int(len(y)),
            "train_acc": None,
        }
        with open(META_PATH, "w") as f:
            json.dump(meta, f)

    with open(META_PATH) as f:
        meta = json.load(f)
    engine = meta["engine"]
    if engine == "xgboost":
        from xgboost import XGBClassifier

        m = XGBClassifier()
        m.load_model(MODEL_PATH)
        _engine = ("xgboost", m)
    elif engine == "sklearn-hgb":
        import joblib

        _engine = ("sklearn-hgb", joblib.load(MODEL_PATH))
    else:
        _engine = ("numpy", np.load(MODEL_PATH))
    return _engine_desc()


def _engine_desc() -> str:
    return f"{_engine[0]}@{MODEL_PATH}"


def predict_proba(elo_diff: float, form_home: float, form_away: float,
                  rest_home: float = 4.0, rest_away: float = 4.0) -> tuple[float, float, float]:
    """输出 ML 模型的 (p_home, p_draw, p_away)。"""
    ensure_model()
    kind, m = _engine
    x = np.array([[elo_diff, form_home, form_away, rest_home, rest_away, 0.0]])
    if kind == "xgboost":
        p = m.predict_proba(x)[0]
    elif kind == "sklearn-hgb":
        p = m.predict_proba(x)[0]
    else:
        Xb = np.column_stack([x / np.array([400, 1, 1, 8, 8, 1]), np.ones(1)])
        z = Xb @ m
        z = np.exp(z - z.max())
        p = (z / z.sum())[0]
    return float(p[0]), float(p[1]), float(p[2])


W_DC = 0.55   # Dixon-Coles 权重（可解释基线）
W_ML = 0.45   # XGBoost 权重


def blend(dc: dict, ml: tuple[float, float, float]) -> dict:
    """Logistic stacking：线性融合两路概率并归一化。"""
    p = np.array([dc["p_home"], dc["p_draw"], dc["p_away"]]) * W_DC + np.array(ml) * W_ML
    p = p / p.sum()
    out = dict(dc)
    out["p_home"], out["p_draw"], out["p_away"] = (round(float(v), 4) for v in p)
    top = max(out["p_home"], out["p_draw"], out["p_away"])
    out["confidence"] = round(min(0.95, 0.4 + (top - 1 / 3) * 1.6), 3)
    out["model_version"] = f"dc-{_engine[0]}-blend-v0.2"
    return out
