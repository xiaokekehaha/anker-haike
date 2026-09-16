"""证据锚点匹配（G2′ 主引用）与可达性基线的判定逻辑。

三类锚点的认法不同，这里逐类钉住；离线基线的 verdict 分类也在这里守住，
因为 kb-anchors 是要进 CI 的，误判会直接变成红灯噪音。
"""

from __future__ import annotations

from app.knowledge.anchors import anchor_marker, match_anchor
from app.knowledge.reachability import check_chunking

C12_TEXT = "翻转主机，按下滚刷盖两侧卡扣取出滚刷，用附带清洁刀具割断缠绕的毛发后装回。"
E1_TEXT = "确认基站电源灯亮，触点无灰尘。"


def _item(eid, doc_id, *, chunk_id="x", snippet="", full_text=None):
    out = {"evidence_id": eid, "doc_id": doc_id, "chunk_id": chunk_id, "snippet": snippet}
    if full_text:
        out["full_text"] = full_text
    return out


def test_anchor_marker_only_for_manual_chunks():
    assert anchor_marker("c12") == "（c12）"
    assert anchor_marker("q7") is None  # FAQ 自带精确 chunk_id，不需要正文标记
    assert anchor_marker("e1") is None  # 排障手册没有人工标记


def test_faq_matches_by_exact_chunk_id():
    """FAQ 索引按条目发命中，chunk_id 就是完整锚点。旧去重比对裸 q7 永远不相等。"""
    ev = {"faq_rv#q7": _item("faq_rv#q7", "faq_rv", chunk_id="faq_rv#q7", snippet="吸口被异物卡住")}
    assert match_anchor("faq_rv#q7", "吸口被异物卡住时清扫声音会变大。", ev) == ("faq_rv#q7", "exact_chunk")


def test_manual_matches_by_marker_not_by_doc():
    """同 doc 的其他小节不能冒充主引用——宽集合正是要靠这一点收窄。"""
    ev = {
        "hit-c15": _item("hit-c15", "manual_rv_v1", snippet="### 1.2 清洁滤网（c15）\n打开尘盒盖取出滤网"),
        "hit-c12": _item("hit-c12", "manual_rv_v1", snippet="### 1.1 清理滚刷（c12）\n" + C12_TEXT),
    }
    assert match_anchor("manual_rv_v1#c12", C12_TEXT, ev) == ("hit-c12", "marker")


def test_manual_falls_back_to_reviewed_text_when_marker_split_off():
    """标记与正文被切到不同块时仍要认得出，否则每一步都退回本地发布。"""
    ev = {"hit": _item("hit", "manual_rv_v1", snippet=C12_TEXT + "建议每周检查一次。")}
    assert match_anchor("manual_rv_v1#c12", C12_TEXT, ev) == ("hit", "text")


def test_marker_may_live_in_parent_full_text():
    ev = {"hit": _item("hit", "manual_rv_v1", snippet="建议每周检查一次。", full_text="（c12）" + C12_TEXT)}
    assert match_anchor("manual_rv_v1#c12", C12_TEXT, ev) == ("hit", "marker")


def test_unmarked_corpus_matches_by_reviewed_text():
    ev = {"hit": _item("hit", "troubleshooting_rv", snippet="## E. 充电问题\n1. " + E1_TEXT)}
    assert match_anchor("troubleshooting_rv#e1", E1_TEXT, ev) == ("hit", "text")


def test_no_match_when_doc_absent_or_contentless():
    """doc 不在 scope 内（manual_rv_v1 是 sku 文档）或命中没带正文 → 认不出，调用方退回本地发布。"""
    assert match_anchor("manual_rv_v1#c12", C12_TEXT, {}) == (None, "none")
    ev = {"c15": _item("c15", "manual_rv_v1")}  # 只有 doc_id，无正文
    assert match_anchor("manual_rv_v1#c15", "打开尘盒盖取出滤网。", ev) == (None, "none")


def test_chunking_verdicts():
    """B(i)：标记与正文同块与否，决定运行时能不能按标记认主引用。"""
    anchors = [
        {"evidence_key": "manual_rv_v1#c12", "doc_id": "manual_rv_v1", "chunk_id": "c12", "text": C12_TEXT},
        {"evidence_key": "manual_rv_v1#c15", "doc_id": "manual_rv_v1", "chunk_id": "c15", "text": "打开尘盒盖取出滤网，轻拍去尘。"},
        {"evidence_key": "troubleshooting_rv#e1", "doc_id": "troubleshooting_rv", "chunk_id": "e1", "text": E1_TEXT},
        {"evidence_key": "faq_rv#q7", "doc_id": "faq_rv", "chunk_id": "q7", "text": "吸口被异物卡住。"},
    ]
    by_doc = {
        "manual_rv_v1": [
            {"id": "k1", "content": "### 1.1 清理滚刷（c12）\n" + C12_TEXT},
            {"id": "k2", "content": "### 1.2 清洁滤网（c15）"},  # 标记落单，正文在下一块
            {"id": "k3", "content": "打开尘盒盖取出滤网，轻拍去尘。"},
        ],
        "troubleshooting_rv": [{"id": "t1", "content": "## E. 充电问题\n1. " + E1_TEXT}],
    }
    got = {r["evidence_key"]: r["verdict"] for r in check_chunking(anchors, by_doc)}
    assert got == {
        "manual_rv_v1#c12": "same_chunk",
        "manual_rv_v1#c15": "split",
        "troubleshooting_rv#e1": "text_only",
        "faq_rv#q7": "no_chunks",
    }
