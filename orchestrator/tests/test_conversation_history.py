from datetime import UTC, datetime

from app.context.builder import build_context
from app.conversation.history import fold_history
from app.sessions.store import EventRecord


def records(events):
    return [
        EventRecord(
            i,
            e.get("run_id", "r1"),
            datetime(2026, 9, 13, tzinfo=UTC),
            {**e, "event_id": f"e{i}", "recorded_at": "2026-09-13T00:00:00+00:00"},
        )
        for i, e in enumerate(events, 1)
    ]


def input_event(iid="i1", text="耳机没声音", run_id="r1"):
    return {
        "type": "input_received",
        "input_id": iid,
        "input_kind": "message",
        "payload": {"text": text},
        "run_id": run_id,
    }


def test_fold_roles_timestamps_and_partial_reply_asof():
    source = records(
        [
            input_event(),
            {"type": "message_start", "message_id": "m1"},
            {"type": "message", "message_id": "m1", "delta": "请先"},
            {"type": "done", "reason": "cancelled"},
            {"type": "message_start", "message_id": "m2", "replaces": "m1", "run_id": "r2"},
            {"type": "message", "message_id": "m2", "delta": "具体哪个设备？", "run_id": "r2"},
            {"type": "message_end", "message_id": "m2", "status": "completed", "run_id": "r2"},
        ]
    )
    early = fold_history("s", source, through_seq=3)
    assert early[1].status == "streaming" and early[1].completed_at is None
    cancelled = fold_history("s", source, through_seq=4)
    assert cancelled[1].status == "aborted"
    history = fold_history("s", source)
    assert [h.role for h in history] == ["user", "assistant", "assistant"]
    assert history[1].status == "replaced"
    assert history[1].reply_to_input_id == "i1"
    assert history[0].received_at == history[1].started_at
    assert [h.first_seq for h in history] == [1, 2, 5]
    assert history[2].source_event_ids == ["e5", "e6", "e7"]


def test_actions_are_not_fake_user_speech_and_tools_keep_failures():
    history = fold_history(
        "s",
        records(
            [
                {
                    "type": "input_received",
                    "input_id": "a1",
                    "input_kind": "action",
                    "payload": {"kind": "request_human"},
                },
                {"type": "tool_call", "tool_id": "t1", "name": "vision", "status": "started"},
                {
                    "type": "tool_call",
                    "tool_id": "t1",
                    "name": "vision",
                    "status": "failed",
                    "summary": "图片已过期",
                },
            ]
        ),
    )
    assert history[0].kind == "action" and history[0].text == "请求人工"
    assert history[1].role == "tool" and history[1].status == "failed"


def test_context_contains_complete_question_answer_and_current_once():
    source = records(
        [
            input_event(),
            {"type": "message_start", "message_id": "m1"},
            {"type": "message", "message_id": "m1", "delta": "是否只有一侧没有声音？"},
            {"type": "message_end", "message_id": "m1", "status": "completed"},
            input_event("i2", "两侧都没有", "r2"),
        ]
    )
    bundle = build_context(
        fold_history("s", source), current_input_id="i2", now="2026-09-13T00:00:00Z", state={}
    )
    assert [role for role, _ in bundle.messages] == ["system", "human", "human", "ai", "human"]
    joined = "\n".join(text for _, text in bundle.messages)
    assert joined.count("两侧都没有") == 1
    assert "只有一侧" in joined and "2026-09-13" in joined
    assert bundle.source_entry_ids == ["i1", "m1", "i2"]


def test_budget_drops_whole_turns_not_assistant_half():
    source = []
    for i in range(10):
        source.extend(
            [
                input_event(f"i{i}", "问题" * 20, f"r{i}"),
                {"type": "message_start", "message_id": f"m{i}", "run_id": f"r{i}"},
                {"type": "message", "message_id": f"m{i}", "delta": "回答" * 20, "run_id": f"r{i}"},
                {
                    "type": "message_end",
                    "message_id": f"m{i}",
                    "status": "completed",
                    "run_id": f"r{i}",
                },
            ]
        )
    source.append(input_event("current", "继续", "current_run"))
    bundle = build_context(
        fold_history("s", records(source)),
        current_input_id="current",
        now="now",
        state={},
        max_tokens=1600,
    )
    assert bundle.tokens <= 1600 and bundle.omitted_entries > 0
    assert len(bundle.source_entry_ids[:-1]) % 2 == 0
