"""New-protocol HTTP harness; only model/provider and knowledge I/O are replaced."""

from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import pytest

from app.knowledge.adapter import Hit, ToolResult
from app.knowledge.runtime import set_knowledge_adapter
from app.main import app
from app.models.config import KNOWN_TASKS, ModelsConfig
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.rules import RulesService, set_rules_service
from app.settings import REPO_ROOT


class Knowledge:
    def __init__(self):
        self.calls = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.calls.append((kb, query, allow))
        hits = (
            []
            if kb != "kb_manual"
            else [
                Hit(
                    "c12",
                    "manual",
                    "c12",
                    "manual_rv_v1",
                    "2026-09-12.1",
                    kb,
                    "翻转主机取出滚刷，割断缠绕的毛发",
                    0.9,
                )
            ]
        )
        return ToolResult("ok" if hits else "no_match", hits, kb=kb, query=query, allowed_count=1)


@dataclass
class Conversation:
    client: httpx.AsyncClient
    sid: str
    models: dict
    knowledge: Knowledge
    outputs: list = field(default_factory=list)

    async def snapshot(self):
        response = await self.client.get(f"/sessions/{self.sid}")
        assert response.status_code == 200, response.text
        return response.json()

    async def state(self):
        row = await app.state.session_store.get_session(self.sid)
        return (
            await app.state.session_graph.aget_state(
                {
                    "configurable": {
                        "thread_id": self.sid,
                        "checkpoint_id": row.published_checkpoint_id,
                    }
                }
            )
        ).values

    async def send(self, text, meaning, *, input_id=None):
        previous_calls = len(self.models["intake"].calls)
        self.models["intake"].script.append(meaning)
        before = await self.snapshot()
        response = await self.client.post(
            f"/sessions/{self.sid}/messages",
            data={
                "input_id": input_id or uuid4().hex,
                "expected_version": before["version"],
                "text": text,
            },
        )
        result = self.check(response)
        assert len(self.models["intake"].calls) == previous_calls + 1, result
        return result

    def check(self, response):
        import json

        assert response.status_code == 200, response.text
        output = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        assert not any(e["type"] == "error" for e in output), output
        assert output[-1]["type"] == "done", output
        self.outputs.append(output)
        return output


REPORT = {
    "primary_intent": "report_problem",
    "device_relation": "other",
    "product_hints": ["X9 Pro"],
    "facts": [
        {"value": "不吸了", "quote": "不吸了"},
        {"value": "滚刷缠头发", "quote": "滚刷缠了头发"},
    ],
}
REPORT_TEXT = "X9 Pro不吸了，滚刷缠了头发"


@pytest.fixture
async def conversation(mem_runtime):
    models = {task: FakeChatModel(name_for_trace=task) for task in KNOWN_TASKS}
    models["diagnose.synthesize"].script = [
        {
            "hypotheses": [
                {"plan_id": "rv_suction_hair_wrap", "confidence": 0.9, "evidence_ids": ["c12"]}
            ]
        }
    ]
    models["reply.stream"].script = [["请看下面的排查步骤。"]]
    models["guide.step"].script = [
        {
            "instruction": "翻转主机，按下滚刷盖两侧卡扣取出滚刷，用附带清洁刀具割断缠绕的毛发后装回。"
        }
    ]
    config = ModelsConfig.model_validate(
        {
            "version": "conversation-test",
            "default_lane": "domestic",
            "providers": {"test": {"sdk": "openai", "api_key_env": "TEST_KEY"}},
            "models": {
                task: {"provider": "test", "id": task, "structured": "native", "vision": True}
                for task in KNOWN_TASKS
            },
            "lanes": {
                "domestic": {
                    task: {"chain": [task], "stream": task == "reply.stream"}
                    for task in KNOWN_TASKS
                }
            },
            "retry": {"same_model_max": 0, "rate_limit_max": 0, "chain_max": 1},
        }
    )
    set_model_router(
        ModelRouter(
            ModelRegistry(config, env={"TEST_KEY": "test"}),
            model_factory=lambda resolved, route: models[resolved.alias],
        )
    )
    knowledge = Knowledge()
    set_knowledge_adapter(knowledge)
    set_rules_service(RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://t"
        ) as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            yield Conversation(client, sid, models, knowledge)
    finally:
        await app.state.run_manager.shutdown()
        set_model_router(None)
        set_knowledge_adapter(None)
        set_rules_service(None)
