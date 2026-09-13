from app.context.builder import build_context
from app.conversation.history import fold_history
from app.conversation.reader import select_history
from tests.test_conversation_history import input_event, records


def long_history():
    source = []
    for i in range(31):
        source.extend(
            [
                input_event(f"i{i}", f"第{i}轮：设备现象", f"r{i}"),
                {"type": "message_start", "message_id": f"m{i}", "run_id": f"r{i}"},
                {
                    "type": "message",
                    "message_id": f"m{i}",
                    "delta": f"第{i}轮回答原文",
                    "run_id": f"r{i}",
                },
                {
                    "type": "message_end",
                    "message_id": f"m{i}",
                    "status": "completed",
                    "run_id": f"r{i}",
                },
            ]
        )
    source.append(input_event("current", "最开始我问的和你回答的是什么", "current_run"))
    return fold_history("s", records(source))


def test_first_question_and_answer_are_exact_after_thirty_turns():
    history = long_history()
    selected = select_history([e.as_dict() for e in history], {"mode": "first"}, before_seq=125)
    assert selected["source_entry_ids"] == ["i0", "m0"]
    bundle = build_context(
        history,
        current_input_id="current",
        now="2026-09-13T00:00:00Z",
        state={"recall_entry_ids": selected["source_entry_ids"]},
    )
    text = "\n".join(m[1] for m in bundle.messages)
    assert "第0轮：设备现象" in text and "第0轮回答原文" in text
    assert text.count("最开始我问的和你回答的是什么") == 1
    assert bundle.tokens <= 8000


def test_unknown_future_and_overlarge_history_are_not_fabricated():
    history = [e.as_dict() for e in long_history()]
    future = select_history(
        history, {"mode": "reference", "source_entry_ids": ["i30"]}, before_seq=50
    )
    assert future["source_entry_ids"] == [] and future["error"]
    invalid_time = select_history(
        history,
        {"mode": "time_range", "from_time": "2026-09-13", "to_time": "2026-09-14"},
        before_seq=125,
    )
    assert invalid_time["error"]
    missing = select_history([], {"mode": "first"}, before_seq=1000)
    assert missing["error"]


def test_reference_read_keeps_original_even_after_newer_messages():
    history = [e.as_dict() for e in long_history()]
    selected = select_history(
        history, {"mode": "reference", "source_entry_ids": ["i4"]}, before_seq=125
    )
    assert selected["source_entry_ids"] == ["i4", "m4"]
