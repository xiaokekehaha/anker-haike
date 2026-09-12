"""只读核查当前 Prompt / 状态更新行为；使用内存与依赖替身，不访问数据库或远程模型。

运行：cd orchestrator && uv run python ../docs/planning/2026-09-12_conversation-memory-design/probe_current_behavior.py
这是缺口复现脚本，报告当前行为，不是新功能通过验收的证明。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "orchestrator"))

from app.intake.extract import IntakeOutcome, build_messages  # noqa: E402
from app.prompts.reply import reply_messages  # noqa: E402
from app.sessions import graph  # noqa: E402


async def main() -> None:
    product = {"sku": "x9", "name": "X9 Pro", "category": "robot_vacuum", "in_scope": True}
    state = {
        "session_id": "memory-probe",
        "run_id": "r2",
        "text": "还是不行",
        "stage": "guide",
        "product_state": "confirmed_sku",
        "product_confirmed": product,
        "symptoms": ["吸力下降"],
        "messages": [{"role": "user", "text": "滤网已经清理过了"}],
        "visible_messages": [{"text": "请检查滚刷"}],
        "steps_executed": [{"step_id": "s1", "feedback": "not_solved"}],
    }
    outcome = IntakeOutcome(emotion={"level": "calm", "strategy": "normal"})
    extractor = AsyncMock(return_value=outcome)
    with (
        patch.object(graph, "get_stream_writer", return_value=lambda event: None),
        patch.object(graph, "get_rules_service", return_value=SimpleNamespace(
            check_in=lambda **kw: SimpleNamespace(flags=[], escalate=False)
        )),
        patch.object(graph, "get_model_router", return_value=None),
        patch.object(graph, "_delay", return_value=0),
        patch.object(graph, "extract_intake", extractor),
    ):
        update = await graph.intake(state)
        corrected = await graph.disambiguate({**state, "text": "刚才说错了，是 S1 Pro"})

    call = extractor.call_args
    intake_prompt = build_messages(call.args[1], has_image=False,
        prev_emotion=call.kwargs["prev_emotion"], state_summary=call.kwargs["state_summary"])
    evidence = [{"evidence_id": f"old-{i}", "snippet": f"旧证据{i}"} for i in range(6)]
    evidence.append({"evidence_id": "new-7", "snippet": "最新一轮相关证据"})
    primary, fallback = reply_messages(state["text"], strategy="normal",
        summary=graph._state_summary({**state, **update}), evidence=evidence, knowledge_status="ok")
    joined = lambda messages: "\n".join(text for _, text in messages)
    report = {
        "intake_roles": [role for role, _ in intake_prompt],
        "reply_roles": [role for role, _ in primary],
        "previous_user_text_in_intake": "滤网已经清理过了" in joined(intake_prompt),
        "previous_assistant_text_in_reply": "请检查滚刷" in joined(primary),
        "previous_symptoms": state["symptoms"],
        "symptoms_after_empty_extraction": update["symptoms"],
        "product_after_text_correction": ({**state, **corrected})["product_confirmed"]["name"],
        "latest_evidence_in_primary": "最新一轮相关证据" in joined(primary),
        "latest_evidence_in_fallback": "最新一轮相关证据" in joined(fallback),
        "stored_user_message_count": len(update["messages"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
