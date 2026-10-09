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
TIPS_LEAD = re.compile(r"^[\s*•\-]*(?:Additional\s+)?Tips?\s*[:：]?\s*", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?。！？])\s")

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


def plan_of(guide: Guide, version: str) -> tuple[dict, dict[str, dict]]:
    texts = [(s.no, s.text, s.warranty) for s in guide.steps] if guide.kind == "steps" else [(1, guide.answer, guide.kind == "warranty")]
    evidence: dict[str, dict] = {}
    steps = []
    # 步骤 id 按位置编号：有的条目分几段、每段编号从 1 重新开始（rv-0004、bp-0114）。
    for index, (_no, text, warranty) in enumerate(texts):
        step_id = f"s{index + 1}"
        nxt = f"s{index + 2}" if index + 1 < len(texts) else "EXHAUSTED"
        key = f"{guide.qa_id}#{step_id}"
        evidence[key] = {"source": "kb_qa", "doc_version": version, "snippet": text}
        steps.append({
            "step_id": step_id,
            # 单步答案的首句就是正文开头，当标题只会重复；用 Q&A 标题（问的是什么问题）更有信息量
            "title": (step_title(guide.title, 80) if len(texts) == 1 else step_title(text)) or guide.title[:60],
            "instruction_src": f"evidence:{key}",
            "expected_result": EXPECTED,
            "caution": TIPS_LEAD.sub("", guide.tips).strip() or None,
            "next_on": {
                "solved": "DONE",
                "not_solved": "EXHAUSTED" if warranty else nxt,
                "cannot_do": nxt,
            },
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
