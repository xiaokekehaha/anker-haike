"""步骤观察结果：写入 / 读取问题事实（issue.facts, kind=observation）。

设计（docs/planning/2026-09-16_diagnostic-loop-design/design.md §3.1）：
- 功能是否恢复（feedback 三态）与检查得到什么（观察选项）是两件事。
- 观察事实沿用现有事实写入与纠正机制：同一 observation_id 只有一份 active 事实，新结果 supersede 旧结果；
  unknown 选项、只说「不行」都不写成阴性结果。
- 事实绑定 card_id / plan / step / input_id；技术推论不写成用户观察。
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from app.plans.library import PlanLibrary
from app.plans.models import StepObservation

UNKNOWN_REPLIES = ("不知道", "不清楚", "无法判断", "没看", "没注意", "不确定", "没观察")
NEGATION_PREFIXES = ("不是", "没有", "并非", "不", "没")
RESELECT_OBSERVATION = "重新选择现象"


def stable_id(*parts) -> str:
    # 与 app.conversation.reduce.stable_id 同一算法；此处内联以避免模块循环引用。
    return uuid.uuid5(uuid.NAMESPACE_URL, ":".join(map(str, parts))).hex


def definitions() -> dict[str, StepObservation]:
    """进程级计划库的观察定义；计划库不可用时返回空（调用方按未知处理，不伪装成用户未回答）。"""
    from app.plans.library import PlansError
    from app.plans.runtime import get_plan_library

    try:
        return get_plan_library().observation_definitions()
    except (PlansError, OSError):
        return {}


def active_observation_facts(issue: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        f
        for f in issue.get("facts", [])
        if f.get("status") == "active" and f.get("kind") == "observation" and f.get("observation_id")
    ]


def interview_observations(
    interview: dict[str, Any] | None, definitions: dict[str, StepObservation]
) -> dict[str, dict[str, Any]]:
    """已接受的问诊 yes / no 回答按 interview_links 折算成观察结果；不复问用户已明确提供的信息。"""
    out: dict[str, dict[str, Any]] = {}
    if not interview or interview.get("superseded_by_input_id"):
        return out
    answers = [a for a in interview.get("answers", []) if a.get("answer") in {"yes", "no"}]
    for obs in definitions.values():
        for link in obs.interview_links:
            for a in answers:
                if a.get("question") == link.question and a["answer"] in link.answers:
                    out[obs.observation_id] = {
                        "option_id": link.answers[a["answer"]],
                        "source": "interview",
                        "source_id": a.get("input_id"),
                        "quote": a.get("quote"),
                    }
    return out


def known_observations(
    issue: dict[str, Any],
    interview: dict[str, Any] | None,
    library: PlanLibrary | None,
) -> dict[str, dict[str, Any]]:
    """当前有效观察：事实优先于问诊折算（事实是用户对具体步骤的明确选择或更正）。"""
    definitions = library.observation_definitions() if library else {}
    known = interview_observations(interview, definitions)
    revising = {
        r["observation_id"] for r in issue.get("observation_requests", [])
        if r.get("revision_input_id") and r.get("status") != "answered"
    }
    for f in active_observation_facts(issue):
        if f.get("option_id") and f["observation_id"] not in revising:
            known[f["observation_id"]] = {
                "option_id": f["option_id"],
                "source": "fact",
                "source_id": f["fact_id"],
                "quote": f.get("quote"),
            }
    return {key: value for key, value in known.items() if key not in revising}


def known_option_ids(known: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {k: v["option_id"] for k, v in known.items() if v.get("option_id")}


def record_observations(
    issue: dict[str, Any],
    answers: list[dict[str, str]],
    *,
    definitions: dict[str, StepObservation],
    input_id: str,
    at: str,
    source_kind: str,
    binding: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """把观察选项写成事实。返回 (更新后的 issue 副本, patches)。

    - 选项不属于该观察 → 忽略（旧卡 / 其他步骤的回答不能污染当前事实）。
    - unknown 选项 → 不写事实（保持未知）。
    - 已有相同 active 结果 → 去重不重复写。
    - 已有不同 active 结果 → 旧事实 superseded，新事实 revision+1。
    """
    issue = copy.deepcopy(issue)
    facts = issue.setdefault("facts", [])
    patches: list[dict[str, Any]] = []
    for index, answer in enumerate(answers):
        obs = definitions.get(answer.get("observation_id", ""))
        option = obs.option(answer.get("option_id", "")) if obs else None
        if obs is None or option is None or option.kind != "finding":
            continue
        current = next(
            (
                f
                for f in facts
                if f.get("status") == "active"
                and f.get("kind") == "observation"
                and f.get("observation_id") == obs.observation_id
            ),
            None,
        )
        if current and current.get("option_id") == option.option_id:
            continue
        fact = {
            "fact_id": stable_id(input_id, "observation", obs.observation_id, index),
            "kind": "observation",
            "context_field": None,
            "value": f"{obs.question}{option.label}",
            "issue_id": issue.get("issue_id"),
            "device_ref_id": (issue.get("device_ref") or {}).get("device_ref_id"),
            "status": "active",
            "revision": (current or {}).get("revision", 0) + 1,
            "source_kind": source_kind,
            "source_entry_ids": [input_id],
            "recorded_at": at,
            "occurred_at": None,
            "time_expression": None,
            "precision": None,
            "quote": option.label,
            "symptom_codes": [],
            "symptom_code": None,
            "observation_id": obs.observation_id,
            "option_id": option.option_id,
            "binding": dict(binding),
        }
        if current:
            current["status"] = "superseded"
            current["superseded_by_input_id"] = input_id
            fact["supersedes"] = current["fact_id"]
            patches.append({"op": "replace", "fact_id": fact["fact_id"], "input_id": input_id})
        else:
            patches.append({"op": "add", "fact_id": fact["fact_id"], "input_id": input_id})
        facts.append(fact)
    if patches:
        issue["issue_revision"] = issue.get("issue_revision", 0) + 1
        issue["observations"] = [
            f["value"] for f in facts if f["status"] == "active" and f["kind"] == "observation"
        ]
    return issue, patches


def match_reply(text: str, obs: StepObservation) -> str | None:
    """自由文本对观察问题的回答 → option_id / "unknown" / None。

    只接受唯一命中：命中多个选项或没有命中都返回 None，交由调用方决定是否换一种表达再问。
    """
    reply = text.strip().strip("。！!，,、 ")
    if not reply:
        return None
    if any(u in reply for u in UNKNOWN_REPLIES):
        return "unknown"
    if any(reply.casefold() == phrase.casefold()
           for option in obs.options if option.kind == "unknown"
           for phrase in [option.label, *option.phrases]):
        return "unknown"
    hits = matching_options(reply, obs)
    return hits[0] if len(hits) == 1 else None


def matching_options(text: str, obs: StepObservation, *, exact: bool = False) -> list[str]:
    """只消除同一文本范围内的包含匹配，不把两段独立现象按字数强行单选。"""
    lowered = text.strip(" \n。！!，,、").casefold()
    hits: list[tuple[str, int, int]] = []
    for option in obs.options:
        if option.kind != "finding":
            continue
        for phrase in [option.label, *option.phrases]:
            needle = phrase.casefold()
            if exact and lowered != needle:
                continue
            index = lowered.find(needle)
            if index < 0:
                continue
            prefix = lowered[max(0, index - 2) : index]
            if any(prefix.endswith(n) for n in NEGATION_PREFIXES) and not needle.startswith(
                tuple(n.casefold() for n in NEGATION_PREFIXES)
            ):
                continue
            hits.append((option.option_id, index, index + len(needle)))
    return list(dict.fromkeys(
        option_id for option_id, start, end in hits
        if not any(other_start <= start and end <= other_end and (other_start, other_end) != (start, end)
                   for _, other_start, other_end in hits)
    ))


def option_label(definitions: dict[str, StepObservation], observation_id: str, option_id: str) -> str:
    obs = definitions.get(observation_id)
    option = obs.option(option_id) if obs else None
    return option.label if option else option_id
