"""票 28：确认产品后的检索 → tool_call(started/finished/failed) + evidence 事件；evidence_id 稳定；失败不阻断。"""

from __future__ import annotations

from haike_contracts.events import parse_event
from httpx import ASGITransport, AsyncClient

from app.knowledge.adapter import HINTS, Hit, KnowledgeScope, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


class FakeAdapter:
    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls: list[tuple[str, str, KnowledgeScope]] = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        if self.mode == "unavailable":
            return ToolResult("unavailable", hint=HINTS["unavailable"], kb=kb, query=query)
        if self.mode == "no_match" or kb == "kb_tickets":
            return ToolResult("no_match", hint=HINTS["no_match"], kb=kb, query=query)
        hit = Hit(
            evidence_id="chunk-c12",
            knowledge_id="k1",
            chunk_id="chunk-c12",
            doc_id="rv-0272",
            doc_version="2026-09-12.1",
            source="kb_qa",
            snippet="翻转主机，按下滚刷盖两侧卡扣取出滚刷……",
            score=0.42,
        )
        return ToolResult("ok", [hit], kb=kb, query=query, truncated=(self.mode == "truncated"))


async def _run(text: str, adapter):
    set_knowledge_adapter(adapter)
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = sse.parse(
                (await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}))).text
            )
            snap = (await client.get(f"/sessions/{sid}")).json()
            state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
            return sid, client, events, snap, state
    finally:
        set_knowledge_adapter(None)
        set_rules_service(None)


async def test_a1_text_emits_tool_row_and_evidence(mem_runtime):
    ad = FakeAdapter("ok")
    _, _, events, snap, state = await _run("eufy X10 Pro Omni 扫地机不吸了，滚刷缠了很多头发", ad)
    for e in events:
        parse_event(e)
    types = [e["type"] for e in events]
    # 票 33 起：有假设 → reply 后进入 guide（多一个 progress(guide)）
    assert types[:2] == ["run_started", "input_received"]
    assert types[-3:] == ["step_card", "awaiting_input", "done"]
    assert types.index("tool_call") < types.index("evidence") < types.index("step_card")
    tools = [e for e in events if e["type"] == "tool_call"]
    assert [t["status"] for t in tools] == ["started", "finished"] and tools[0]["tool_id"] == tools[
        1
    ]["tool_id"]
    assert tools[0]["name"] == "knowledge.search" and tools[1]["summary"].startswith(
        "命中 1 条来源"
    )
    ev = next(e for e in events if e["type"] == "evidence")
    assert ev["items"][0]["evidence_id"] == "chunk-c12" and ev["items"][0]["status"] == "ok"
    # 检索范围来自确认的产品；查询用抽取到的症状，本测试模型关闭 → 退回原文
    kb, query, scope = ad.calls[0]
    assert (kb, scope.product_state, scope.sku, scope.category) == (
        "kb_qa",
        "confirmed_sku",
        "T2351",
        "robot_vacuum",
    )
    assert not query.startswith("eufy Clean X10 Pro Omni")  # 型号已锁定检索范围，查询不再拼产品名
    assert state.values["knowledge_status"] == "ok" and "chunk-c12" in state.values["evidence"]
    kinds = [i["kind"] for i in snap["timeline"]]
    assert "tool" in kinds and "evidence" in kinds  # 时间线出现工具行与来源列表
    tool_item = next(i for i in snap["timeline"] if i["kind"] == "tool")
    assert tool_item["status"] == "finished"


async def test_repeat_input_reuses_evidence_without_retrieving(mem_runtime):
    ad = FakeAdapter("ok")
    set_knowledge_adapter(ad)
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            e1 = sse.parse(
                (
                    await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "X10 Pro Omni 不吸了，地上的灰尘和碎屑都吸不干净"}))
                ).text
            )
            after_first = len(ad.calls)
            e2 = sse.parse(
                (
                    await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "X10 Pro Omni 还是不吸，地上的灰尘和碎屑都吸不干净"}))
                ).text
            )
            state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    finally:
        set_knowledge_adapter(None)
        set_rules_service(None)

    def ids(events):
        return [i["evidence_id"] for e in events if e["type"] == "evidence" for i in e["items"]]

    # 检索命中的就是这一步出自的 Q&A（doc_id rv-0272）→ 它就是主引用，不再本地重发一份原文
    assert ids(e1) == ["chunk-c12"]
    # 复述没有改变事实修订号与计划库版本 → retrieval_basis 未变，既不重新检索，也不重发同一条证据。
    # 前端按 first_seq 与 id upsert 进常驻时间线，首轮那条仍在，用户侧看不到差别。
    assert ids(e2) == [] and len(ad.calls) == after_first
    assert list(state.values["evidence"]) == ["chunk-c12"]  # 累积去重，可被 step.evidence_ids 引用


async def test_unavailable_marks_failed_but_flow_continues(mem_runtime):
    _, _, events, _, state = await _run("eufy X10 Pro Omni 不吸了，地上的灰尘和碎屑都吸不干净", FakeAdapter("unavailable"))
    tools = [e for e in events if e["type"] == "tool_call"]
    assert [t["status"] for t in tools] == ["started", "failed"] and "暂不可用" in tools[1][
        "summary"
    ]
    # 没有错误码、知识库又不可用：没有可依据的官方 Q&A，不编步骤，整理摘要转人工
    assert not [e for e in events if e["type"] == "step_card"]
    assert events[-1]["type"] == "done" and any(e["type"] == "escalation_summary" for e in events)
    assert state.values["knowledge_status"] == "unavailable"


async def test_no_match_has_text_marker(mem_runtime):
    _, _, events, _, state = await _run("eufy X10 Pro Omni 不吸了，地上的灰尘和碎屑都吸不干净", FakeAdapter("no_match"))
    finished = [e for e in events if e["type"] == "tool_call" and e["status"] == "finished"]
    assert finished and finished[0]["summary"] == "未找到匹配的官方说明"
    assert state.values["knowledge_status"] == "no_match"


async def test_adapter_disabled_is_failed_tool_call(mem_runtime):
    """HAIKE_KNOWLEDGE=off（单测默认）：无适配器 → tool_call failed，流程继续。"""
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            events = sse.parse(
                (
                    await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "X10 Pro Omni 不吸了，地上的灰尘和碎屑都吸不干净"}))
                ).text
            )
    finally:
        set_rules_service(None)
    assert [e["status"] for e in events if e["type"] == "tool_call"] == ["started", "failed"]
    assert any(e["type"] == "escalation_summary" for e in events)  # 无知识依据 → 转人工，不给自编步骤


async def test_unknown_product_does_not_retrieve(mem_runtime):
    ad = FakeAdapter("ok")
    _, _, events, _, _ = await _run("充电器不亮灯", ad)
    assert ad.calls == [] and "tool_call" not in [e["type"] for e in events]
