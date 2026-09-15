"""Independent text gold evaluated through the same interpreter as live sessions."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.conversation.history import ConversationEntry
from app.conversation.interpret import interpret_turn
from app.conversation.tasks import ordered_intents
from app.emotion.policy import evaluate_emotion
from app.settings import REPO_ROOT

MODEL_KINDS = ("intent", "routing", "emotion")


class SemanticCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    family: str
    text: str
    history: list[str] = Field(default_factory=list)
    expected: dict


def load_cases(kind):
    path = REPO_ROOT / f"data/eval/{kind}/semantic-gold.yaml"
    cases = [SemanticCase.model_validate(c) for c in yaml.safe_load(path.read_text())["cases"]]
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("semantic gold must have unique, nonempty cases")
    for case in cases:
        if not case.expected or set(case.expected) - {
            "primary_intent",
            "intents",
            "order",
            "emotion_level",
        }:
            raise ValueError(f"unsupported expected fields: {case.id}")
    return cases, hashlib.sha256(path.read_bytes()).hexdigest()


def scenario(case):
    # Gold labels never enter the interpreter's state or prompt.
    at = "2026-09-14T12:00:00+08:00"
    texts = [*case.history, case.text]
    entries = [
        ConversationEntry(
            entry_id=f"input-{i}",
            session_id="l3-semantic-eval",
            run_id=f"run-{i}",
            kind="message",
            role="user",
            first_seq=i,
            last_seq=i,
            recorded_at=at,
            received_at=at,
            text=text,
            issue_id="issue",
            processing_status="completed",
        ).as_dict()
        for i, text in enumerate(texts, 1)
    ]
    return {
        "session_id": "l3-semantic-eval",
        "active_issue_id": "issue",
        "input_id": entries[-1]["entry_id"],
        "input_seq": len(entries),
        "at": at,
        "text": case.text,
        "entry": "message",
        "history": entries,
        "issues": {"issue": {"issue_id": "issue", "title": "售后咨询", "facts": []}},
        "risk_cases": [],
    }


def judge(case, meaning, *, source):
    intents = list(dict.fromkeys([meaning.primary_intent, *meaning.secondary_intents]))
    order = ordered_intents(meaning.primary_intent, meaning.secondary_intents)
    emotion = evaluate_emotion(meaning.emotion_level, case.text, [], case.id)["emotion"]["level"]
    actual = {
        "primary_intent": meaning.primary_intent,
        "intents": sorted(intents),
        "order": order,
        "emotion_level": emotion,
        "model_emotion_level": meaning.emotion_level,
    }
    errors = [] if source == "model" else ["model_unavailable"]
    for field, expected in case.expected.items():
        if actual[field] != (sorted(expected) if field == "intents" else expected):
            errors.append(field)
    return actual, errors


async def run_model(kind, output: Path, *, lane=None, router=None):
    from app.models.runtime import get_model_router
    from app.replay.runtime import versions_now

    cases, fingerprint = load_cases(kind)
    router = router or get_model_router()
    if router is None:
        raise RuntimeError("model evaluation requires HAIKE_LLM=on and a configured model router")
    rows = []
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": kind,
        "mode": "model",
        "source": "synthetic_independent_text_gold",
        "dataset_sha256": fingerprint,
        "versions": versions_now(),
        "lane": lane or router.registry.cfg.default_lane,
        "at": datetime.now(UTC).isoformat(),
        "planned": len(cases),
        "cases": rows,
    }
    for case in cases:
        start = time.monotonic()
        meaning, context = await interpret_turn(router, scenario(case), lane=lane)
        actual, errors = judge(case, meaning, source=context.get("source"))
        rows.append(
            {
                "id": case.id,
                "family": case.family,
                "text": case.text,
                "expected": case.expected,
                "actual": actual,
                "errors": errors,
                "model": context.get("model_used"),
                "latency_ms": round((time.monotonic() - start) * 1000),
            }
        )
        fields = {field for row in rows for field in row["expected"]}
        report.update(
            total=len(rows),
            passed=sum(not row["errors"] for row in rows),
            complete=len(rows) == len(cases),
            field_accuracy={
                field: sum(
                    field not in row["errors"] and "model_unavailable" not in row["errors"]
                    for row in rows
                    if field in row["expected"]
                )
                / sum(field in row["expected"] for row in rows)
                for field in fields
            },
        )
        report["accuracy"] = report["passed"] / report["total"]
        (output / f"{kind}-model.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(f"{kind} {len(rows)}/{len(cases)} {case.id}: {errors or 'PASS'}", flush=True)
    return report
