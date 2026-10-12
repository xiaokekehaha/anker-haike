"""Phase 2：管理员观测台接口。

查询层是 SQL，必须对真实 Postgres 验证（跑不到库就 skip）。每个用例写自己的前缀数据并在结束时删掉，
不依赖库里已有内容，也不影响其它数据。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from psycopg_pool import AsyncConnectionPool

from app.admin.graph_export import NODE_STAGE, topology
from app.analytics.queries import _rates
from app.main import app
from app.settings import settings

pytestmark = pytest.mark.anyio if False else []  # 默认 asyncio 模式，见 pyproject


# ---------------------------------------------------------------- 静态拓扑（无需数据库）


def test_topology_matches_the_compiled_graph():
    topo = topology()
    ids = {n["id"] for n in topo["nodes"]}
    assert {"__start__", "understand", "await_input", "close", "__end__"} <= ids
    assert len(topo["edges"]) > len(ids)  # 条件边多于节点
    # 每个节点都有阶段归类，前端才能着色
    assert all(n["stage"] != "other" for n in topo["nodes"]), [
        n for n in topo["nodes"] if n["stage"] == "other"
    ]
    assert set(NODE_STAGE) >= ids


def test_topology_marks_conditional_edges():
    edges = topology()["edges"]
    conditional = {(e["source"], e["target"]) for e in edges if e["conditional"]}
    fixed = {(e["source"], e["target"]) for e in edges if not e["conditional"]}
    assert ("__start__", "understand") in fixed
    assert ("understand", "disambiguate") in conditional
    assert ("prepare_card", "await_input") in fixed  # 固定边


def test_topology_is_cached():
    assert topology() is topology()


# ---------------------------------------------------------------- 解决率口径（纯函数）


def test_self_service_rate_excludes_policy_escalations():
    """用户主动要人工 / 安全升级不算系统没解决，不进分母。"""
    rates = _rates(
        {"resolved": 8, "escalated": 6, "escalated_system": 2, "escalated_policy": 4, "abandoned": 0}
    )
    assert rates["self_service"] == 0.8  # 8 / (8 + 2)
    assert rates["closure"] == round(8 / 14, 4)  # 8 / (8 + 6)


def test_rates_are_none_when_nothing_finished():
    """没有已终结会话时返回 None——「没有数据」不能显示成 0%。"""
    rates = _rates({"resolved": 0, "escalated": 0, "escalated_system": 0, "abandoned": 0})
    assert rates == {"self_service": None, "closure": None, "escalation": None}


# ---------------------------------------------------------------- 真实数据库


@pytest.fixture
async def db():
    import psycopg

    try:
        psycopg.connect(settings.database_url, connect_timeout=1).close()
    except Exception:  # noqa: BLE001
        pytest.skip("postgres not reachable")
    from psycopg.rows import dict_row

    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=2,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=5)
    yield pool
    await pool.close()


@pytest.fixture
async def seeded(db):
    """三个会话：已解决 / 系统原因升级 / 等用户（久未动 → abandoned）。前缀隔离，用完即删。"""
    tag = f"t{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    sessions = [
        (f"{tag}-resolved", "resolved", "solved", "robot_vacuum", "EUFY-X9-PRO", now, 2),
        (f"{tag}-escalated", "escalated", "R2", "robot_vacuum", "EUFY-X9-PRO", now, 3),
        # 8 小时没动静：查询期按 abandon_after_h=6 判为 abandoned
        (
            f"{tag}-stale",
            "awaiting_user",
            "step_feedback",
            "robot_vacuum",
            "T2080",
            now - timedelta(hours=8),
            1,
        ),
    ]
    async with db.connection() as conn:
        for sid, outcome, reason, category, sku, at, runs in sessions:
            await conn.execute(
                """insert into analytics.session_facts
                   (session_id, created_at, last_run_at, runs, first_question, sku, category,
                    product_state, emotion_level, fault_plan_ids, steps_executed, knowledge_status,
                    outcome, outcome_reason, outcome_at, model_calls, tokens_in, tokens_out,
                    total_latency_ms, raw_available_until)
                   values (%s,%s,%s,%s,%s,%s,%s,'confirmed_sku','calm',
                           %s,2,'ok',%s,%s,%s,4,1000,200,7000,%s)""",
                (sid, at, at, runs, f"{tag} 扫地机不吸了", sku, category,
                 ["qa_test_seeded_plan"], outcome, reason, at, at + timedelta(hours=24)),
            )
            run_id = f"{sid}-run1"
            await conn.execute(
                """insert into analytics.run_facts
                   (run_id, session_id, seq_no, started_at, ended_at, duration_ms, entry,
                    stage_to, done_reason, first_visible_ms, card_ready_ms, card_kind,
                    model_calls, tokens_in, tokens_out, node_count)
                   values (%s,%s,1,%s,%s,7000,'message','guide','awaiting_input',
                           5000,7000,'step_card',4,1000,200,3)""",
                (run_id, sid, at, at + timedelta(seconds=7)),
            )
            for idx, (node, prev) in enumerate(
                [("intake", None), ("disambiguate", "intake"), ("retrieve", "disambiguate")],
                start=1,
            ):
                await conn.execute(
                    """insert into analytics.node_runs
                       (session_id, run_id, idx, node, prev_node, started_at, duration_ms, status, summary)
                       values (%s,%s,%s,%s,%s,%s,%s,'ok',%s)""",
                    (sid, run_id, idx, node, prev, at, 100 * idx, '{"knowledge_status": "ok"}'),
                )
            await conn.execute(
                """insert into analytics.model_calls
                   (session_id, run_id, node, task, model_used, lane, status, attempts,
                    fallback_used, stream, latency_ms, tokens_in, tokens_out, created_at)
                   values (%s,%s,'intake','intake','deepseek/chat','domestic','ok',1,
                           false,false,2000,643,45,%s)""",
                (sid, run_id, at),
            )
            await conn.execute(
                """insert into analytics.retrieval_calls
                   (session_id, run_id, node, round, kb, status, allowed_count, hits,
                    top_score, latency_ms, query, created_at)
                   values (%s,%s,'retrieve',1,'kb_manual','ok',2,5,0.016,243,%s,%s)""",
                (sid, run_id, f"{tag} query", at),
            )
    yield tag, [s[0] for s in sessions]
    async with db.connection() as conn:
        for table in ("cases", "retrieval_calls", "model_calls", "node_runs", "run_facts", "session_facts"):
            await conn.execute(
                f"delete from analytics.{table} where session_id like %s", (f"{tag}-%",)
            )


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture
async def api(db):
    """接口用 app.state 上的连接池；不跑 lifespan，直接注入。"""
    app.state.session_pool = db
    yield _client
    app.state.session_pool = None


async def test_sessions_list_filters_and_flags_abandoned(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        resp = await client.get("/admin/api/sessions", params={"q": tag, "limit": 50})
    assert resp.status_code == 200
    items = {i["session_id"]: i for i in resp.json()["items"]}
    assert len(items) == 3
    assert items[f"{tag}-resolved"]["outcome"] == "resolved"
    assert items[f"{tag}-escalated"]["outcome_reason"] == "R2"
    # 8 小时没动静的等待会话在查询期判为 abandoned（库里仍是 awaiting_user）
    assert items[f"{tag}-stale"]["outcome"] == "abandoned"
    assert items[f"{tag}-resolved"]["raw_available"] is True


async def test_sessions_list_filters_by_outcome_and_plan(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        by_outcome = await client.get(
            "/admin/api/sessions", params={"q": tag, "outcome": "escalated"}
        )
        by_plan = await client.get(
            "/admin/api/sessions", params={"q": tag, "plan": "qa_test_seeded_plan"}
        )
        missing = await client.get("/admin/api/sessions", params={"q": tag, "sku": "NOPE"})
    assert [i["session_id"] for i in by_outcome.json()["items"]] == [f"{tag}-escalated"]
    assert len(by_plan.json()["items"]) == 3
    assert missing.json()["items"] == []


async def test_sessions_list_pages_with_a_cursor(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        first = await client.get("/admin/api/sessions", params={"q": tag, "limit": 2})
        body = first.json()
        assert len(body["items"]) == 2 and body["next_cursor"]
        second = await client.get(
            "/admin/api/sessions", params={"q": tag, "limit": 2, "cursor": body["next_cursor"]}
        )
    rest = second.json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    assert {i["session_id"] for i in body["items"]} & {i["session_id"] for i in rest["items"]} == set()


async def test_journey_groups_nodes_models_and_retrievals_under_each_run(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        resp = await client.get(f"/admin/api/sessions/{tag}-resolved/journey")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["outcome"] == "resolved"
    (run,) = body["runs"]
    assert [n["node"] for n in run["nodes"]] == ["intake", "disambiguate", "retrieve"]
    assert [n["prev_node"] for n in run["nodes"]] == [None, "intake", "disambiguate"]
    assert len(run["model_calls"]) == 1 and run["model_calls"][0]["node"] == "intake"
    assert len(run["retrieval_calls"]) == 1 and run["retrieval_calls"][0]["kb"] == "kb_manual"
    assert body["case"] is None
    # 这些是伪造的 session_id，原始会话不存在 → 没有快照，前端据此降级
    assert body["snapshot"] is None


async def test_journey_404_for_unknown_session(api):
    async with _client() as client:
        resp = await client.get("/admin/api/sessions/does-not-exist/journey")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "session_not_found"


async def test_overview_counts_outcomes_and_computes_rates(api, seeded):
    frm = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    async with _client() as client:
        resp = await client.get("/admin/api/metrics/overview", params={"from": frm})
    body = resp.json()
    totals, rates = body["totals"], body["rates"]
    assert totals["sessions"] >= 3
    assert totals["escalated_system"] >= 1  # R2
    assert 0 <= rates["self_service"] <= 1
    assert body["latency"]["first_visible_p50"] is not None
    assert any(r["value"] == "robot_vacuum" for r in body["breakdown"])
    assert any(m["task"] == "intake" for m in body["models"])


async def test_overview_breakdown_dimensions(api, seeded):
    frm = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    async with _client() as client:
        by_plan = await client.get(
            "/admin/api/metrics/overview", params={"from": frm, "dim": "plan"}
        )
        by_reason = await client.get(
            "/admin/api/metrics/overview", params={"from": frm, "dim": "reason"}
        )
    # 共享开发库里当天有大量真实回放会话（每会话多个 qa_ 计划），breakdown 只取前 30：按 qa_ 维度存在即可
    assert by_plan.status_code == 200 and all(r["value"] for r in by_plan.json()["breakdown"])
    assert any(r["value"] == "R2" for r in by_reason.json()["breakdown"])


async def test_flow_returns_edges_nodes_and_entries(api, seeded):
    frm = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    async with _client() as client:
        resp = await client.get("/admin/api/metrics/flow", params={"from": frm})
    body = resp.json()
    edges = {(e["source"], e["target"]): e["n"] for e in body["edges"]}
    assert edges[("intake", "disambiguate")] >= 3
    assert any(n["node"] == "intake" and n["p50_ms"] is not None for n in body["nodes"])
    steps = {n["node"]: n["avg_step"] for n in body["nodes"]}
    assert steps["intake"] < steps["disambiguate"]  # 平均步序：前端按实际先后排列
    assert any(e["node"] == "intake" for e in body["entries"])  # 入口节点


async def test_graph_endpoint_serves_the_topology(api):
    async with _client() as client:
        resp = await client.get("/admin/api/graph")
    body = resp.json()
    assert resp.headers["cache-control"].startswith("public")
    assert {n["id"] for n in body["nodes"]} >= {"understand", "guide", "close"}
    assert body["stage_order"][0] == "start"


# ---------------------------------------------------------------- 案例标注


async def test_label_case_then_patch_status(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        created = await client.post(
            "/admin/api/cases",
            json={
                "session_id": f"{tag}-escalated",
                "verdict": "bad",
                "reason_tags": ["knowledge_missing"],
                "note": "手册里没有这个故障",
                "labeled_by": "tester",
            },
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]

        # 重复标注同一会话 → 更新而不是新建
        again = await client.post(
            "/admin/api/cases",
            json={"session_id": f"{tag}-escalated", "verdict": "review", "reason_tags": []},
        )
        assert again.json()["case_id"] == case_id and again.json()["verdict"] == "review"

        patched = await client.patch(
            f"/admin/api/cases/{case_id}", json={"status": "fixed", "fixed_in": "rel-20260913"}
        )
        assert patched.json()["status"] == "fixed"

        listed = await client.get("/admin/api/cases", params={"status": "fixed"})
    body = listed.json()
    mine = [c for c in body["items"] if c["case_id"] == case_id]
    assert len(mine) == 1 and mine[0]["first_question"].startswith(tag)
    assert "knowledge_missing" in body["reason_tags"]


async def test_case_rejects_unknown_tags_and_missing_sessions(api, seeded):
    tag, _ = seeded
    async with _client() as client:
        bad_tag = await client.post(
            "/admin/api/cases",
            json={"session_id": f"{tag}-resolved", "verdict": "bad", "reason_tags": ["made_up"]},
        )
        missing = await client.post(
            "/admin/api/cases", json={"session_id": "nope", "verdict": "good"}
        )
        empty_patch = await client.patch("/admin/api/cases/whatever", json={})
    assert bad_tag.status_code == 422 and bad_tag.json()["detail"]["code"] == "unknown_reason_tags"
    assert missing.status_code == 404
    assert empty_patch.status_code == 422


async def test_patch_unknown_case_is_404(api, seeded):
    async with _client() as client:
        resp = await client.patch("/admin/api/cases/no-such-case", json={"status": "fixed"})
    assert resp.status_code == 404


async def test_endpoints_return_503_without_a_database():
    app.state.session_pool = None
    async with _client() as client:
        resp = await client.get("/admin/api/sessions")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "analytics_unavailable"
