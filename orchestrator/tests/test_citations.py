"""自由文本回复的事后引用归因（G1a）。

这里钉住的是判据本身：什么算「有据」、什么算「给了动作却无来源」。指标要先跑一周基线再
决定是否加门，判据漂了基线就没有可比性。
"""

from __future__ import annotations

from app.conversation.citations import attribute, sentences

C12 = "翻转主机，按下滚刷盖两侧卡扣取出滚刷，用附带清洁刀具割断缠绕的毛发后装回。"
C15 = "打开尘盒盖取出滤网，轻拍去尘并用清水冲洗，晾干 24 小时后装回。"
EV = [{"evidence_id": "c12", "snippet": C12}, {"evidence_id": "c15", "snippet": C15}]


def test_sentences_strips_markdown_list_markers_and_short_fillers():
    got = sentences("好的。\n1. 请先取出滚刷并清理缠绕的毛发\n- 然后洗一下滤网并晾干再装回")
    assert got == ["请先取出滚刷并清理缠绕的毛发", "然后洗一下滤网并晾干再装回"]


def test_action_sentence_matching_a_snippet_is_cited():
    out = attribute("我明白您的情况。请翻转主机，用清洁刀具割断缠绕的毛发后装回。", EV)
    assert out["citations"] == ["c12"]
    assert out["ungrounded"] == 0


def test_cites_each_source_once_in_evidence_order():
    out = attribute("先取出滤网，轻拍去尘并用清水冲洗，晾干 24 小时后装回。再按下滚刷盖两侧卡扣取出滚刷。", EV)
    assert out["citations"] == ["c15", "c12"]


def test_actions_without_any_matching_snippet_count_as_ungrounded():
    """R7 样本里模型自行给出的三步排查：读得通，但没有任何来源。"""
    out = attribute("请检查基站是否正常供电。再清洁一下充电触点。最后把机器重新放回基站。", EV)
    assert out["citations"] == []
    assert out["actionable"] == 3 and out["ungrounded"] == 3


def test_reassurance_and_questions_are_not_counted_as_ungrounded():
    """安抚、澄清提问本来就不该有引用，强行要求会让语气机械化。"""
    out = attribute("非常抱歉给您带来不便，我会尽快帮您处理。方便告诉我这台机器用了多久吗？", EV)
    assert out["citations"] == [] and out["actionable"] == 0 and out["ungrounded"] == 0


def test_no_evidence_makes_every_action_sentence_ungrounded():
    """按记录回答的路径不给证据：出现动作句即违反「不生成新的排障动作」。"""
    out = attribute("建议您先重启设备试试。再检查一下滤网是否需要清洗。", [])
    assert out["ungrounded"] == 2


def test_paraphrase_below_threshold_is_reported_as_ungrounded_not_cited():
    """字面匹配会漏判改写过的句子。偏差方向必须是保守的——宁可少认，不可错认。"""
    out = attribute("把滚刷拆下来，把上面缠的毛清理干净。", EV)
    assert out["citations"] == [] and out["ungrounded"] == 1


def test_action_detection_is_keyword_based_and_misses_colloquial_phrasing():
    """已知局限：口语说法不含动作词时不计入分母，ungrounded 会偏低。

    模型的实际输出是「请清理…」这类书面说法，扩大词表反而会把安抚语误判成动作句，
    所以这里选择让分母偏保守，并把这条限制显式钉住。
    """
    out = attribute("把那个部件拿下来，上面的毛弄一弄就好了。", EV)
    assert out["actionable"] == 0 and out["ungrounded"] == 0
