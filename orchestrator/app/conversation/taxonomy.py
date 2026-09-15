"""Controlled symptom codes and deterministic discriminator selection."""

import argparse
import hashlib
import json

import yaml

from app.settings import REPO_ROOT


def taxonomy():
    return yaml.safe_load((REPO_ROOT / "config/symptom_taxonomy.yaml").read_text())


def normalize(text, category="robot_vacuum"):
    cfg = taxonomy()
    if category != cfg["category"]:
        return []
    result = []
    for family in cfg["families"]:
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


def select_discriminator(families, asked=()):
    choices = []
    for item in taxonomy()["discriminators"]:
        key = hashlib.sha256(item["question"].encode()).hexdigest()[:12]
        if key in asked or not set(families) <= set().union(*map(set, item["splits"].values())):
            continue
        sizes = [len(set(families) & set(v)) for v in item["splits"].values()]
        if min(sizes) > 0:
            choices.append((min(sizes), {**item, "key": key}))
    return max(choices, key=lambda item: item[0])[1] if choices else None


def discriminator(families):
    question = select_discriminator(families)
    return question["question"] if question else None


def canonical_codes(quote, model_code=None, category=None):
    cfg = taxonomy()
    if category and category != cfg["category"]:
        return [], None
    rules = [item["symptom_code"] for item in normalize(quote)]
    known = {f["symptom_code"] for f in cfg["families"]}
    codes = rules or ([model_code] if model_code in known else [])
    disagreement = {"model_code": model_code, "rule_codes": rules} if model_code and (model_code not in known or (rules and model_code not in rules)) else None
    return codes, disagreement


def interview_answer(interview, answer, text, input_id):
    """A quoted answer applies only to the currently asked question, once."""
    if not interview or not answer:
        return interview, False
    question = interview.get("question")
    if not question or answer.question_id != question["question_id"] or not answer.quote.strip() or answer.quote not in text:
        return interview, False
    answers = list(interview.get("answers", []))
    if any(a["input_id"] == input_id for a in answers):
        return interview, False
    candidates = interview["candidates"]
    if answer.answer in {"yes", "no"}:
        candidates = [f for f in candidates if f in question["splits"][answer.answer]]
    answers.append({"key": question["key"], "question": question["question"], "answer": answer.answer, "quote": answer.quote, "input_id": input_id})
    return {**interview, "candidates": candidates, "answers": answers, "question": None,
            "status": "narrowed" if len(candidates) == 1 else "asking"}, True


def next_interview(interview, issue_id, input_id):
    cfg = taxonomy()
    current = dict(interview or {})
    if current.get("taxonomy_version") != cfg["version"]:
        current = {"taxonomy_version": cfg["version"], "candidates": [f["fault_family"] for f in cfg["families"]], "answers": [], "status": "asking"}
    question = select_discriminator(current["candidates"], [a["key"] for a in current["answers"]])
    if question:
        current["question"] = {**question, "question_id": f"{issue_id}:{input_id}:{question['key']}"}
    else:
        current["question"] = None
    return current


def interview_codes(interview):
    if not interview or interview.get("status") != "narrowed":
        return []
    return [f["symptom_code"] for f in taxonomy()["families"] if f["fault_family"] in interview["candidates"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export-synonyms"])
    parser.parse_args()
    print(
        json.dumps([f["expressions"] for f in taxonomy()["families"]], ensure_ascii=False, indent=2)
    )
