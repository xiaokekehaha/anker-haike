"""官方 63 单复测 P2：措辞不预设事实、充电盒对象不被换成泵、材料请求与操作反馈分开、缺资料不是查询。

模型与知识库均为假；只检查服务端的确定性约束与客户可见文案。
"""

from datetime import date

import pytest

from app.backends import logistics
from app.conversation.interpret import TurnInterpretation
from app.conversation.reply import fallback_reply
from app.conversation.request_constraints import ground_additional_queries
from app.diagnose.charging import check_charging_recipient
from app.official.models import OfficialData
from app.plans.qa import ACTION_WITH_MATERIAL_EXPECTED, EXPECTED, qa_plan_library
from app.sessions.l3 import HARDWARE_BASIS

LIB = qa_plan_library()


def test_t9_presale_with_pending_hold_does_not_promise_shipping():
    """T9：暂缓已交人工后仍说「It will be sent on the expected ship date」。"""
    order = next(o for o in OfficialData().orders if o.order_no == "Anker008")
    as_of = date(2026, 10, 10)
    assert "It will be sent" in logistics.sop_text(order, as_of)
    held = logistics.sop_text(order, as_of, change_pending=True)
    assert "will be sent" not in held and "original expected ship date" in held and "colleague" in held


def test_t14_hardware_basis_does_not_confirm_warranty():
    for text in HARDWARE_BASIS.values():
        assert "covered by warranty service" not in text and "depends on the check below" in text


def _complaint_state(**extra):
    return {"turn_decision": {"primary_intent": "complaint", "allowed_operations": True}, "input_id": "i1", **extra}


def test_t58_first_message_complaint_does_not_imply_earlier_service():
    """T58：首封只有一句抱怨，没有排障或案件，不说「we haven't solved this yet」。"""
    text = fallback_reply(_complaint_state())
    assert "haven't solved" not in text and "what it is doing" in text


def test_complaint_after_tried_steps_keeps_the_unresolved_wording():
    attempts = [{"plan_id": "p", "step_id": "s1", "card_id": "c1", "kind": "action", "feedback": "not_solved"}]
    assert fallback_reply(_complaint_state(step_attempts=attempts)).startswith("I'm sorry we haven't solved this yet.")


CASE_DEAD = [{"kind": "symptom", "value": "charging case will not charge", "quote": "My charging case will not charge",
              "subject": "charging case", "status": "active"}]


def test_b11_charging_case_fault_does_not_match_a_pump_power_guide():
    """B11：盒自身接电灯不亮，却选了 bp-0025「泵开不了机」长按泵电源键。"""
    assert check_charging_recipient(LIB.get("qa_bp_0025").fault, CASE_DEAD, CASE_DEAD) == ("mismatch", "charging case")
    # 标题讲充电盒的条目不受影响
    assert check_charging_recipient(LIB.get("qa_bp_0127").fault, CASE_DEAD, CASE_DEAD)[0] == "matched"


def test_robot_not_charging_is_unaffected():
    """T31：整机自己充不上电，标题不写 case 也不算对象不同。"""
    robot = [{"kind": "symptom", "value": "robot won't charge", "quote": "The robot won't charge when it is at the base station",
              "status": "active"}]
    assert check_charging_recipient(LIB.get("qa_rv_0473").fault, robot, robot)[0] == "unrelated"


def test_t40_action_with_material_request_says_they_are_separate():
    """T40：rv-0073 操作卡里顺带要照片 / 视频，卡上说明两件事分开，点「未解决」不等于交了材料。"""
    assert LIB.get("qa_rv_0073").steps[0].expected_result == ACTION_WITH_MATERIAL_EXPECTED
    assert LIB.get("qa_rv_0147").steps[0].expected_result == EXPECTED


@pytest.mark.parametrize("quote,kept", [
    ("I don't have my receipt right now.", False),            # B17
    ("I don't have my order number, can you find it?", True),  # 真在问
    ("What did I order?", True),
])
def test_b17_saying_material_is_missing_is_not_an_order_query(quote, kept):
    text = "Do not submit any replacement request yet. " + quote
    meaning = TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["order_query"],
        request_quotes={"replacement_request": "Do not submit any replacement request yet.", "order_query": quote},
        answer_request={"fields": ["order_no", "sku"], "quote": quote},
    )
    result, rejected = ground_additional_queries(meaning, text)
    assert ("order_query" in result.secondary_intents) is kept
    if not kept:
        assert rejected == [{"intent": "order_query", "reason": "lacks_material_not_query"}]
