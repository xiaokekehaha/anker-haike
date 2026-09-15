"""票 30：diagnose.vision 模块级测试（假 router 回放）：观察输出、图片截断、无视觉能力降级、链失败不中断、CP-in 观察项 R4。"""

from __future__ import annotations

import base64
import json

from app.diagnose.vision import (
    NO_VISION_TEXT,
    VisionObservation,
    build_messages,
    image_limit,
    observe_images,
    select_images,
)
from app.images import InMemoryImageStore
from app.models.config import load_models_config
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.scripted_model import ScriptedSemanticModel as FakeChatModel
from tests.test_images import png_bytes

CONFIG = """
version: t
default_lane: domestic
providers:
  p1: {sdk: openai, api_key_env: K1}
  p2: {sdk: openai, api_key_env: K2}
models:
  vl_small: {provider: p1, id: vl1, structured: json_object, vision: true, max_images: 2}
  vl_big:   {provider: p2, id: vl2, structured: json_object, vision: true, max_images: 10}
  text_only: {provider: p1, id: t1, structured: json_object, vision: false}
  emb: {provider: p1, id: e, kind: embedding}
  rr:  {provider: p1, id: r, kind: rerank}
lanes:
  domestic:
    intake:              {chain: [text_only]}
    diagnose.vision:     {chain: [vl_small, vl_big], needs_vision: true}
    diagnose.synthesize: {chain: [text_only]}
    guide.step:          {chain: [text_only]}
    reply.stream:        {chain: [text_only], stream: true}
    escalate.summary:    {chain: [text_only]}
    warranty.receipt_ocr: {chain: [vl_big], needs_vision: true}
    disambiguate.clarify: {chain: [text_only]}
"""
# 视觉链只剩 p2 的 vl_big；测试里不给 K2 → 视觉模型全部不可用，只剩文本模型可服务（07 §6「备用模型不支持图片」）
NO_VISION_CONFIG = CONFIG.replace(
    "diagnose.vision:     {chain: [vl_small, vl_big], needs_vision: true}",
    "diagnose.vision:     {chain: [vl_big], needs_vision: true}",
)
RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


def _router(
    tmp_path, config: str, outputs: list, env: dict | None = None
) -> tuple[ModelRouter, FakeChatModel]:
    p = tmp_path / "models.yaml"
    p.write_text(config, encoding="utf-8")
    cfg = load_models_config(p)
    fake = FakeChatModel(
        script=[
            o if isinstance(o, Exception) else json.dumps(o, ensure_ascii=False) for o in outputs
        ]
    )
    reg = ModelRegistry(cfg, env=env if env is not None else {"K1": "x", "K2": "x"})
    return ModelRouter(reg, model_factory=lambda r, route: fake), fake


async def _store_with(n: int, session_id: str = "s") -> tuple[InMemoryImageStore, list[dict]]:
    store = InMemoryImageStore()
    refs = []
    for i in range(n):
        ref = await store.put(session_id, "fault", png_bytes(64 + i), "image/png")
        refs.append({**ref.public(), "run_id": "r1"})
    return store, refs


async def test_brush_hair_wrap_observation_from_vision_task(tmp_path):
    """滚刷缠毛照片 → observations 含「毛发缠绕」类观察；调用 internal、图片以 data URL 进入消息。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            {
                "observations": ["滚刷缠绕大量毛发", "滚刷两端有线头"],
                "visible_parts": ["滚刷", "底盘"],
            }
        ],
    )
    store, refs = await _store_with(1)
    out = await observe_images(
        router, store, session_id="s", refs=refs, text="滚刷这样正常吗", lane="domestic"
    )
    assert out.status == "ok" and any("毛发" in o for o in out.observations)
    assert out.visible_parts == ["滚刷", "底盘"] and out.used_image_ids == [refs[0]["image_id"]]
    assert out.model_trace["task"] == "diagnose.vision" and out.model_used
    call = fake.calls[0]
    assert call["metadata"]["task"] == "diagnose.vision" and "internal" in call["tags"]
    human = call["messages"][-1].content
    assert isinstance(human, list) and human[0]["type"] == "text"
    assert '<data kind="user_message">' in human[0]["text"] and "滚刷这样正常吗" in human[0]["text"]
    url = human[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1])[:8] == b"\x89PNG\r\n\x1a\n"


async def test_smoke_observation_hits_r4_via_cp_in(tmp_path):
    """含冒烟的图片观察 → 规则 CP-in observation_terms 命中 R4（升级由图节点执行）。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            {
                "observations": ["visible smoke near the battery", "机身底部发黑"],
                "visible_parts": ["电池仓"],
            }
        ],
    )
    store, refs = await _store_with(1)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    cp = RulesService(RULES, hot_reload=False).check_in(observations=out.observations)
    assert cp.escalate and cp.rule_ids == ["R4"]
    hit = next(h for h in cp.hits if h.rule_id == "R4")
    assert hit.source == "observation" and hit.term in ("smoke", "smoking")


async def test_too_many_images_keep_latest_within_chain_limit(tmp_path):
    """图片数超过链上视觉模型单请求上限（vl_small max_images=2）→ 只保留最新 2 张。"""
    router, fake = _router(tmp_path, CONFIG, [{"observations": ["ok"], "visible_parts": []}])
    assert image_limit(router.registry.chain("diagnose.vision", "domestic")) == 2
    store, refs = await _store_with(5)
    out = await observe_images(router, store, session_id="s", refs=refs, text="x", lane="domestic")
    assert out.status == "ok"
    assert out.used_image_ids == [r["image_id"] for r in refs[-2:]]
    assert out.dropped_image_ids == [r["image_id"] for r in refs[:3]]
    human = fake.calls[0]["messages"][-1].content
    assert sum(1 for p in human if p.get("type") == "image_url") == 2
    keep, dropped = select_images(refs, 10)
    assert keep == refs and dropped == []


async def test_no_vision_capable_model_degrades_with_user_hint(tmp_path):
    """备用模型不支持图片：不调用、observations 为空、给用户「请文字描述」提示（07 §6）。"""
    router, fake = _router(tmp_path, NO_VISION_CONFIG, [], env={"K1": "x"})  # 视觉 provider 缺 key
    store, refs = await _store_with(1)
    out = await observe_images(
        router, store, session_id="s", refs=refs, text="看图", lane="domestic"
    )
    assert out.status == "no_vision" and out.observations == [] and out.user_hint == NO_VISION_TEXT
    assert fake.calls == [] and out.model_trace["model_used"] == "skipped"


async def test_whole_chain_failing_does_not_raise(tmp_path):
    router, fake = _router(tmp_path, CONFIG, [RuntimeError("boom")] * 8)
    store, refs = await _store_with(1)
    out = await observe_images(
        router, store, session_id="s", refs=refs, text="看图", lane="domestic"
    )
    assert out.status == "failed" and out.observations == [] and out.user_hint is None
    assert out.reason and out.model_trace["attempts"] >= 1
    assert fake.calls  # 确实尝试过


async def test_router_or_store_missing_and_receipt_images_ignored(tmp_path):
    store, refs = await _store_with(1)
    out = await observe_images(None, store, session_id="s", refs=refs, text="", lane="domestic")
    assert out.status == "skipped" and out.observations == []
    router, _ = _router(tmp_path, CONFIG, [])
    receipt = [{**refs[0], "purpose": "receipt"}]
    out2 = await observe_images(
        router, store, session_id="s", refs=receipt, text="", lane="domestic"
    )
    assert out2.status == "no_images"
    # 图片已被清理：不中断
    out3 = await observe_images(
        router, InMemoryImageStore(), session_id="s", refs=refs, text="", lane="domestic"
    )
    assert out3.status == "failed" and "not found" in (out3.reason or "")


def test_build_messages_shape_and_schema():
    msgs = build_messages(
        [({"mime": "image/jpeg"}, b"\xff\xd8\xff")], "t", strategy="normal", summary=None
    )
    assert msgs[1].content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert (
        VisionObservation.model_validate({"observations": [], "visible_parts": []}).observations
        == []
    )
