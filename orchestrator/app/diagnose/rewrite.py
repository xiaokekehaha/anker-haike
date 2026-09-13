"""无命中时的一次查询改写（默认关闭；03 §1.4.2、09 §4.1）。

只改检索表达，不产生业务事实：Schema 仅 {query}，校验拒绝空 / 超长 / 与原 query 相同 / 改变否定 /
新增型号、错误码、数值、未经输入支持的部件或原因（已审核同义映射放行）。校验失败不另调模型裁判。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.diagnose.config import QueryRewriteConfig
from app.diagnose.query import normalize_query
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.rewrite")

NEGATIONS = ("不", "没", "无", "未", "别", "非")
_MODEL_TOKEN = re.compile(
    r"[A-Za-z]{1,6}\s?-?\d{1,4}[A-Za-z]{0,4}|[A-Z]{2,}\d*"
)  # X9 Pro / L60 / E20 / S1Pro
_ERROR_CODE = re.compile(r"\b(?:E|ERR|err|错误)\s?-?\d{1,4}\b|错误码\s?\d+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CJK_WORD = re.compile(r"[一-鿿]{2,}")
# 产品部件名：改写不得引入原文没有的部件（03 §1.4.2「不猜部件」）
PARTS = (
    "滚刷",
    "主刷",
    "边刷",
    "侧刷",
    "滤网",
    "滤芯",
    "过滤网",
    "尘盒",
    "垃圾盒",
    "集尘盒",
    "集尘袋",
    "水箱",
    "拖布",
    "基站",
    "轮子",
    "万向轮",
    "传感器",
    "雷达",
    "摄像头",
    "吸口",
    "进风口",
    "触点",
    "密封圈",
    "轴承",
)
# 「不是 X，是 Y」纠正句式：X 上的否定词属于被纠正掉的旧事实，计否定时先剥掉
_CORRECTION = re.compile(r"不是[^，,。！？；;]{0,30}?[，,]?\s*(?:而)?是")
# 与原因 / 维修动作相关、不允许无中生有的词
FORBIDDEN_NEW = (
    "电机",
    "主板",
    "电池",
    "损坏",
    "烧毁",
    "更换",
    "拆机",
    "维修",
    "故障原因",
    "短路",
    "进水",
    "老化",
)


class RewriteQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)


@dataclass
class RewriteDecision:
    triggered: bool
    reason: str
    query: str | None = None
    rejected_reason: str | None = None
    model_used: str | None = None
    latency_ms: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


def should_rewrite(
    *,
    cfg: QueryRewriteConfig,
    per_kb_status: dict[str, str],
    allowed_counts: dict[str, int],
    has_hits: bool,
    remaining_ms: int,
    quota_used: bool,
    product_state: str | None,
    router_available: bool,
    in_clarify: bool = False,
    replay: bool = False,
    cancelled: bool = False,
) -> RewriteDecision:
    """09 §4.1 决策表：只有「允许集合非空的库全部真实 no_match」且开关 / 名额 / 预算允许时才触发一次。"""
    if not cfg.enabled:
        return RewriteDecision(False, "disabled")
    if product_state not in ("confirmed_sku", "category_only"):
        return RewriteDecision(False, "product_state")
    if in_clarify or replay or cancelled:
        return RewriteDecision(
            False, "state:" + ("clarify" if in_clarify else "replay" if replay else "cancelled")
        )
    if has_hits:
        return RewriteDecision(False, "has_hits")
    requested = {kb: s for kb, s in per_kb_status.items() if allowed_counts.get(kb, 0) > 0}
    if not requested:
        return RewriteDecision(False, "empty_scope")
    if any(s == "unavailable" for s in requested.values()):
        return RewriteDecision(False, "unavailable")  # 部分故障不能算正常无命中
    if any(s != "no_match" for s in requested.values()):
        return RewriteDecision(False, "not_all_no_match")
    if quota_used:
        return RewriteDecision(False, "quota_used")
    if remaining_ms < cfg.min_remaining_ms:
        return RewriteDecision(False, f"budget:{remaining_ms}ms")
    if not router_available:
        return RewriteDecision(False, "router_unavailable")
    return RewriteDecision(True, "eligible")


def _tokens(pattern: re.Pattern[str], text: str) -> set[str]:
    return {m.group(0).replace(" ", "").casefold() for m in pattern.finditer(text)}


def _synonym_base(word: str, synonyms: dict[str, list[str]]) -> str:
    for base, alts in synonyms.items():
        if word == base or word in alts:
            return base
    return word


def strip_corrected_clause(text: str) -> str:
    """「不是吸力小，是有异响」→「是有异响」：纠正句式里被否定掉的旧事实不参与否定词比较。"""
    return _CORRECTION.sub("", text)  # src 里原话可能重复出现，全部剥掉


def shares_anchor(candidate: str, anchors: str, synonyms: dict[str, list[str]]) -> bool:
    """改写必须保留原症状的至少一个锚点，防止整体漂移到别的故障。锚点 = 与原症状共有的 2 字词，
    或一个已审核同义词的规范词（其口语说法出现在原症状里）——改写的本职就是把口语换成说明书用语，
    字面重叠可能为零，所以同义映射必须算锚点。单字同义词（扫 / 跑）区分度不够，不作锚点依据。"""
    if not anchors.strip():
        return True
    if any(candidate[i : i + 2] in anchors for i in range(len(candidate) - 1)):
        return True
    return any(
        any(w in candidate for w in (base, *alts) if len(w) >= 2)
        for base, alts in synonyms.items()
        if any(len(a) >= 2 and a in anchors for a in (base, *alts))
    )


def validate_rewrite(
    original: str,
    candidate: str,
    *,
    inputs: str,
    cfg: QueryRewriteConfig,
    anchors: str | None = None,
) -> str | None:
    """返回拒绝原因；None 表示放行。inputs = 用户原话 + 产品 + 症状拼接（改写只能使用其中的信息）；
    anchors = 不含产品词的症状 / 原话（用于「保留至少一个原症状词」检查），默认退回 inputs。

    03 §1.4.2 的意图是「拒绝新增未经输入支持的部件、原因或操作」。cfg.strict_terms=true 时额外启用早期的
    整句可切分规则（任何新词都拒），实测会拒掉几乎所有自然改写（阶段 6 findings），默认关闭。"""
    cand = " ".join(candidate.split())
    if not cand:
        return "empty"
    if len(cand) > cfg.max_query_chars:
        return "too_long"
    if normalize_query(cand) == normalize_query(original):
        return "same_as_original"
    if re.search(r"[{}\[\]\"':]|sku|scope|knowledge", cand, re.IGNORECASE):
        return "contains_filter_or_structure"
    src = f"{original} {inputs}"
    if _tokens(_ERROR_CODE, cand) - _tokens(_ERROR_CODE, src):
        return "new_error_code"
    err_tokens = _tokens(_ERROR_CODE, cand)
    if (_tokens(_MODEL_TOKEN, cand) - err_tokens) - _tokens(_MODEL_TOKEN, src):
        return "new_model_token"
    if _tokens(_NUMBER, cand) - _tokens(_NUMBER, src):
        return "new_number"
    # 否定分两个方向：凭空「加」否定会翻转语义，必须拒；「丢」否定只在被否定的是真事实时才拒
    # （「不是吸力小，是有异响」里的否定属于被纠正掉的旧事实，剥掉后不算丢失）
    neg_cand = sum(cand.count(n) for n in NEGATIONS)
    if neg_cand and not sum(src.count(n) for n in NEGATIONS):
        return "negation_changed"
    if not neg_cand and sum(strip_corrected_clause(src).count(n) for n in NEGATIONS):
        return "negation_changed"
    for word in FORBIDDEN_NEW:
        if word in cand and word not in src:
            return f"new_cause_or_action:{word}"
    approved = {base for base, alts in cfg.synonyms.items() if any(a in src for a in (base, *alts))}
    for part in PARTS:
        if part in cand and part not in src and _synonym_base(part, cfg.synonyms) not in approved:
            return f"new_part:{part}"
    if not shares_anchor(cand, anchors if anchors is not None else inputs, cfg.synonyms):
        return "lost_original_symptom"
    if cfg.strict_terms:
        # 早期严格模式：新出现的中文片段必须能完全分解为原文片段或已审核同义词
        for run in _CJK_WORD.findall(cand):
            if not _segmentable(run, src, approved):
                return f"unsupported_term:{run}"
    return None


def _segmentable(run: str, src: str, approved: set[str]) -> bool:
    """贪心最长匹配：每一段要么是原文子串（≥1 字），要么是已审核同义词。"""
    i, n = 0, len(run)
    while i < n:
        matched = 0
        for j in range(n, i, -1):
            seg = run[i:j]
            if seg in approved or (seg in src and (len(seg) >= 2 or j - i == 1)):
                matched = j
                break
        if not matched:
            return False
        i = matched
    return True


INSTRUCTION = (
    "首轮检索没有找到匹配的知识。请把用户的口语描述改写成更接近说明书 / 工单用语的一句检索查询：\n"
    "- 保留原意与否定词，不要猜测型号、部件、故障原因或维修动作；\n"
    "- 不要加入产品型号或过滤条件，产品范围由系统控制；\n"
    '- 只输出 JSON：{"query": "..."}，不超过 60 字。'
)


async def rewrite_query(
    router: ModelRouter,
    *,
    original: str,
    user_text: str,
    product: str,
    symptoms: list[str],
    cfg: QueryRewriteConfig,
    category_label: str | None = None,
    session_id: str | None,
    lane: str,
    budget_ms: int | None = None,
) -> RewriteDecision:
    inputs = " ".join([product, category_label or "", *symptoms, user_text])
    anchors = " ".join([*symptoms, user_text])  # 不含产品词：产品词不能充当「保留了原症状」的凭据
    messages = [
        (
            "system",
            compose_system_prompt(
                "normal", {"stage": "diagnose", "product": product or None, "symptoms": symptoms}
            ),
        ),
        ("human", f"{INSTRUCTION}\n首次查询：{original}\n{wrap_data(user_text)}"),
    ]
    try:
        res = await router.invoke(
            "query.rewrite",
            messages,
            RewriteQuery,
            budget_ms=budget_ms or cfg.budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.warning("query.rewrite failed session=%s: %s", session_id, str(exc)[:200])
        return RewriteDecision(True, "eligible", rejected_reason=f"model:{type(exc).__name__}")
    cand = res.parsed.query
    reason = validate_rewrite(original, cand, inputs=inputs, cfg=cfg, anchors=anchors)
    decision = RewriteDecision(
        True,
        "eligible",
        query=None if reason else " ".join(cand.split()),
        rejected_reason=reason,
        model_used=res.model_used,
        latency_ms=res.latency_ms,
        detail={"candidate": cand},
    )
    log.info(
        "query.rewrite session=%s original=%r candidate=%r accepted=%s reason=%s model=%s ms=%d",
        session_id,
        original,
        cand,
        reason is None,
        reason,
        res.model_used,
        res.latency_ms,
        extra={
            "event": "query_rewrite",
            "accepted": reason is None,
            "rejected_reason": reason,
            "session_id": session_id,
        },
    )
    return decision
