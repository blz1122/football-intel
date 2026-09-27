"""AI 比赛报告生成引擎。

两级生成策略：
1. 数据驱动模板引擎（默认，零依赖、毫秒级）：从 xG 差 / 控球 / 红牌 /
   概率摆动 / 射门效率等真实指标推导叙事；
2. 可选 LLM 润色（OpenAI 兼容接口）：配置 OPENAI_API_KEY 后，
   将结构化事实交给 LLM 生成更具分析深度的报告，失败自动回退模板。
"""
import json
import urllib.request
from typing import Any

from app.core.config import settings


# ---------------- 指标推导 ----------------
def _fmt_pct(x: float) -> str:
    return f"{round(x * 100)}%"


def build_facts(
    m: Any, state: dict, events: list, stats: Any,
    pred: Any, curve: list[dict] | None,
) -> dict[str, Any]:
    """把比赛对象压缩为报告所需的客观事实。"""
    hs, as_ = state["home_score"], state["away_score"]
    elo_diff = m.home_team.elo_rating - m.away_team.elo_rating

    # 概率摆动：曲线中主胜概率的最大波动
    swing, swing_note = 0.0, "比赛尚未开始"
    if curve and len(curve) >= 2:
        ph = [c["p_home"] for c in curve]
        peak_i = max(range(len(ph)), key=lambda i: ph[i])
        low_i = min(range(len(ph)), key=lambda i: ph[i])
        swing = abs(ph[peak_i] - ph[low_i])
        if swing > 0.25:
            swing_note = "走势剧烈，胜率多次反转"
        elif swing > 0.10:
            swing_note = "概率存在明显波动"
        else:
            swing_note = "概率走势平稳，局面可控"

    xg_h = stats.xg_home if stats else 0.0
    xg_a = stats.xg_away if stats else 0.0
    poss_h = stats.possession_home if stats else 50

    return {
        "home": m.home_team.name, "away": m.away_team.name,
        "league": m.league.name,
        "status": state["status"], "minute": state["minute"],
        "score": f"{hs}-{as_}",
        "elo_diff": round(elo_diff),
        "xg": [round(xg_h, 2), round(xg_a, 2)],
        "possession": [poss_h, 100 - poss_h],
        "shots": [stats.shots_home if stats else 0, stats.shots_away if stats else 0],
        "on_target": [stats.shots_on_target_home if stats else 0,
                      stats.shots_on_target_away if stats else 0],
        "reds": [stats.red_home if stats else 0, stats.red_away if stats else 0],
        "yellows": [stats.yellow_home if stats else 0,
                    stats.yellow_away if stats else 0],
        "goals": [{"minute": e.minute, "side": e.side, "detail": e.detail}
                  for e in events if e.type == "goal"],
        "pred": {"p_home": pred.p_home, "p_draw": pred.p_draw,
                 "p_away": pred.p_away, "confidence": pred.confidence,
                 "expected_score": pred.expected_score},
        "swing": round(swing, 3), "swing_note": swing_note,
    }


def _template_report(f: dict[str, Any]) -> list[dict[str, str]]:
    """数据驱动模板引擎：每个板块由具体指标条件触发。"""
    home, away = f["home"], f["away"]
    sections: list[dict[str, str]] = []

    # 1) 赛况概述
    if f["status"] == "scheduled":
        lead = (
            f"{home} 将在{f['league']}迎战 {away}。赛前模型给出 "
            f"{_fmt_pct(f['pred']['p_home'])} / {_fmt_pct(f['pred']['p_draw'])} / "
            f"{_fmt_pct(f['pred']['p_away'])} 的胜平负分布，"
            f"模型置信度 {_fmt_pct(f['pred']['confidence'])}。"
        )
    elif f["status"] == "finished":
        lead = (
            f"终场比分 {home} {f['score']} {away}。"
            f"xG 对比 {f['xg'][0]} : {f['xg'][1]}，"
            f"控球 {f['possession'][0]}% : {f['possession'][1]}%。"
        )
    else:
        lead = (
            f"比赛进行至第 {f['minute']} 分钟，{home} {f['score']} {away}。"
            f"当前 xG {f['xg'][0]} : {f['xg'][1]}，"
            f"控球 {f['possession'][0]}% : {f['possession'][1]}%。"
        )
    sections.append({"icon": "📋", "title": "赛况概述", "body": lead})

    # 2) 关键点：xG 与比分是否匹配（效率判断）
    xg_h, xg_a = f["xg"]
    sc_h, sc_a = (int(x) for x in f["score"].split("-"))
    points: list[str] = []
    if f["status"] != "scheduled":
        if abs((xg_h - xg_a) - (sc_h - sc_a)) > 1.2:
            better = home if xg_h > xg_a else away
            points.append(
                f"{better} 的预期进球显著领先实际比分，射门转化率异常，"
                "大概率受到门将发挥或门框运气影响。"
            )
        if xg_h + xg_a < 1.5 and f["minute"] and f["minute"] > 55:
            points.append("双方合计 xG 不足 1.5，比赛进入低节奏胶着状态。")
        if f["swing"] >= 0.25:
            points.append(f"胜率曲线最大摆动达 {_fmt_pct(f['swing'])}，{f['swing_note']}。")
    if abs(f["elo_diff"]) > 80:
        strong = home if f["elo_diff"] > 0 else away
        points.append(f"Elo 实力差 {abs(f['elo_diff'])} 分，{strong} 纸面实力占优。")
    if not points:
        points.append("双方表现与模型预期基本一致，无明显异常信号。")
    sections.append({"icon": "🔑", "title": "比赛关键点", "body": " ".join(points)})

    # 3) 战术分析：控球结构 + 进攻区域代理指标
    poss = f["possession"][0]
    tactics: list[str] = []
    if poss >= 60:
        tactics.append(f"{home} 掌握 {poss}% 控球，呈压制型控局打法，对方大概率收缩防反。")
    elif poss <= 40:
        tactics.append(f"{away} 以 {100 - poss}% 控球主导中场，{home} 主动让出球权打转换。")
    else:
        tactics.append(f"控球 {poss}% : {100 - poss}%，中场五五开，胜负取决于攻防转换质量。")
    sh_h, sh_a = f["shots"]
    sot_h, sot_a = f["on_target"]
    if sh_h + sh_a > 0:
        eff = (sot_h / sh_h if sh_h else 0, sot_a / sh_a if sh_a else 0)
        side = home if eff[0] >= eff[1] else away
        tactics.append(
            f"射正率 {side} 更高（{_fmt_pct(max(eff))}），进攻选择更克制、机会质量更好。"
        )
    sections.append({"icon": "🎯", "title": "战术分析", "body": " ".join(tactics)})

    # 4) 风险提醒
    risks: list[str] = []
    r_h, r_a = f["reds"]
    if r_h or r_a:
        team = home if r_h else away
        risks.append(
            f"{team} 已领到红牌（共 {r_h + r_a} 张），人数劣势下防守压迫范围收窄，"
            "失球风险显著上升。"
        )
    y_h, y_a = f["yellows"]
    if y_h + y_a >= 5:
        risks.append(f"双方合计 {y_h + y_a} 张黄牌，判罚尺度偏紧，后续减员风险高。")
    if f["status"] == "live" and sc_h != sc_a:
        leader = home if sc_h > sc_a else away
        trailer = away if sc_h > sc_a else home
        risks.append(
            f"{trailer} 落后之下预计提高阵线，{leader} 需防范被逼平的回头球风险。"
        )
    if not risks:
        risks.append("暂无明显风险信号。")
    sections.append({"icon": "⚠️", "title": "风险提醒", "body": " ".join(risks)})

    # 5) 走势展望
    if f["status"] == "scheduled":
        outlook = (
            f"模型最可能比分 {f['pred'].get('expected_score', '')}。"
            "建议开赛前 30 分钟回看首发与伤停更新。"
        )
    elif f["status"] == "finished":
        outlook = "比赛已结束，数据将纳入 7 日滚动 KPI 与模型复盘。"
    else:
        wp = f["pred"]
        outlook = (
            f"按当前强度推演，剩余时间主队期望进球 "
            f"{(xg_h * (90 - (f['minute'] or 0)) / max(f['minute'], 1)):.2f}，"
            "模型将持续按分钟更新胜率曲线。"
        )
    sections.append({"icon": "🔮", "title": "走势展望", "body": outlook})
    return sections


# ---------------- 可选 LLM 润色 ----------------
def _llm_report(f: dict[str, Any]) -> list[dict[str, str]] | None:
    """调用 OpenAI 兼容接口生成报告；任何异常返回 None 走模板回退。"""
    if not settings.OPENAI_API_KEY:
        return None
    prompt = (
        "你是专业足球数据分析师。基于以下 JSON 事实写一份中文比赛分析报告，"
        "输出 JSON 数组，每项 {\"icon\": \"emoji\", \"title\": \"板块名\", "
        "\"body\": \"分析文本\"}，板块依次为：赛况概述/比赛关键点/战术分析/"
        "风险提醒/走势展望。只输出 JSON。\n" + json.dumps(f, ensure_ascii=False)
    )
    req = urllib.request.Request(
        f"{settings.OPENAI_BASE_URL}/chat/completions",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
    )
    body = json.dumps({
        "model": settings.OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }).encode()
    try:
        with urllib.request.urlopen(req, body, timeout=15) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"]
        sections = json.loads(content)
        if isinstance(sections, list) and sections:
            return sections
    except Exception as e:
        print(f"[report] LLM fallback to template: {e}")
    return None


def generate_report(f: dict[str, Any]) -> dict[str, Any]:
    sections = _llm_report(f)
    generated_by = "llm"
    if sections is None:
        sections = _template_report(f)
        generated_by = "template"
    return {"generated_by": generated_by, "sections": sections}
