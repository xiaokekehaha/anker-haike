"""官方 Q&A → 计划：步骤类型、问句分支、禁用段落（2026-10-09 第二批 I4）。"""

from app.official.qa_index import get_qa_index
from app.plans.qa import ANSWER_EXPECTED, MATERIAL_EXPECTED, plan_of, qa_plan_library


def test_question_steps_carry_options_branches_and_no_feedback_semantics():
    plan, _ = plan_of(get_qa_index().guides["bp-0032"], "v")
    first = plan["steps"][0]
    assert first["kind"] == "question" and first["options"] == ["Breast shield opening", "Bottle connection"]
    assert first["branches"] == {"Breast shield opening": "s2", "Bottle connection": "s3"}
    assert first["expected_result"] == ANSWER_EXPECTED
    assert first["next_on"] == {"solved": "s2", "not_solved": "s2", "cannot_do": "s2"}


def test_disabled_steps_are_skipped_without_renumbering():
    """bp-0123 第 9、10 段禁用：计划里没有 s9 / s10，但其余 step_id 仍按原位置编号（card_id 不漂移）。"""
    plan, evidence = plan_of(get_qa_index().guides["bp-0123"], "v")
    ids = [s["step_id"] for s in plan["steps"]]
    assert "s9" not in ids and "s10" not in ids and "s8" in ids and "s11" in ids
    assert "bp-0123#s9" not in evidence
    kinds = {s["step_id"]: s["kind"] for s in plan["steps"]}
    assert kinds["s1"] == "statement" and kinds["s2"] == "question" and kinds["s5"] == "material_request" and kinds["s11"] == "handoff"
    # 禁用段落被跳过后，前一段的 not_solved 指向下一个仍存在的步骤
    s8 = next(s for s in plan["steps"] if s["step_id"] == "s8")
    assert s8["next_on"]["not_solved"] == "s11"
    s11 = next(s for s in plan["steps"] if s["step_id"] == "s11")
    assert s11["next_on"]["not_solved"] == "EXHAUSTED"
    s5 = next(s for s in plan["steps"] if s["step_id"] == "s5")
    assert s5["expected_result"] == MATERIAL_EXPECTED


def test_statement_steps_do_not_wait_for_feedback():
    plan, _ = plan_of(get_qa_index().guides["bp-0123"], "v")
    s1 = plan["steps"][0]
    assert s1["kind"] == "statement" and s1["next_on"] == {"solved": "s2", "not_solved": "s2", "cannot_do": "s2"}


def test_library_validates_branch_targets():
    library = qa_plan_library()
    plan = library.get("qa_bp_0032")
    assert plan.step("s1").branches["Bottle connection"] == "s3"
    assert plan.step("s1").kind == "question"


def test_request_to_donate_a_video_is_a_material_request():
    """bp-0199 第 2 段「Donate a video for further analysis」是请客户交视频，不是设备操作；按操作卡发会问「解决了吗」（T58）。
    判定看客户要交付什么（照片 / 视频交给售后），donate / submit 与 send / upload 同属交付动词；全库只有这一段因此改变。"""
    plan, _ = plan_of(get_qa_index().guides["bp-0199"], "v")
    kinds = {s["step_id"]: s["kind"] for s in plan["steps"]}
    assert kinds == {"s1": "action", "s2": "material_request", "s3": "action", "s4": "action"}
