"""票 30：读图节点接入会话图——上传故障图后 tool_call(diagnose.vision)、observations 进状态、R4 升级、失败不中断。"""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation.taxonomy import families
from app.diagnose.decision import known_symptom_codes
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
def l3_services():
    """补拍与图文冲突的路由挂在 route_after_vision 的 L3 分支上（graph.py 的 get_services() 判断），
    生产里由 sessions/runtime.py 在数据库池就绪时注册；内存态测试要自己注册一份。"""
    from app.actions.runtime import configure

    configure(memory=True)
    yield
    configure()


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


# ---- 阶段 3 的补拍闭环：像素门控 → 补拍卡 → 重新上传 → 恢复排障 ----


def _real_png(width: int = 900, height: int = 700, brightness: float = 1.0) -> bytes:
    """可被 Pillow 解码的图（tests.test_images.png_bytes 是手工拼的，解不开，会绕过像素门控）。"""
    from PIL import Image, ImageDraw, ImageEnhance

    im = Image.new("RGB", (width, height), (210, 210, 214))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([60, 180, 840, 470], radius=70, fill=(60, 60, 64))
    for x in range(90, 820, 26):
        d.line([(x, 200), (x + 12, 450)], fill=(150, 150, 155), width=3)
    if brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(brightness)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def _send_bytes(client, sid: str, text: str, blobs: list[bytes]):
    files = [("images", (f"p{i}.png", io.BytesIO(b), "image/png")) for i, b in enumerate(blobs)]
    resp = await client.post(
        f"/sessions/{sid}/messages",
        data=await message_form(client, f"/sessions/{sid}/messages", {"text": text, "purpose": "fault"}),
        files=files,
    )
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


async def test_underexposed_photo_yields_a_retake_card_without_calling_the_model(
    mem_runtime, img_store, l3_services, tmp_path
):
    """阶段 3 验收的端到端版：太暗的照片在零模型调用下变成补拍卡。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [INTAKE_OK, {"observations": ["滚刷缠绕"], "visible_parts": ["滚刷"]}],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_bytes(client, sid, "eufy X9 Pro 不吸了，拍了张照片", [_real_png(brightness=0.08)])
    calls = [c for c in fake.calls if c["metadata"]["task"] == "diagnose.vision"]
    assert calls == [], "被像素门控拦下时不应发起任何视觉模型调用"
    finished = [e for e in _tool(events, "diagnose.vision") if e["status"] == "finished"]
    assert finished and "未调用识别模型" in finished[0]["summary"]
    cards = [e for e in events if e["type"] == "retake_card"]
    assert cards, "应当发出补拍卡"
    assert cards[0]["reasons"] == ["too_dark"]
    assert "光线充足" in cards[0]["guidance"][0]
    state = await _state(sid)
    assert state["vision_status"] == "unusable"
    assert state["image_quality"]["usable"] is False


async def test_a_good_retake_resumes_diagnosis(mem_runtime, img_store, l3_services, tmp_path):
    """补拍一张正常照片后，读图应当真的跑起来并把观察写进状态。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,  # 第一轮（暗图）的 intake
            INTAKE_OK,  # 第二轮（补拍）的 intake
            {
                "observations": ["滚刷缠绕大量毛发"],
                "visible_parts": ["滚刷"],
                "findings": [{"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠满毛发"}],
            },
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send_bytes(client, sid, "eufy X9 Pro 不吸了，拍了张照片", [_real_png(brightness=0.08)])
        assert (await _state(sid))["vision_status"] == "unusable"
        events = await _send_bytes(client, sid, "重新拍了一张", [_real_png()])
    calls = [c for c in fake.calls if c["metadata"]["task"] == "diagnose.vision"]
    assert len(calls) == 1, "补拍后应当真正调用一次视觉模型"
    state = await _state(sid)
    assert state["vision_status"] == "ok"
    assert any("毛发" in o for o in state["image_observations"])
    # 签名先验由 retrieve 直接读 fault_localization 消费，不经 fault_card_hits（那个键存 chunk_id）
    from app.diagnose.localization import signature_plans

    assert signature_plans(state["fault_localization"]) == ["rv_suction_hair_wrap"]
    assert [e["type"] for e in events if e["type"] == "retake_card"] == []


async def test_unverified_model_hint_does_not_silently_lock_the_sku(
    mem_runtime, img_store, l3_services, tmp_path
):
    """A8：没能复看确认的型号只当线索进 product_hints，绝不静默锁 SKU。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [INTAKE_OK, {"observations": [], "visible_parts": [], "model_hint": "X10 Pro", "model_hint_cell": None}],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send_bytes(client, sid, "eufy X9 Pro 不吸了", [_real_png()])
    state = await _state(sid)
    assert state["fault_localization"]["model_hint_verified"] is False
    # 用户文字已经确认了 X9 Pro：未验证的铭牌既不能改写它，也不能让它变成别的 SKU
    assert state["product_confirmed"]["sku"] == "EUFY-X9-PRO"
    assert state["product_state"] == "confirmed_sku"


async def _nameplate_card(tmp_path, text: str, hint: str) -> dict:
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            {**INTAKE_OK, "product_hints": []},
            {"observations": [], "visible_parts": [], "model_hint": hint, "model_hint_cell": None},
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send_bytes(client, sid, text, [_real_png()])
    state = await _state(sid)
    assert state["fault_localization"]["model_hint_verified"] is False
    assert state["product_state"] != "confirmed_sku"
    return state


async def test_unverified_nameplate_reading_replaces_the_open_product_question(
    mem_runtime, img_store, l3_services, tmp_path
):
    """品类不明、原本要开放式追问产品时：未核实的铭牌读数变成可点选的候选，单命中也要用户点确认。"""
    state = await _nameplate_card(tmp_path, "不吸了", "X10 Pro")
    card = state["pending_card"]
    assert card["kind"] == "select_product"
    assert "X10 Pro" in card["payload"]["note"]
    assert card["payload"]["allow_unknown"] and card["payload"]["category"] == "robot_vacuum"
    assert [c["sku"] for c in card["payload"]["candidates"]] == ["EUFY-X10-PRO-OMNI"]


async def test_unverified_nameplate_reading_leads_the_model_card(mem_runtime, img_store, l3_services, tmp_path):
    """本来就要问型号（知识按型号分化）时：照片读到的型号排第一并说明来源，仍由用户确认。"""
    state = await _nameplate_card(tmp_path, "充电宝充不进电", "A1289")
    card = state["pending_card"]
    assert card["kind"] == "select_product" and card["payload"]["allow_unknown"]
    assert card["payload"]["candidates"][0]["sku"] == "ANKER-A1289"
    assert "A1289" in card["payload"]["note"]


async def test_nameplate_reading_does_not_add_a_model_question_when_models_do_not_matter(
    mem_runtime, img_store, l3_services, tmp_path
):
    """品类已知且排查不按型号分化：不为了用上铭牌读数多问一张卡（spec 2026-09-19-0810 三档判定）。"""
    state = await _nameplate_card(tmp_path, "扫地机不吸了", "X10 Pro")
    assert (state.get("pending_card") or {}).get("kind") != "select_product"


async def test_step_card_echoes_what_the_photo_showed_once(mem_runtime, img_store, l3_services, tmp_path):
    """阶段 4 隐式确认：首张步骤卡带一句「从照片里我看到…」，且不掺进步骤正文。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,
            {
                "observations": ["滚刷缠绕大量毛发"],
                "visible_parts": ["滚刷"],
                "findings": [
                    {"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠满毛发"},
                    {"part": "吸口", "phenomenon": "正常", "evidence": "无异物"},
                ],
            },
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_bytes(client, sid, "eufy X9 Pro 不吸了", [_real_png()])
    cards = [e for e in events if e["type"] == "step_card"]
    assert cards, f"应当出步骤卡：{[e['type'] for e in events]}"
    seen = cards[0].get("seen")
    assert seen and "滚刷缠绕" in seen
    assert "吸口正常" not in seen, "非故障项不该回显"
    assert "如果不对" in seen, "隐式确认要留一句让用户纠正的话"
    assert seen not in cards[0]["step"]["instruction"], "步骤是已审核原文，不能被掺入生成的句子"
    assert (await _state(sid))["vision_echoed"] is True


async def test_photo_contradicting_the_text_asks_before_diagnosing(
    mem_runtime, img_store, l3_services, tmp_path
):
    """demo 第三步：用户咬定滤网，照片显示滚刷缠绕 → 先澄清，不带着错误前提往下走。

    冲突判定在代码层做（视觉调用根本看不到用户那句话），所以这一步是确定性的，适合现场演示。
    """
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,
            {
                "observations": ["滚刷缠绕大量毛发"],
                "visible_parts": ["滚刷"],
                "findings": [{"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠满毛发"}],
            },
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_bytes(
            client, sid, "eufy X9 Pro 吸力变小，应该是滤网堵住了吧", [_real_png()]
        )
    state = await _state(sid)
    conflicts = state["fault_localization"]["conflicts_with_text"]
    assert conflicts == ["您提到的是滤网，但照片里看到问题的是滚刷（缠绕）"]
    assert state["clarification"]["reason"] == "conflict"
    said = " ".join(e.get("delta", "") for e in events if e["type"] == "message")
    assert "图片与文字描述存在差异" in said and "滚刷" in said, f"应当把差异说给用户听：{said!r}"


async def test_photo_signature_of_another_category_does_not_mask_the_text_symptom(
    mem_runtime, img_store, l3_services, tmp_path
):
    """（充电触点, 污渍）也是耳机不充电的签名。照片在品类确定前读，签名事实只能带耳机的码；
    决策层按扫地机过滤后不能落空，也不能因此跳过原文「回不了座，充不上电」的归一。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            INTAKE_OK,
            {
                "observations": ["充电触点发黑"],
                "visible_parts": ["充电触点"],
                "findings": [{"part": "充电触点", "phenomenon": "污渍", "evidence": "触点发黑"}],
            },
        ],
    )
    set_model_router(router)
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        events = await _send_bytes(client, sid, "eufy X9 Pro 回不了座，充不上电", [_real_png()])
    st = await _state(sid)
    assert st["category"] == "robot_vacuum"
    vacuum = {f["symptom_code"] for f in families("robot_vacuum")}
    codes = known_symptom_codes(st)
    assert codes and set(codes) <= vacuum
    assert set(st.get("symptom_codes") or []) <= vacuum
    assert not any(e["type"] == "escalation_summary" for e in events)
