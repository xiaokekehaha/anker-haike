"""官方 Q&A → 排障计划（取代手写 config/plans.yaml）。

每条可见 Q&A 生成一个计划，计划 id = qa_<qa_id>，下游的步骤卡、反馈推进、下一动作选择不变：
- steps 型（≥2 个编号步骤）：一步一张卡，线性推进；步骤正文就是 Q&A 原文（英文，已去链接）。
- answer 型：整条答案作为一张卡。
- 末步写「hardware malfunction / warranty service」的步骤：not_solved 直接 EXHAUSTED，交给质保流程。
- warranty 型（整条就是硬件故障结论）也生成计划，但 diagnose 不会给它发步骤卡，而是直接进质保判断。
symptom_codes 填 Q&A 标题里的错误码：客户报了错误码，allowed_for 就只剩精确命中的那几条。
"""

from __future__ import annotations

import re

from app.official.qa_index import Guide, QAIndex, get_qa_index
from app.plans.library import PlanLibrary
from app.plans.models import PlansConfig

# 步骤卡的「预期结果」直接显示给客户，用英文（D2）。步骤正文本身就是官方 Q&A 原文（英文）。
EXPECTED = "After this step, check whether the problem is resolved."
ANSWER_EXPECTED = "Pick the option that matches, or describe it in a few words."
MATERIAL_EXPECTED = "Upload it here if you have it, or tell me you don't have it right now."
EXPECTED_BY_KIND = {"action": EXPECTED, "question": ANSWER_EXPECTED, "material_request": MATERIAL_EXPECTED,
                    "statement": "No action needed here.", "handoff": "A support colleague will continue from here."}
TIPS_LEAD = re.compile(r"^[\s*•\-]*(?:Additional\s+)?Tips?\s*[:：]?\s*", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?。！？])\s")
# 「If the robot is often stuck on the edge of stairs…, it is recommended…」：逗号 / 冒号 / then 之前是适用条件。
CONDITION = re.compile(r"^\s*if\s+(?P<cond>[^,:;]{3,200}?)\s*(?:,|:|;|\bthen\b)", re.IGNORECASE)
# 「If the error persists after restarting」「If heating still fails」接的是上一步的结果，不是场景前提，不拿事实去核。
# continue 不在内：rv-0106「continues to display errors on flat ground」说的是场景。
CONTINUATION = re.compile(r"\b(?:still|persists?|again|after|above|previous|remains?)\b", re.IGNORECASE)

# 官方 Q&A 是写给客服看的内部指引，少数条目直接用了客服口吻（「让用户去照一下」）。
# 原样发给客户会变成「请让用户打开手电筒」—— 客户就是用户本人。
# data/official/qa.yaml 是 XLSX 的生成产物（文件头写明勿手改），改它既违反生成文件约定，
# 也会让本地数据与主办方原文悄悄分叉；所以在**渲染层**把人称改过来，原文留在证据里不动。
# 只改人称，不改任何操作内容、器具或顺序。
AGENT_VOICE = (
    (re.compile(r"\b[Hh]ave the (?:user|customer)\s+(\w+)"), lambda m: m.group(1).capitalize()),
    (re.compile(r"\b[Aa]sk the (?:user|customer) to\s+(\w+)"), lambda m: m.group(1).capitalize()),
    (re.compile(r"\b[Tt]ell the (?:user|customer) to\s+(\w+)"), lambda m: m.group(1).capitalize()),
    (re.compile(r"\b[Ii]nstruct the (?:user|customer) to\s+(\w+)"), lambda m: m.group(1).capitalize()),
    (re.compile(r"\b[Tt]he (?:user|customer) can\b"), lambda m: "You can"),
    (re.compile(r"\b[Tt]he (?:user|customer) should\b"), lambda m: "You should"),
    (re.compile(r"\b[Tt]he (?:user|customer) needs to\b"), lambda m: "You need to"),
)


def customer_voice(text: str) -> str:
    """把官方 Q&A 里的客服口吻改成对客户说话的口吻。只改人称。"""
    for pattern, repl in AGENT_VOICE:
        text = pattern.sub(repl, text)
    return text


def step_title(text: str, limit: int = 60) -> str:
    first = SENTENCE.split(text.strip(), maxsplit=1)[0].strip()
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def step_condition(text: str) -> str | None:
    """操作步骤开头的场景前提（rv-0106：卡在楼梯 / 家具边缘时设禁区）；续接上一步结果的条件不算。"""
    match = CONDITION.match(text)
    if match is None or CONTINUATION.search(match.group("cond")):
        return None
    return match.group("cond").strip()


def plan_of(guide: Guide, version: str) -> tuple[dict, dict[str, dict]]:
    texts = [(pos, s) for pos, s in enumerate(guide.steps, 1) if not s.disabled]
    evidence: dict[str, dict] = {}
    steps = []
    # 步骤 id 按原文位置编号（s{pos}）：编号在条目里会重复（rv-0004、bp-0114 每段从 1 起），
    # 禁用的段落跳过但不重排，card_id 由 step_id 派生，覆写一段不能让后面的卡全部换 id。
    positions = [pos for pos, _ in texts]
    if guide.sections:
        key = f"{guide.qa_id}#select_scope"
        instruction = "Which of these problems are you experiencing? Choose the matching section."
        options = [section.title for section in guide.sections]
        evidence[key] = {"source": "kb_qa", "doc_version": version, "snippet": instruction + "\n" + "\n".join(options)}
        steps.append({
            "step_id": "select_scope", "title": instruction, "instruction_src": f"evidence:{key}",
            "expected_result": ANSWER_EXPECTED, "kind": "question", "options": options,
            "branches": {section.title: f"s{section.start}" for section in guide.sections},
            "next_on": {"solved": "EXHAUSTED", "not_solved": "EXHAUSTED", "cannot_do": "EXHAUSTED"},
            "required_resources": [],
        })
    for i, (pos, step) in enumerate(texts):
        step_id = f"s{pos}"
        nxt = f"s{positions[i + 1]}" if i + 1 < len(positions) else "EXHAUSTED"
        section = next((s for s in guide.sections if s.start <= pos <= s.end), None)
        if section and (i + 1 == len(positions) or positions[i + 1] > section.end):
            nxt = "EXHAUSTED"
        key = f"{guide.qa_id}#{step_id}"
        evidence[key] = {"source": "kb_qa", "doc_version": version, "snippet": step.text}
        kind = step.kind
        # 只有操作步骤才有「解决了 / 没解决」的语义；问句按回答分支，说明与材料请求一律向后走；
        # 交人工段落走完就耗尽（进质保 / 人工流程）。
        if kind == "action":
            next_on = {"solved": "DONE", "not_solved": "EXHAUSTED" if step.warranty else nxt, "cannot_do": nxt}
        elif kind == "handoff":
            next_on = {"solved": "DONE", "not_solved": "EXHAUSTED", "cannot_do": "EXHAUSTED"}
        else:
            next_on = {"solved": nxt, "not_solved": nxt, "cannot_do": nxt}
        steps.append({
            "step_id": step_id,
            # 单步答案的首句就是正文开头，当标题只会重复；用 Q&A 标题（问的是什么问题）更有信息量
            "title": (step_title(guide.title, 80) if len(texts) == 1 else step_title(step.text)) or guide.title[:60],
            "instruction_src": f"evidence:{key}",
            "expected_result": EXPECTED_BY_KIND[kind],
            "caution": TIPS_LEAD.sub("", guide.tips).strip() or None,
            "next_on": next_on,
            "kind": kind,
            "source_gap": step.source_gap,
            "options": list(step.options),
            "branches": {option: f"s{target}" for option, target in step.branches.items()},
            "required_resources": ["device"] if kind == "action" else [],
            "condition": step_condition(step.text) if kind == "action" else None,
        })
    plan = {
        "plan_id": guide.plan_id,
        "version": 1,
        "fault": guide.title[:200],
        "applies_to": {"scope": "sku", "category": guide.category, "sku_list": list(guide.pns)},
        "symptom_codes": list(guide.codes),
        "steps": steps,
    }
    return plan, evidence


def plans_config(index: QAIndex) -> PlansConfig:
    plans, evidence = [], {}
    for guide in index.guides.values():
        if not guide.visible:
            continue
        plan, ev = plan_of(guide, index.version)
        plans.append(plan)
        evidence.update(ev)
    return PlansConfig.model_validate({"version": index.version, "evidence": evidence, "plans": plans})


def qa_plan_library(index: QAIndex | None = None) -> PlanLibrary:
    return PlanLibrary(plans_config(index or get_qa_index()))


def guide_of(plan_id: str) -> Guide | None:
    return get_qa_index().guides.get(plan_id.removeprefix("qa_").replace("_", "-"))
