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
            {"text": "物流状态", "last_consult_params": {"order_no": "Anker016"}},
            {"order_no": "Anker016"},
        ),
        ({"text": "查另一个订单物流", "last_consult_params": {"order_no": "Anker016"}}, {}),
        (
            {
                "text": "查物流 Anker003",
                "last_consult_params": {"order_no": "Anker016", "tracking_no": "Anker1234567-19"},
            },
            {"order_no": "Anker003"},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "i",
                "history": [history("查物流 Anker016"), history("物流状态", seq=2)],
            },
            {"order_no": "Anker016"},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "other",
                "history": [history("查物流 Anker016")],
            },
            {},
        ),
        (
            {
                "text": "物流状态",
                "active_issue_id": "i",
                "history": [history("查物流 Anker016"), history("查另一个订单物流", seq=2)],
                "receipt": {"status": "order_verified", "fields": {"order_no": "Anker016"}},
            },
            {},
        ),
        (
            {
                "text": "物流状态",
                "receipt": {"status": "order_verified", "fields": {"order_no": "Anker016"}},
            },
            {"order_no": "Anker016"},
        ),
        (
            {
                "text": "保修状态",
                "execution": {
                    "receipt": {"order_no": "Anker016", "service_order_no": "SRV-123456ABCDEF"}
                },
            },
            {"order_no": "Anker016", "service_order_no": "SRV-123456ABCDEF"},
        ),
    ],
)
def test_query_subject_resolution(state, expected):
    assert restore_legacy_params(state) == expected
