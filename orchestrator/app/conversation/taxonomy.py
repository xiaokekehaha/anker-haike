"""Controlled symptom codes and deterministic discriminator selection.

2026-09-17 起词表按品类分组（`categories.<category>.families / discriminators`，共享一个 version）：
- 品类已知时只在该品类内归一、选题；
- 品类未知时（intake 抽取阶段）用全部品类的并集归一，后面 decide 再按品类过滤计划；
- 没有词表的品类得到空 families —— 调用方据此走 category_coverage_missing（R5），
  而不是拿别的品类的判别题去问用户。
"""

import argparse
import hashlib
import json

import yaml

from app.settings import CONFIG_DIR


def taxonomy():
    return yaml.safe_load((CONFIG_DIR / "symptom_taxonomy.yaml").read_text())


def taxonomy_for(category):
    """某品类的 families / discriminators；未登记的品类返回空列表。"""
    spec = (taxonomy().get("categories") or {}).get(category or "") or {}
    return {
        "families": list(spec.get("families") or []),
        "discriminators": list(spec.get("discriminators") or []),
    }


def families(category=None):
    """品类给定 → 该品类的故障族；否则全部品类的并集（按 (fault_family, symptom_code) 去重）。"""
    if category:
        return taxonomy_for(category)["families"]
    out, seen = [], set()
    for spec in (taxonomy().get("categories") or {}).values():
        for family in spec.get("families") or []:
            key = (family["fault_family"], family["symptom_code"])
            if key not in seen:
                seen.add(key)
                out.append(family)
    return out


def _discriminators(category=None):
    if category:
        return taxonomy_for(category)["discriminators"]
    return [d for spec in (taxonomy().get("categories") or {}).values() for d in spec.get("discriminators") or []]


def normalize(text, category=None):
    result = []
    for family in families(category):
        for expression in family["expressions"]:
            index = text.casefold().find(expression.casefold())
            if index >= 0 and not any(
                text[max(0, index - 3) : index].endswith(n) for n in ("不是", "没有", "并非")
            ):
                result.append(
                    {
                        "fault_family": family["fault_family"],
                        "symptom_code": family["symptom_code"],
                        "quote": expression,
                    }
                )
                break
    return result


def select_discriminator(candidates, asked=(), category=None):
    choices = []
    for item in _discriminators(category):
        key = hashlib.sha256(item["question"].encode()).hexdigest()[:12]
        if key in asked or not set(candidates) <= set().union(*map(set, item["splits"].values())):
            continue
        sizes = [len(set(candidates) & set(v)) for v in item["splits"].values()]
        if min(sizes) > 0:
            choices.append((min(sizes), {**item, "key": key}))
    return max(choices, key=lambda item: item[0])[1] if choices else None


def discriminator(candidates, category=None):
    question = select_discriminator(candidates, category=category)
    return question["question"] if question else None


def canonical_codes(quote, model_code=None, category=None):
    rules = [item["symptom_code"] for item in normalize(quote, category)]
    known = {f["symptom_code"] for f in families(category)}
    codes = rules or ([model_code] if model_code in known else [])
    disagreement = {"model_code": model_code, "rule_codes": rules} if model_code and (model_code not in known or (rules and model_code not in rules)) else None
    return codes, disagreement


def response_attempts(interview):
    """Legacy accepted answers count once; new records also cover unparsed replies."""
    current = list((interview or {}).get("response_attempts", []))
    recorded = {a["input_id"] for a in current}
    legacy = [
        {"input_id": a["input_id"], "question": a["question"],
         "outcome": a["answer"], "progressed": a["answer"] != "unknown"}
        for a in (interview or {}).get("answers", []) if a["input_id"] not in recorded
    ]
    return [*legacy, *current]


def record_response(interview, *, input_id, outcome, candidates, progressed, quote=""):
    attempts = response_attempts(interview)
    if any(a["input_id"] == input_id for a in attempts):
        return interview
    question = interview.get("question") or {}
    return {**interview, "response_attempts": [*attempts, {
        "input_id": input_id, "question_id": question.get("question_id"),
        "question": question.get("question"), "outcome": outcome,
        "candidates_before": list(interview.get("candidates", [])),
        "candidates_after": list(candidates), "progressed": progressed, "quote": quote,
    }]}


def interview_answer(interview, answer, text, input_id):
    """A quoted answer applies only to the currently asked question, once."""
    if not interview or not answer:
        return interview, False
    if interview.get("taxonomy_version") not in {None, taxonomy()["version"]}:
        return interview, False
    question = interview.get("question")
    if not question or answer.question_id != question["question_id"] or not answer.quote.strip() or answer.quote not in text:
        return interview, False
    answers = list(interview.get("answers", []))
    if any(a["input_id"] == input_id for a in answers):
        return interview, False
    candidates = interview["candidates"]
    selected = []
    if question.get("kind") == "symptom_selection":
        allowed = {o["value"] for o in question["options"]}
        selected = list(dict.fromkeys(answer.selected_families))
        if answer.answer == "unknown" and selected:
            return interview, False
        if answer.answer != "unknown" and (answer.answer != "selection" or not selected or not set(selected) <= allowed):
            return interview, False
        if selected:
            candidates = selected
    elif answer.answer == "selection":
        return interview, False
    if answer.answer in {"yes", "no"}:
        candidates = [f for f in candidates if f in question["splits"][answer.answer]]
    interview = record_response(
        interview, input_id=input_id, outcome=answer.answer, candidates=candidates,
        progressed=(set(candidates) != set(interview["candidates"]) or bool(selected)),
        quote=answer.quote,
    )
    answers.append({"key": question["key"], "question": question["question"], "answer": answer.answer, "quote": answer.quote, "input_id": input_id,
                    **({"selected_families": selected} if selected else {})})
    return {**interview, "candidates": candidates, "answers": answers, "question": None,
            "status": "narrowed" if len(candidates) == 1 else "asking"}, True


def next_interview(interview, issue_id, input_id, category=None):
    """问诊状态机的下一问。品类记在 interview 里：词表版本或品类变了就从头开始。"""
    cfg = taxonomy()
    current = dict(interview or {})
    category = category or current.get("category")
    if current.get("taxonomy_version") != cfg["version"] or current.get("category") != category:
        current = {
            "taxonomy_version": cfg["version"],
            "category": category,
            "candidates": [f["fault_family"] for f in families(category)],
            "answers": [],
            "status": "asking",
        }
    question = select_discriminator(current["candidates"], [a["key"] for a in current["answers"]], category=category)
    if not question and current["candidates"]:
        # 没有手写判别题能再切分剩余候选：这是配置的边界，不是用户答错。直接让用户在剩余现象里选。
        # 选项文案用词表里的 selection_label（用户视角的说法），没有就用故障族名。
        labels = {f["fault_family"]: f.get("selection_label") or f["fault_family"] for f in families(category)}
        options = [{"value": f, "label": labels.get(f, f)} for f in current["candidates"]]
        text = "具体有哪些现象（可多选）？" + "；".join(f"{i}．{o['label']}" for i, o in enumerate(options, 1)) + "。也可以描述其他现象，或回答不确定。"
        question = {"kind": "symptom_selection", "question": text, "options": options,
                    "key": hashlib.sha256(text.encode()).hexdigest()[:12]}
    if question:
        current["question"] = {**question, "asked_input_id": input_id, "question_id": f"{issue_id}:{input_id}:{question['key']}"}
    else:
        current["question"] = None
    return current


def interview_codes(interview):
    if not interview or interview.get("status") != "narrowed":
        return []
    return [f["symptom_code"] for f in families(interview.get("category")) if f["fault_family"] in interview["candidates"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export-synonyms"])
    parser.parse_args()
    print(json.dumps([f["expressions"] for f in families()], ensure_ascii=False, indent=2))
