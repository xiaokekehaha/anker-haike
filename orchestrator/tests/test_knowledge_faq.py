"""本地 FAQ 索引（阶段 3）：相似度、阈值、scope、命中形状。"""

from __future__ import annotations

from app.knowledge.adapter import KnowledgeScope
from app.knowledge.faq import LocalFaqIndex, get_faq_index, set_faq_index, similarity
from app.settings import REPO_ROOT

FAQ = REPO_ROOT / "data" / "knowledge" / "kb_manual" / "faq_rv.yaml"
X10 = KnowledgeScope("confirmed_sku", "robot_vacuum", "EUFY-X10-PRO-OMNI")
CAT = KnowledgeScope("category_only", "robot_vacuum")
UNKNOWN = KnowledgeScope("unknown", "robot_vacuum")
PUMP = KnowledgeScope("confirmed_sku", "breast_pump", "EUFY-BP-S1-PRO")


def test_similarity_substring_and_bigram():
    assert similarity("扫地机吸力变小了怎么办", "扫地机吸力变小了怎么办") >= 0.99
    assert similarity("吸力变小", "扫地机吸力变小了怎么办") >= 0.85  # 子串
    assert 0.3 <= similarity("边刷不动了", "边刷不转怎么办") < 0.85
    assert similarity("App 连不上机器", "滚刷多久清理一次") < 0.3
    assert similarity("", "x") == 0.0


def test_index_from_repo_yaml_hits_expected_entries():
    idx = LocalFaqIndex.from_yaml(FAQ)
    assert len(idx.entries) == 50 and idx.docs == {"faq_rv": "2026-09-12.1"}
    assert {e.category for e in idx.entries} == {"robot_vacuum"}
    r = idx.search("EUFY-X10-PRO-OMNI App 无法连接", 3, X10)
    assert r.status == "ok" and r.hits[0].chunk_id == "faq_rv#q35"
    h = r.hits[0]
    assert h.source == "kb_faq" and h.doc_id == "faq_rv" and h.case_outcome == "n/a"
    assert h.snippet.startswith("问：App 连不上机器\n答：")
    assert r.allowed_count == 50
    r2 = idx.search("扫地机器人 滤网清洗", 3, CAT)
    assert r2.status == "ok" and {h.chunk_id for h in r2.hits} & {
        "faq_rv#q3",
        "faq_rv#q37",
        "faq_rv#q38",
    }


def test_index_threshold_blocks_unrelated_and_scope_blocks_unknown_and_other_category():
    idx = LocalFaqIndex.from_yaml(FAQ)
    assert idx.search("EUFY-X9-PRO 语音语言设置", 3, X10).status == "no_match"
    assert idx.search("扫地机不吸了", 3, UNKNOWN).status == "no_match"
    r = idx.search("扫地机不吸了", 3, PUMP)
    assert r.status == "no_match" and r.allowed_count == 0


def test_runtime_getter_loads_repo_file_and_can_be_overridden():
    set_faq_index(None)
    try:
        assert get_faq_index() is None  # 显式注入 None 生效
    finally:
        # 恢复为「未构建」状态，让下一次 get 走文件加载
        import app.knowledge.faq as mod

        mod._built = False
        mod._index = None
    idx = get_faq_index()  # 默认加载目录下全部 faq_*.yaml
    assert idx is not None and len(idx.entries) >= 50 and "faq_rv" in idx.docs and "faq_pb" in idx.docs
    mod._built = False
    mod._index = None
