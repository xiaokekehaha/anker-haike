"""expect 规则 → 0–1 的准确率分。每个 task 一个评分函数；规则名尽量沿用 tests/fixtures/intake_golden.yaml。"""

from __future__ import annotations

import re
from typing import Any

_DIGITS = re.compile(r"\D+")
STEP_WORDS = ("第一步", "步骤", "首先", "请先", "然后", "接着", "1.", "2.", "①")
FORBIDDEN_WARRANTY = (
    "可保",
    "标准质保",
    "符合质保",
    "享受质保",
    "保修资格",
    "免费维修",
    "免费换新",
)


def _contains_any(text: str, words: list[str]) -> bool:
    t = text.lower()
    return any(w.lower() in t for w in words)


def _checks(results: list[bool]) -> float:
    return sum(results) / len(results) if results else 1.0


def score_intake(out: Any, expect: dict[str, Any]) -> float:
    if out.degraded:
        return 0.0
    checks: list[bool] = []
    if "level" in expect:
        checks.append(out.emotion["level"] == expect["level"])
    if "level_in" in expect:
        checks.append(out.emotion["level"] in expect["level_in"])
    checks.append(out.wants_human is bool(expect.get("wants_human", False)))
    if "hints_include_any" in expect:
        checks.append(_contains_any(" ".join(out.product_hints), expect["hints_include_any"]))
    if expect.get("hints_empty"):
        checks.append(out.product_hints == [])
    if "symptoms_min" in expect:
        checks.append(len(out.symptoms) >= int(expect["symptoms_min"]))
    if "symptoms_include_any" in expect:
        checks.append(_contains_any(" ".join(out.symptoms), expect["symptoms_include_any"]))
    if expect.get("symptoms_empty"):
        checks.append(out.symptoms == [])
    return _checks(checks)


def score_clarify(out: Any, expect: dict[str, Any]) -> float:
    if out.model_used in ("skipped", "fixed"):
        return 0.0
    q = out.text
    checks = [
        2 <= len(q) <= int(expect.get("max_chars", 80)),
        not _contains_any(q, list(STEP_WORDS)),
    ]
    if "must_contain_any" in expect:
        checks.append(_contains_any(q, expect["must_contain_any"]))
    if "must_not_contain" in expect:
        checks.append(not _contains_any(q, expect["must_not_contain"]))
    return _checks(checks)


def score_synthesize(out: dict[str, Any], expect: dict[str, Any]) -> float:
    ranked = out.get("plans_ranked") or []
    from_model = [p for p in ranked if p.get("source") == "synthesize"]
    if not from_model:
        # 模型给空列表，或假设全被证据过滤（all_dropped → 标准流程兜底）：等价于「没有计划能解释」
        return 1.0 if expect.get("empty_ok") else 0.0
    if out.get("degraded"):
        return 0.0
    top = ranked[0]["plan_id"]
    checks: list[bool] = []
    if "top1" in expect:
        checks.append(top == expect["top1"])
    if "top1_in" in expect:
        checks.append(top in expect["top1_in"])
    if "top2_include" in expect:
        checks.append(expect["top2_include"] in [p["plan_id"] for p in ranked[:2]])
    checks.append(all(p.get("evidence_ids") for p in ranked))
    return _checks(checks)


def score_stream(out: Any, expect: dict[str, Any]) -> float:
    if not out.completed or not out.text.strip():
        return 0.0
    t = out.text.strip()
    checks = [len(t) <= int(expect.get("max_chars", 200)), "```" not in t]
    if expect.get("no_steps"):
        checks.append(not _contains_any(t, list(STEP_WORDS)))
    if "must_contain_any" in expect:
        checks.append(_contains_any(t, expect["must_contain_any"]))
    if "must_not_contain" in expect:
        checks.append(not _contains_any(t, expect["must_not_contain"]))
    checks.append(not _contains_any(t, list(FORBIDDEN_WARRANTY)))
    return _checks(checks)


def score_summary(source: str, polished: str | None, expect: dict[str, Any]) -> float:
    """polish 只允许清理空白 / 标点：句子序列必须一致且无资格结论。polished 为 None 表示模型未给出。"""
    if polished is None:
        return 0.0

    def sents(x: str) -> list[str]:
        return [re.sub(r"\s+", "", s) for s in re.split(r"[。！？!?；;\n]+", x) if s.strip()]

    # 资格结论只惩罚「新增」的：用户原话里本来就有的词（注入样本）逐句保留才是正确行为
    new_forbidden = [w for w in FORBIDDEN_WARRANTY if w in polished and w not in source]
    return _checks([sents(source) == sents(polished), not new_forbidden])


def score_rewrite(decision: Any, expect: dict[str, Any]) -> float:
    if decision.rejected_reason or not decision.query:
        return 0.0
    checks: list[bool] = []
    if "must_contain_any" in expect:
        checks.append(_contains_any(decision.query, expect["must_contain_any"]))
    return _checks(checks)


UNKNOWN_PHENOMENA = ("正常", "不可辨")
VISION_FIELD_KEYS = {
    "findings_include",
    "findings_exclude",
    "plan",
    "model_hint_contains",
    "no_fabricated_model",
    "no_fault_findings",
    "usable",
}


def _findings(out: Any) -> list[dict[str, Any]]:
    return ((out.fault_localization or {}).get("findings")) or []


def _expand(want: dict[str, Any]) -> dict[str, Any]:
    """`{part, plan}` 展开成「签名表里映射到该 plan 的全部现象」。

    手写期望会和签名表脱节：签名表已经把 {滤网, 满} 和 {滤网, 堵塞} 映射到同一个 plan，
    期望却只认「堵塞」，于是模型答「满」时 plan 命中却被判现象错。让两边同源，改签名表即改期望。
    """
    if "plan" not in want:
        return want
    from app.diagnose.localization import vocabulary

    phenomena = [
        s["phenomenon"]
        for s in vocabulary()["signatures"]
        if s["plan_id"] == want["plan"] and s["part"] == want["part"]
    ]
    return {"part": want["part"], "phenomenon": phenomena or ["不可能命中"]}


def _has_finding(out: Any, want: dict[str, Any]) -> bool:
    """want 的值可以是列表，表示「其中任一说法都算对」；也可以用 plan 从签名表反查。"""
    want = _expand(want)

    def match(f: dict[str, Any], k: str, v: Any) -> bool:
        return f.get(k) in v if isinstance(v, list) else f.get(k) == v

    return any(all(match(f, k, v) for k, v in want.items()) for f in _findings(out))


def vision_metrics(out: Any, expect: dict[str, Any]) -> dict[str, bool]:
    """按指标族给出本样本的判定；不适用的指标不出现在返回里（聚合时按分母只算适用样本）。

    指标族对应规划 §5 阶段 0：part / phenomenon 准确率、plan 命中率、幻觉率、安全召回、可用判定。
    幻觉率是「反向」指标：这里记 hallucination_free=True 表示本样本没有编造。
    """
    m: dict[str, bool] = {}
    # unusable = 像素层门控直接判不可用（未调模型），它是一个有效结论，要参与 usable 指标
    if out.status not in ("ok", "unusable"):
        return {}
    loc = out.fault_localization or {}
    findings = _findings(out)

    for want in expect.get("findings_include") or []:
        if "part" in want:
            m["part"] = m.get("part", True) and _has_finding(out, {"part": want["part"]})
        if "phenomenon" in want or "plan" in want:
            m["phenomenon"] = m.get("phenomenon", True) and _has_finding(out, want)
    for bad in expect.get("findings_exclude") or []:
        m["hallucination_free"] = m.get("hallucination_free", True) and not _has_finding(out, bad)

    if expect.get("no_fault_findings"):
        m["hallucination_free"] = m.get("hallucination_free", True) and all(
            f.get("phenomenon") in UNKNOWN_PHENOMENA for f in findings
        )

    gold = expect.get("model_hint_contains")
    hint = (loc.get("model_hint") or "").strip()
    if gold:
        m["model_hint"] = all(g.lower() in hint.lower() for g in gold)
        if expect.get("no_fabricated_model"):
            # 读到了内容但不含金标 → 编造；留空或只给 ? 占位 → 诚实的漏测，不计入幻觉
            fabricated = bool(hint.replace("?", "").strip()) and not m["model_hint"]
            m["hallucination_free"] = m.get("hallucination_free", True) and not fabricated

    # 过度弃答：期望图可用时，把部件或现象填成「不可辨」就是在用弃答换幻觉率。
    # A2「宁可不知道，不可知道错」是相对误测说的，没有上界会把系统推向「全部不可辨」的退化解。
    if expect.get("usable") is not False and (VISION_FIELD_KEYS & expect.keys()):
        m["abstention_free"] = not any(
            f.get("part") == "不可辨" or f.get("phenomenon") == "不可辨" for f in findings
        )

    if "usable" in expect:
        m["usable"] = bool((loc.get("image_quality") or {}).get("usable")) is bool(expect["usable"])

    if "plan" in expect:
        from app.diagnose.localization import signature_plans

        m["plan"] = expect["plan"] in (signature_plans(loc) if loc else [])

    if "safety_any" in expect:
        blob = " ".join([*out.observations, *out.visible_parts]).lower()
        m["safety"] = any(w.lower() in blob for w in expect["safety_any"])
    return m


def score_vision(out: Any, expect: dict[str, Any]) -> float:
    """字段级评分：命中的指标数 / 适用的指标数。

    旧样本（只有 observe / absent / safety_any 的关键词组规则）继续走 _score_vision_keywords，
    口径不变，以免历史 bake-off 数字不可比。
    """
    if out.status not in ("ok", "unusable"):
        return 0.0
    if not (VISION_FIELD_KEYS & expect.keys()):
        return _score_vision_keywords(out, expect)
    m = vision_metrics(out, expect)
    return _checks(list(m.values()))


def _score_vision_keywords(out: Any, expect: dict[str, Any]) -> float:
    """观察召回：expect.observe 是若干组同义词，每组至少命中一个算召回；safety 关键词单独必须命中。"""
    if out.status != "ok":
        return 0.0  # 关键词口径要看模型观察项，被门控拦下时没有观察项可评
    blob = " ".join([*out.observations, *out.visible_parts]).lower()
    groups: list[list[str]] = expect.get("observe") or []
    hit = sum(1 for g in groups if any(w.lower() in blob for w in g))
    recall = hit / len(groups) if groups else 1.0
    if "safety_any" in expect and not any(w.lower() in blob for w in expect["safety_any"]):
        return 0.0
    if "absent" in expect:
        # 「未见缠绕物」是正确否定，不算出现：去掉含否定词的短句后再查 absent 词
        positive = " ".join(
            seg
            for seg in re.split(r"[，,；;。\s]+", blob)
            if seg and not re.search(r"未|无|没|不|non|no\b", seg)
        )
        if any(w.lower() in positive for w in expect["absent"]):
            recall *= 0.5
    return recall


def _norm_field(k: str, v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if k == "order_no":
        return _DIGITS.sub("", s) or s.upper()
    if k == "purchase_date":
        return _DIGITS.sub("", s)[:8]
    if k == "amount":
        m = re.search(r"\d+(?:\.\d+)?", s.replace(",", ""))
        return f"{float(m.group()):.2f}" if m else s
    return s.replace(" ", "").lower()


def score_receipt(out: Any, expect: dict[str, Any]) -> float:
    """字段准确率：期望有值的字段要抄对；期望 unreadable 的字段要为空。"""
    if out.status != "ok":
        return 0.0
    fields: dict[str, str | None] = expect.get("fields") or {}
    unreadable: list[str] = expect.get("unreadable") or []
    checks: list[bool] = []
    for k, v in fields.items():
        got = _norm_field(k, out.fields.get(k))
        want = _norm_field(k, v)
        checks.append(got is not None and want is not None and (want in got or got in want))
    for k in unreadable:
        checks.append(out.fields.get(k) is None)
    return _checks(checks)


def score_grade(out: Any, expect: dict[str, Any]) -> float:
    """逐条 verdict 命中期望（relevant / irrelevant 两个列表）+ coverage 在期望集合内；未评分（模型失败）记 0。"""
    if out.status != "graded":
        return 0.0
    checks: list[bool] = []
    for eid in expect.get("relevant") or []:
        checks.append(out.verdicts.get(eid) == "relevant")
    for eid in expect.get("irrelevant") or []:
        checks.append(out.verdicts.get(eid) == "irrelevant")
    if "coverage_in" in expect:
        checks.append(out.coverage in expect["coverage_in"])
    return _checks(checks)
