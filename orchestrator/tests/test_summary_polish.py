"""票 41：摘要可选模型调用不可改变核对事实/资格边界，失败和取消行为。"""

import asyncio

import pytest

from app.escalation.polish import polish_summary
from app.escalation.summary import build_summary, summary_to_text
from tests.test_vision import CONFIG, _router


def summary():
    return build_summary(
        {
            "active_issue_id": "i", "issues": {"i": {"facts": [{"kind": "symptom", "value": "扫地机  X10 不吸了！还有异响。", "status": "active"}]}},
            "receipt": {
                "status": "order_product_mismatch",
                "conflicts": ["SKU 不一致"],
                "verified_facts": {},
                "next_step": "凭证与当前设备信息不一致，需人工核实",
            },
        },
        reason="R1",
        lane="domestic",
    )


def config():
    # 独立任务通过真实 ModelRouter 调用；只复用测试配置中的模型定义。
    return CONFIG


async def test_polish_invokes_internal_and_preserves_rule_fields(tmp_path):
    original = summary()
    router, fake = _router(
        tmp_path, config(), [{"problem": "扫地机 X10 不吸了。还有异响。"}]
    )
    out = await polish_summary(original, router, session_id="s", lane="domestic")
    assert out.problem == "扫地机 X10 不吸了。还有异响。"
    assert out.receipt == original.receipt and out.reason == original.reason
    assert out.model_trace[-1].task == "escalate.summary"
    call = fake.calls[0]
    assert call["metadata"]["task"] == "escalate.summary" and "internal" in call["tags"]
    assert '<data kind="summary_problem">' in call["messages"][-1].content
    text = summary_to_text(out)
    assert "SKU 不一致" in text and "可保" not in text and "标准质保" not in text


@pytest.mark.parametrize(
    "payload",
    [
        {"problem": "扫地机 X10 已确认可保，走标准质保"},
        {"problem": "扫地机 X10 吸了。还有异响。"},
        {"problem": "扫地机 X10 不吸了。还有异响。", "receipt": {"status": "order_verified"}},
    ],
)
async def test_unsafe_or_extra_fields_fall_back(tmp_path, payload):
    original = summary()
    router, _ = _router(tmp_path, config(), [payload] * 4)
    assert await polish_summary(original, router, session_id="s", lane="domestic") == original


async def test_model_failure_no_budget_and_no_model_fall_back(tmp_path):
    original = summary()
    router, fake = _router(tmp_path, config(), [RuntimeError("offline")] * 4)
    assert (
        await polish_summary(original, router, session_id="s", lane="domestic", budget_ms=0)
        == original
    )
    assert not fake.calls
    assert await polish_summary(original, None, session_id="s", lane="domestic") == original
    assert await polish_summary(original, router, session_id="s", lane="domestic") == original


async def test_cancel_propagates():
    class CancelledRouter:
        async def invoke(self, *args, **kwargs):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await polish_summary(summary(), CancelledRouter(), session_id="s", lane="domestic")
