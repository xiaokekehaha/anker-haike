"""真实图 + 假模型 + 本机 Langfuse 的可重复联调；不调用模型厂商、不写业务数据库。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

import httpx
from app.knowledge.adapter import Hit, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.models import ModelRegistry, ModelRouter, load_models_config
from app.models.fake import FakeChatModel
from app.models.runtime import set_model_router
from app.observability.metrics import summarize
from app.observability.runtime import LangfuseExporter, configure_logging, set_exporter
from app.sessions.graph import build_graph
from app.sessions.runner import run_message
from app.sessions.store import InMemorySessionStore
from dotenv import dotenv_values
from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parents[2]


class SmokeKnowledge:
    async def hybrid_search(self, kb, query, top_k, allow):
        if kb != "kb_qa":
            return ToolResult("no_match", kb=kb, query=query)
        return ToolResult(
            "ok",
            [
                Hit(
                    evidence_id="rv-0272#s1",
                    knowledge_id="smoke",
                    chunk_id="rv-0272#s1",
                    doc_id="rv-0272",
                    doc_version="smoke",
                    source=kb,
                    snippet="翻转主机，按下滚刷盖两侧卡扣取出滚刷，清理缠绕毛发后装回。",
                    score=0.9,
                )
            ],
            kb=kb,
            query=query,
        )


async def main(*, offline: bool = False):
    auth = None
    if not offline:
        credentials = dotenv_values(ROOT / "deploy/observability/.env")
        auth = (credentials["LANGFUSE_PUBLIC_KEY"], credentials["LANGFUSE_SECRET_KEY"])
    base_url = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
    log_path = ROOT / "logs/observability-smoke.jsonl"
    logging.basicConfig(level=logging.INFO)
    handler = configure_logging(str(log_path))
    fake = FakeChatModel(
        script=[
            json.dumps(
                {
                    "primary_intent": "report_problem",
                    "device_relation": "current",
                    "device_category": "robot_vacuum",
                    "product_hints": ["X10 Pro Omni"],
                    "emotion_level": "calm",
                    "emotion_cues": [],
                    "facts": [
                        {"kind": "symptom", "value": "不吸了", "quote": "不吸了"},
                        {"kind": "symptom", "value": "滚刷缠头发", "quote": "滚刷缠头发"},
                    ],
                }
            ),
            json.dumps(
                {
                    "hypotheses": [
                        {
                            "plan_id": "qa_rv_0272",
                            "confidence": 0.9,
                            "evidence_ids": ["rv-0272#s1"],
                            "rationale": "滚刷缠绕",
                        }
                    ]
                }
            ),
            ["已找到滚刷缠绕的处理资料。", "请按提示操作。"],
        ]
    )
    config = load_models_config(ROOT / "config/models.yaml", lane_override="domestic")
    router = ModelRouter(
        ModelRegistry(config, env={"DEEPSEEK_API_KEY": "fake-only"}), model_factory=lambda *_: fake
    )
    set_model_router(router)
    set_knowledge_adapter(SmokeKnowledge())
    exporter = LangfuseExporter(base_url, *auth) if auth else None
    if exporter:
        exporter.start()
    set_exporter(exporter)
    store = InMemorySessionStore()
    sid = (await store.create_session()).session_id
    try:
        events = [
            event
            async for event in run_message(
                store,
                build_graph(InMemorySaver()),
                sid,
                "eufy X10 Pro Omni 不吸了，滚刷缠头发。手机号 13800138000，订单号：CHECK-ORDER-123",
            )
        ]
    finally:
        set_exporter(None)
        if exporter:
            await exporter.close()
        set_model_router(None)
        set_knowledge_adapter(None)
        logging.getLogger().removeHandler(handler)
        handler.close()
    assert events[-1]["type"] == "done" and events[-1]["reason"] == "awaiting_input"
    assert any(event["type"] == "step_card" for event in events)
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    calls = [
        row for row in rows if row.get("event") == "model_call" and row.get("session_id") == sid
    ]
    # 调用数不写死：步骤正文自 2026-10-08 起直接取官方 Q&A 原文，guide.step 不再调模型；
    # 冒烟要验的是「链路通 + 每次调用都成功 + 同属一个 run」，不是调用次数。
    assert calls and all(row["status"] == "ok" for row in calls), calls
    assert {row["task"] for row in calls} >= {"intake", "diagnose.synthesize"}, calls
    assert len({row["run_id"] for row in calls}) == 1
    traces = []
    if not offline:
        async with httpx.AsyncClient(base_url=base_url, auth=auth, timeout=10) as client:
            traces = []
            for _ in range(30):
                response = await client.get(
                    "/api/public/v2/observations",
                    params={
                        "filter": json.dumps(
                            [
                                {
                                    "type": "string",
                                    "column": "sessionId",
                                    "operator": "=",
                                    "value": sid,
                                }
                            ]
                        ),
                        "fields": "core,basic,io,metadata,model,usage,metrics",
                    },
                )
                response.raise_for_status()
                traces = response.json()["data"]
                if len(traces) == len(calls):
                    break
                await asyncio.sleep(1)
            assert len(traces) == len(calls), (
                f"expected {len(calls)} observations, got {len(traces)}"
            )
            assert {item["name"] for item in traces} == {row["task"] for row in calls}
            for detail in traces:
                assert detail["sessionId"] == sid and detail["type"] == "GENERATION"
                assert (
                    detail["model"] == "deepseek/deepseek-chat"
                    and detail["metadata"]["run_id"] == calls[0]["run_id"]
                )
                assert detail["input"] and detail["output"]
                if detail["name"] != "reply.stream":
                    assert detail["usageDetails"]["input"] == 10
                    assert detail["usageDetails"]["output"] == 5
                assert "13800138000" not in json.dumps(
                    detail
                ) and "CHECK-ORDER-123" not in json.dumps(detail)
    current = [json.dumps(row) for row in rows if row.get("session_id") == sid]
    assert "13800138000" not in "".join(current) and "CHECK-ORDER-123" not in "".join(current)
    session_log = ROOT / "logs/observability-smoke-session.jsonl"
    session_log.write_text("\n".join(current) + "\n")
    result = {
        "session_id": sid,
        "mode": "offline" if offline else "langfuse",
        "traces": len(traces),
        "tasks": sorted(row["task"] for row in calls),
        "pii_redacted": True,
        "metrics": summarize([session_log]),
    }
    # 只断言本条链路真正会产生的指标。这一单以步骤卡作答（正文取官方 Q&A 原文，不走流式回复），
    # 因此只有 card_ready_ms；first_visible_ms 属于流式回复路径，这里本就不该有。
    assert result["metrics"]["metrics"]["card_ready_ms"]["count"] == 1, result["metrics"]
    output = ROOT / (
        "logs/observability-offline-result.json"
        if offline
        else "logs/observability-smoke-result.json"
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="只验证本地 JSONL，不连接 Langfuse")
    asyncio.run(main(offline=parser.parse_args().offline))
