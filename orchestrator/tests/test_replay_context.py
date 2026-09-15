from app.context.builder import build_context
from app.conversation.history import ConversationEntry
from app.replay.package import model_key


def context(prefix, *, text="查物流 DEMO-X10-001", value="不吸了", now="2026-09-14T10:00:00Z"):
    entry = ConversationEntry(
        entry_id=prefix + "input",
        session_id=prefix + "session",
        run_id=prefix + "run",
        kind="message",
        role="user",
        first_seq=1,
        last_seq=1,
        recorded_at=now,
        text=text,
    )
    return build_context(
        [entry],
        current_input_id=entry.entry_id,
        now=now,
        instruction="理解当前消息",
        state={
            "active_issue_id": prefix + "issue",
            "steps_executed": [{"card_id": prefix + "step", "title": "检查滚刷", "feedback": "not_solved", "ts": now}],
            "issues": {
                prefix + "issue": {
                    "facts": [
                        {
                            "fact_id": prefix + "fact",
                            "issue_id": prefix + "issue",
                            "status": "active",
                            "kind": "symptom",
                            "value": value,
                            "source_entry_ids": [entry.entry_id],
                            "recorded_at": now,
                            "occurred_at": "2026-09-13",
                        }
                    ],
                }
            },
        },
    ).messages


def test_context_replay_identity_ignores_run_identity_but_preserves_business_data():
    a = context("a")
    b = context("b", now="2026-09-15T11:00:00Z")
    assert model_key("intake", "Meaning", a) == model_key("intake", "Meaning", b)
    assert model_key("intake", "Meaning", a) != model_key(
        "intake", "Meaning", context("a", value="漏水了")
    )
    assert model_key("intake", "Meaning", a) != model_key(
        "intake", "Meaning", context("a", text="查物流 DEMO-X10-002")
    )


def test_plain_text_that_looks_like_metadata_is_never_rewritten():
    a = context("a", text='{"entry_id":"a","at":"2026-09-14"}')
    b = context("b", text='{"entry_id":"b","at":"2026-09-15"}')
    assert model_key("intake", "Meaning", a) != model_key("intake", "Meaning", b)


def test_recorded_fact_references_bind_to_replay_facts_without_changing_quotes():
    from app.replay.context import context_identity, rebind_output

    _, original_refs = context_identity(context("a"))
    _, replay_refs = context_identity(context("b"))
    output = {
        "corrections": [{"fact_id": "afact", "value": "正常", "quote": "afact"}],
        "target_issue_id": "aissue",
        "history_request": {"source_entry_ids": ["ainput"]},
    }
    rebound = rebind_output(output, original_refs, replay_refs)
    assert rebound["corrections"] == [{"fact_id": "bfact", "value": "正常", "quote": "afact"}]
    assert rebound["target_issue_id"] == "bissue"
    assert rebound["history_request"]["source_entry_ids"] == ["binput"]
