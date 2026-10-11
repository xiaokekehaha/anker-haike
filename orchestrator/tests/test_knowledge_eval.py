"""haike-kb eval：63 单工单首封 → 检索范围与查询；打分、汇总与报告（不连 WeKnora，检索用假适配器）。"""

from __future__ import annotations

from app.diagnose.query import build_query
from app.knowledge.adapter import Hit, ToolResult
from app.knowledge.eval import case_state, evaluate, gold_of, render_markdown, score_case, summarize
from app.official.models import OfficialData

BODIES = {t.id: t.body for t in OfficialData().tickets}


def _hit(doc: str) -> Hit:
    return Hit(doc, "k", doc, doc, "v", "kb_qa", "s", 0.5)


def test_pn_in_first_message_scopes_to_that_model():
    state, scope = case_state({"id": "T20"}, BODIES["T20"])
    assert (scope.product_state, scope.sku, scope.category) == ("confirmed_sku", "T2351", "robot_vacuum")
    # 范围已按 PN 锁定：查询只留问题描述，不拼型号名、表头和图片链接
    query = build_query(state)
    assert query.startswith("Kan positie niet bepalen") and "http" not in query and "Productnaam" not in query


def test_unique_model_name_without_pn_is_confirmed():
    _, scope = case_state({"id": "T61"}, "omni c20  isn't following my schedule")
    assert (scope.product_state, scope.sku) == ("confirmed_sku", "T2280")


def test_single_product_category_is_confirmed_and_unknown_product_has_no_scope():
    # 吸奶器品类只有 T8D04：品类即型号，与线上消歧一致
    _, scope = case_state({"id": "T54"}, "My breast pump has weak suction on the left side.")
    assert (scope.product_state, scope.sku) == ("confirmed_sku", "T8D04")
    _, none = case_state({"id": "x"}, "It stopped working.")
    assert none is None


def test_gold_merges_exact_and_semantic_labels():
    assert gold_of({"qa_exact": "rv-0147"}) == ["rv-0147"]
    assert gold_of({"qa_gold": ["bp-0102", "bp-0043"]}) == ["bp-0102", "bp-0043"]
    assert gold_of({"id": "T1"}) == []


def test_score_case_hit_and_rank_within_top_k():
    hits = [_hit("rv-0001"), _hit("rv-0218"), _hit("rv-0106")]
    assert score_case(["rv-0106"], hits, 5) == {
        "doc_ids": ["rv-0001", "rv-0218", "rv-0106"], "hit": True, "first_rank": 3,
    }
    assert score_case(["rv-0106"], hits, 2)["hit"] is False


def test_summarize_reports_recall_by_language_for_semantic_cases_only():
    rows = [
        {"id": "a", "language": "en", "exact": False, "gold": ["x"], "status": "ok", "hit": True, "latency_ms": 10},
        {"id": "b", "language": "nl", "exact": False, "gold": ["y"], "status": "ok", "hit": False, "latency_ms": 20},
        {"id": "c", "language": "en", "exact": True, "gold": ["z"], "status": "ok", "hit": False, "latency_ms": 30},
    ]
    s = summarize(rows, top_k=5)
    assert s["semantic_cases"] == 2 and s["recall@5"] == "50%"
    assert s["exact_also_retrieved@5"] == "0%"
    assert s["by_language"] == {"en": {"n": 1, "recall@5": "100%"}, "nl": {"n": 1, "recall@5": "0%"}}
    md = render_markdown(arm="A", summary=s, rows=rows, top_k=5)
    assert "| nl | 1 | 0% |" in md and "| c | en | 是 |" in md


def test_query_keeps_the_subject_when_the_symptom_is_a_bare_pronoun():
    """T34 复测：模型把「cannot use them」抽成症状，主语是 maps；检索词只有代词时整条 Q&A 都召不回。"""
    state = {
        "product_state": "confirmed_sku", "product_confirmed": {"sku": "T2080", "name": "S1 Pro"},
        "symptoms": ["cannot use them"], "active_issue_id": "i",
        "issues": {"i": {"facts": [{"kind": "symptom", "value": "cannot use them", "subject": "maps", "status": "active"}]}},
    }
    assert build_query(state) == "maps cannot use them"


def test_query_does_not_repeat_a_subject_already_in_the_symptom():
    state = {
        "product_state": "confirmed_sku", "product_confirmed": {"sku": "T2080"},
        "symptoms": ["charging case will not charge"], "active_issue_id": "i",
        "issues": {"i": {"facts": [{"kind": "symptom", "value": "charging case will not charge", "subject": "charging case", "status": "active"}]}},
    }
    assert build_query(state) == "charging case will not charge"



class _Adapter:
    """按查询返回预设命中，记录收到的查询（评测与线上共用 search_round）。"""

    def __init__(self, table):
        self.table, self.queries = table, []

    async def refresh_index(self):
        return None

    async def hybrid_search(self, kb, query, top_k, allow):
        self.queries.append(query)
        return ToolResult("ok", [_hit(d) for d in self.table.get(query, [])], kb=kb, query=query, allowed_count=5)


async def test_eval_uses_the_english_description_like_the_graph():
    """--english：评测与线上 retrieve 一样原文 + 英文双路，报告逐单记下用了哪句英文。"""
    case = {"id": "T43", "language": "es", "qa_gold": ["rv-0271"]}
    query = build_query(case_state(case, BODIES["T43"])[0])
    adapter = _Adapter({query: ["rv-0106", "rv-0107"], "robot cannot connect to Wi-Fi": ["rv-0271"]})
    single = await evaluate(adapter, [case], BODIES, top_k=5)
    assert single[0]["hit"] is False and adapter.queries == [query]
    adapter.queries.clear()
    dual = await evaluate(adapter, [case], BODIES, top_k=5, english={"T43": "robot cannot connect to Wi-Fi"})
    assert adapter.queries == [query, "robot cannot connect to Wi-Fi"]
    assert dual[0]["hit"] is True and dual[0]["query_en"] == "robot cannot connect to Wi-Fi"
