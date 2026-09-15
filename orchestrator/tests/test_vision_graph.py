"""票 30：读图节点接入会话图——上传故障图后 tool_call(diagnose.vision)、observations 进状态、R4 升级、失败不中断。"""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.images import InMemoryImageStore
from app.images.runtime import set_image_store
from app.main import app
from app.models.runtime import set_model_router
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form
from tests.test_images import png_bytes
from tests.test_vision import CONFIG, NO_VISION_CONFIG, _router

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"
INTAKE_OK = {
    "emotion_level": "calm",
    "product_hints": ["X9 Pro"],
    "symptoms": ["吸力变小"],
    "wants_human": False,
}


@pytest.fixture
def img_store():
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    set_rules_service(RulesService(RULES, hot_reload=False))
    yield store
    set_image_store(None)
    app.state.image_store = None
    set_rules_service(None)
    set_model_router(None)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _send_with_images(client, sid: str, text: str, n_images: int = 1):
    files = [
        ("images", (f"p{i}.png", io.BytesIO(png_bytes(512 + i)), "image/png"))
        for i in range(n_images)
    ]
    resp = await client.post(
        f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text, "purpose": "fault"}), files=files
    )
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


def _tool(events, name: str):
    return [e for e in events if e["type"] == "tool_call" and e["name"] == name]


async def _state(sid: str):
    return (await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})).values


async def test_brush_hair_photo_yields_observation_and_continues(mem_runtime, img_store, tmp_path):
    """滚刷缠毛照片 → tool_call(diagnose.vision) finished 含「毛发缠绕」→ image_observations 进状态 → 继续检索。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,
            {"observations": ["滚刷缠绕大量毛发", "尘盒已满"], "visible_parts": ["滚刷", "尘盒"]},
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        # 图片只有两张脚本输出：intake + vision；后续 synthesize / reply 调用会拿到 ScriptExhausted → 降级路径
        events = await _send_with_images(client, sid, "eufy X9 Pro 滚刷这样正常吗")
    calls = _tool(events, "diagnose.vision")
    assert [c["status"] for c in calls] == ["started", "finished"]
    assert "毛发" in calls[1]["summary"] and calls[0]["summary"] == "识别 1 张故障照片"
    substages = [e.get("substage") for e in events if e["type"] == "progress"]
    assert "vision" in substages and "retrieve" in substages  # 读图先于检索
    st = await _state(sid)
    assert st["vision_status"] == "ok" and st["image_observations"] == [
        "滚刷缠绕大量毛发",
        "尘盒已满",
    ]
    assert st["visible_parts"] == ["滚刷", "尘盒"] and st.get("escalate_reason") is None
    assert any(o.startswith("图片：滚刷缠绕") for o in st["observations"])
    assert any(t["task"] == "diagnose.vision" for t in st["model_trace"])
    # 视觉调用带图片、internal、任务名
    vcall = next(c for c in fake.calls if c["metadata"]["task"] == "diagnose.vision")
    assert "internal" in vcall["tags"]
    assert any(p.get("type") == "image_url" for m in vcall["messages"] if isinstance(m.content, list) for p in m.content)
    assert events[-1]["reason"] == "awaiting_input"  # 票 34：读图 → 检索 → 步骤卡


async def test_smoke_in_photo_triggers_r4_escalation(mem_runtime, img_store, tmp_path):
    """含冒烟的图片观察 → CP-in R4 → 不再检索 / 调模型，直接升级摘要。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,
            {
                "observations": ["smoke coming out of the vent", "外壳发黑"],
                "visible_parts": ["机身"],
            },
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_with_images(client, sid, "扫地机 X9 有点味道", 1)
        snap = (await client.get(f"/sessions/{sid}")).json()
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages[-1] == "escalate" and "retrieve" not in [
        e.get("substage") for e in events if e["type"] == "progress"
    ]
    summary = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R4" and "smoke" in summary["reason"]["text"]
    assert any("smoke" in o for o in summary["observations"])
    st = await _state(sid)
    flag = next(f for f in st["safety_flags"] if f["rule_id"] == "R4")
    assert flag["source"] == "observation" and flag["term"] in ("smoke", "smoking")
    assert st["escalate_reason"] == "R4"
    # 只发生 intake + vision 两次模型调用，没有 synthesize / reply
    assert [c["metadata"]["task"] for c in fake.calls] == ["intake", "diagnose.vision"]
    assert snap["stage"] == "escalate" and snap["last_error"] is None


async def test_vision_chain_failure_does_not_break_run(mem_runtime, img_store, tmp_path):
    router, _ = _router(tmp_path, CONFIG, [INTAKE_OK, *([RuntimeError("vision down")] * 8)])
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_with_images(client, sid, "eufy X9 Pro 吸力变小", 2)
    calls = _tool(events, "diagnose.vision")
    assert [c["status"] for c in calls] == ["started", "failed"]
    assert calls[0]["summary"] == "识别 2 张故障照片" and "失败" in calls[1]["summary"]
    assert events[-1]["reason"] == "awaiting_input"  # 票 34：读图 → 检索 → 步骤卡  # 流程不中断
    st = await _state(sid)
    assert st["vision_status"] == "failed" and st["image_observations"] == []
    assert st.get("escalate_reason") is None and "retrieve" in [
        e.get("substage") for e in events if e["type"] == "progress"
    ]
    assert any(
        t["task"] == "diagnose.vision" and t["model_used"] == "skipped" for t in st["model_trace"]
    )


async def test_no_vision_model_available_hints_user_to_describe(mem_runtime, img_store, tmp_path):
    """视觉 provider 不可用（缺 key）：tool_call failed + 固定提示「请用文字描述」，observations 为空。"""
    router, fake = _router(tmp_path, NO_VISION_CONFIG, [INTAKE_OK], env={"K1": "x"})
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_with_images(client, sid, "eufy X9 Pro 看图")
        snap = (await client.get(f"/sessions/{sid}")).json()
    calls = _tool(events, "diagnose.vision")
    assert calls[-1]["status"] == "failed" and "无可用的图片识别模型" in calls[-1]["summary"]
    hint = "".join(e["delta"] for e in events if e["type"] == "message")
    assert "请用文字描述" in hint
    assert (await _state(sid))["vision_status"] == "no_vision"
    assert [c["metadata"]["task"] for c in fake.calls][:1] == ["intake"]  # 没有视觉调用
    assert any(
        i["kind"] == "assistant_message" and "请用文字描述" in i["text"] for i in snap["timeline"]
    )


async def test_message_without_images_skips_vision_node(mem_runtime, img_store):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "扫地机 X9 吸力变小"}))
    events = sse.parse(resp.text)
    assert _tool(events, "diagnose.vision") == []
    assert "vision" not in [e.get("substage") for e in events if e["type"] == "progress"]
