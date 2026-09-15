import pytest

from app.conversation.business_migration import restore_legacy_params


def history(text, *, issue="i", seq=1):
    return {
        "entry_id": str(seq),
        "first_seq": seq,
        "issue_id": issue,
        "role": "user",
        "kind": "message",
        "text": text,
        "processing_status": "completed",
    }


@pytest.mark.parametrize(
    "state,expected",
    [
        (
            {"text": "物流状态", "last_consult_params": {"order_no": "DEMO-X10-001"}},
            {"order_no": "DEMO-X10-001"},
        ),
        ({"text": "查另一个订单物流", "last_consult_params": {"order_no": "DEMO-X10-001"}}, {}),
        (
            {
                "text": "查物流 DEMO-UK-005",
                "last_consult_params": {"order_no": "DEMO-X10-001", "tracking_no": "TRACK-123456"},
            },
            {"order_no": "DEMO-UK-005"},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "i",
                "history": [history("查物流 DEMO-X10-001"), history("物流状态", seq=2)],
            },
            {"order_no": "DEMO-X10-001"},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "other",
                "history": [history("查物流 DEMO-X10-001")],
            },
            {},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "i",
                "history": [history("查物流 DEMO-X10-001"), history("查另一个订单物流", seq=2)],
                "receipt": {"status": "order_verified", "fields": {"order_no": "DEMO-X10-001"}},
            },
            {},
        ),
        (
            {
                "text": "物流状态",
                "receipt": {"status": "order_verified", "fields": {"order_no": "DEMO-X10-001"}},
            },
            {"order_no": "DEMO-X10-001"},
        ),
        (
            {
                "text": "保修状态",
                "execution": {
                    "receipt": {"order_no": "DEMO-X10-001", "service_order_no": "SRV-123456"}
                },
            },
            {"order_no": "DEMO-X10-001", "service_order_no": "SRV-123456"},
        ),
    ],
)
def test_query_subject_resolution(state, expected):
    assert restore_legacy_params(state) == expected
