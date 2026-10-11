"""票 30：diagnose.vision 模块级测试（假 router 回放）：观察输出、图片截断、无视觉能力降级、链失败不中断、CP-in 观察项 R4。"""

from __future__ import annotations

import base64
import io
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
    # 阶段 2：用户文字不进这次调用；图在前、指令在后、逐图带标签
    assert isinstance(human, list)
    assert human[0]["type"] == "text" and human[0]["text"].startswith("Image 1")
    assert human[1]["type"] == "image_url" and human[-1]["type"] == "text"
    blob = " ".join(part.get("text", "") for part in human)
    assert "滚刷这样正常吗" not in blob and "<data" not in blob
    assert "症状" not in call["messages"][0].content, "系统提示也不该带会话状态"
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
        [
            ({"mime": "image/jpeg"}, b"\xff\xd8\xff", "image/jpeg"),
            ({"mime": "image/png"}, b"\x89PNG", "image/png"),
        ]
    )
    content = msgs[1].content
    assert [c["type"] for c in content] == ["text", "image_url", "text", "image_url", "text"]
    assert content[0]["text"].startswith("Image 1") and content[2]["text"].startswith("Image 2")
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[3]["image_url"]["url"].startswith("data:image/png;base64,")
    assert (
        VisionObservation.model_validate({"observations": [], "visible_parts": []}).observations
        == []
    )


def test_vision_output_schema_does_not_ask_the_model_for_derived_fields():
    """conflicts_with_text 由代码层比对得出，model_hint_readable 由字面派生 —— 都不该向模型索取。"""
    fields = list(VisionObservation.model_fields)  # 定义顺序即生成顺序
    assert "conflicts_with_text" not in fields and "model_hint_readable" not in fields
    assert fields[0] == "observations", "observations 必须排在最前（describe-first）"
    assert fields.index("observations") < fields.index("findings")


# ---- 阶段 1：铭牌裁剪复看与交叉核对 ----
# 背景：2026-09-15 实测 deepseek 在 14px 铭牌上给出 `T2351` —— 格式合理、不带 ? 占位的假型号。
# 假型号会直接进 disambiguate 造成错误单命中，且下游无从察觉，所以复看必须「看到铭牌就做」，
# 而不是「读不清才做」。


def _loc(fake_calls_output, **kw):
    return {"observations": [], "visible_parts": [], **kw}


async def _store_with_decodable(n: int, session_id: str = "s") -> tuple[InMemoryImageStore, list[dict]]:
    """tests.test_images.png_bytes 造的是手工 PNG，Pillow 解不开（裁剪会被跳过），
    这里用真正可解码的图，才能走到裁剪复看那条路。"""
    import io

    from PIL import Image

    store = InMemoryImageStore()
    refs = []
    for i in range(n):
        buf = io.BytesIO()
        # 尺寸要过像素门控的 short_edge 阈值，否则会在调用模型前就被拦下
        Image.new("RGB", (800 + i * 10, 600), (200 - i * 20, 200, 200)).save(buf, "PNG")
        ref = await store.put(session_id, "fault", buf.getvalue(), "image/png")
        refs.append({**ref.public(), "run_id": "r1"})
    return store, refs


async def test_nameplate_reread_overrides_a_fabricated_hint(tmp_path):
    """全图读出假型号 → 裁剪放大后读到真型号 → 以像素更多的那次为准。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            _loc(None, model_hint="T2351", model_hint_cell="右下"),
            {"model_hint": "X10 Pro"},
        ],
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    assert out.fault_localization["model_hint"] == "X10 Pro"
    assert out.fault_localization["model_hint_readable"] == "full"
    assert len(fake.calls) == 2, "看到铭牌就应该复看一次"


async def test_nameplate_reread_erases_hint_when_the_zoom_cannot_read_it(tmp_path):
    """单图时，裁剪放大都读不出 → 全图那次的自信答案不可信，清空回到「不知道」。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            _loc(None, model_hint="T2351", model_hint_cell="右下"),
            {"model_hint": ""},
        ],
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    assert out.fault_localization["model_hint"] is None
    assert out.fault_localization["model_hint_readable"] == "unreadable"


async def test_nameplate_reread_keeps_hint_when_several_images_make_it_inconclusive(tmp_path):
    """多图时裁的是最新一张，铭牌可能在别的图里；读不出只说明本次无结论，不能据此清空。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            _loc(None, model_hint="X10 Pro", model_hint_cell="右下"),
            {"model_hint": ""},
        ],
    )
    store, refs = await _store_with_decodable(2)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    assert out.fault_localization["model_hint"] == "X10 Pro"


async def test_no_reread_when_no_nameplate_is_reported(tmp_path):
    """画面里没有铭牌就不多花一次调用。"""
    router, fake = _router(
        tmp_path, CONFIG, [_loc(None, model_hint=None, model_hint_cell=None)]
    )
    store, refs = await _store_with(1)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    assert len(fake.calls) == 1 and out.fault_localization["model_hint"] is None


async def test_findings_without_evidence_do_not_raise_a_plan_prior(tmp_path):
    """A2：没有可见证据支撑的 finding 不驱动 plan（符号条件取代模型自评 confidence）。"""
    from app.diagnose.localization import signature_plans

    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            _loc(
                None,
                findings=[
                    {"part": "滚刷", "phenomenon": "缠绕"},
                    {"part": "滤网", "phenomenon": "堵塞", "evidence": "滤网布满灰尘"},
                ],
            )
        ],
    )
    store, refs = await _store_with(1)
    out = await observe_images(router, store, session_id="s", refs=refs, text="", lane="domestic")
    assert signature_plans(out.fault_localization) == ["qa_rv_0306", "qa_rv_0016"]


# ---- 阶段 2：图文冲突由代码层在两个独立结论之间比对 ----


def _loc_for_conflict(findings, usable=True):
    return {
        "image_quality": {"usable": usable},
        "findings": [{"evidence": "见图", **f} for f in findings],
    }


def test_conflict_same_part_different_phenomenon():
    from app.diagnose.conflict import detect_conflicts

    out = detect_conflicts(
        _loc_for_conflict([{"part": "滤网", "phenomenon": "正常"}]), ["应该是滤网堵住了"]
    )
    assert out == ["you mentioned the filter is clogged, but in the photo it looks normal"]


def test_conflict_user_blames_one_part_while_the_fault_is_on_another():
    """2026-09-15 实测的那条：用户一口咬定滤网，图里其实是滚刷缠绕。"""
    from app.diagnose.conflict import detect_conflicts

    out = detect_conflicts(
        _loc_for_conflict([{"part": "滚刷", "phenomenon": "缠绕"}]),
        ["我家扫地机吸力变小了，应该是滤网堵住了"],
    )
    assert out == ["you mentioned the filter, but the photo shows a problem with the roller brush (tangled)"]


def test_conflict_claimed_part_is_not_in_the_photo():
    from app.diagnose.conflict import detect_conflicts

    out = detect_conflicts(
        _loc_for_conflict([{"part": "滚刷", "phenomenon": "正常"}]), ["滤网是不是堵了"]
    )
    assert out == ["you mentioned the filter, but it isn't visible in the photo"]


def test_no_conflict_when_text_and_image_agree_or_evidence_is_weak():
    from app.diagnose.conflict import detect_conflicts

    agree = _loc_for_conflict([{"part": "滚刷", "phenomenon": "缠绕"}])
    assert detect_conflicts(agree, ["滚刷好像缠住了"]) == []
    assert detect_conflicts(agree, ["吸力变小了"]) == [], "没点名部件就没有可比对的断言"
    assert detect_conflicts(agree, []) == []
    blurry = _loc_for_conflict([{"part": "滚刷", "phenomenon": "缠绕"}], usable=False)
    assert detect_conflicts(blurry, ["滤网堵了"]) == [], "图都看不清时「图里没有」说明不了任何事"
    no_evidence = {
        "image_quality": {"usable": True},
        "findings": [{"part": "滚刷", "phenomenon": "缠绕"}],
    }
    assert detect_conflicts(no_evidence, ["滤网堵了"]) == [], "无证据的结论不拿去质疑用户"


async def test_user_text_reaches_conflict_detection_but_never_the_model(tmp_path):
    """阶段 2 的完整回路：同一句误导文字，模型看不到，冲突检测看得到。"""
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            _loc(
                None,
                findings=[{"part": "滚刷", "phenomenon": "缠绕", "evidence": "刷体缠满毛发"}],
            )
        ],
    )
    store, refs = await _store_with(1)
    out = await observe_images(
        router,
        store,
        session_id="s",
        refs=refs,
        lane="domestic",
        text="应该是滤网堵住了",
        symptoms=["吸力变小"],
    )
    blob = " ".join(
        part.get("text", "") for part in fake.calls[0]["messages"][-1].content
    ) + fake.calls[0]["messages"][0].content
    # 词表本身会出现在指令里，所以比对的是用户那句话，而不是单个词
    assert "应该是滤网堵住了" not in blob and "吸力变小" not in blob
    assert out.fault_localization["conflicts_with_text"] == [
        "you mentioned the filter, but the photo shows a problem with the roller brush (tangled)"
    ]


# ---- 阶段 3：像素层画质门控（可信度外生） ----


def _degrade(data: bytes, *, blur: float = 0, bright: float = 1.0) -> bytes:
    import io

    from PIL import Image, ImageEnhance, ImageFilter

    im = Image.open(io.BytesIO(data))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    if bright != 1.0:
        im = ImageEnhance.Brightness(im).enhance(bright)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_pixel_gate_does_not_flag_a_well_exposed_photo_of_a_dark_device():
    """最要紧的一条：Anker 的设备大多是黑色的，深色机身不能被当成「拍得暗」。

    亮度中位数会把这两件事混为一谈（实测深色机身图中位数只有 64），所以门控用的是亮端分位。
    """
    from app.bakeoff.synth import render
    from app.images.quality import assess, measure

    dark_device = render({"kind": "scene", "seed": 7})
    m = measure(dark_device)
    assert m["luma_p50"] < 70, "这张图的中位数确实很低（深色机身）"
    assert m["luma_p95"] > 150, "但亮端正常，说明曝光没问题"
    assert assess(dark_device).verdict == "ok"


def test_pixel_gate_rejects_underexposure_and_only_warns_about_blur():
    from app.bakeoff.synth import render
    from app.images.quality import assess

    sharp = render({"kind": "parts", "part": "roller_brush", "hair": True, "seed": 1})
    assert assess(sharp).verdict == "ok"
    assert assess(_degrade(sharp, bright=0.15)).verdict == "reject"
    assert assess(_degrade(sharp, bright=0.15)).reasons == ["too_dark"]
    # 清晰度阈值标定在合成图上，不可迁移，因此只允许 marginal，永远不单独拦人
    assert assess(_degrade(sharp, blur=9)).verdict == "marginal"
    from app.images.quality import thresholds

    assert thresholds()["blurry"]["reject"] is None


async def test_unusable_photo_never_reaches_the_model(tmp_path):
    """阶段 3 验收：硬阈值命中时一次模型都不调，并带着补拍指引返回。"""
    import io

    from PIL import Image

    from app.bakeoff.synth import render

    router, fake = _router(tmp_path, CONFIG, [_loc(None)])
    store = InMemoryImageStore()
    dark = _degrade(render({"kind": "parts", "part": "roller_brush", "hair": True, "seed": 1}), bright=0.1)
    assert Image.open(io.BytesIO(dark)).size  # 图本身是完好的，只是太暗
    ref = await store.put("s", "fault", dark, "image/png")
    out = await observe_images(
        router, store, session_id="s", refs=[{**ref.public(), "run_id": "r1"}], lane="domestic"
    )
    assert out.status == "unusable"
    assert fake.calls == [], "被门控拦下时不应发起任何模型调用"
    quality = out.fault_localization["image_quality"]
    assert quality["usable"] is False and quality["reasons"] == ["too_dark"]
    assert "enough light" in quality["guidance"][0]  # 客户可见，英文（D2）
    assert out.fault_localization["findings"] == []


async def test_model_cannot_overrule_the_pixel_layer_but_can_add_to_it(tmp_path):
    """usable = 像素层 AND 模型判定；模型说不可用时，像素层的软阈值原因并进来让指引更具体。"""
    from app.bakeoff.synth import render

    router, _ = _router(
        tmp_path,
        CONFIG,
        [_loc(None, image_quality={"usable": False, "reasons": ["blurry"]})],
    )
    store = InMemoryImageStore()
    blurred = _degrade(render({"kind": "parts", "part": "roller_brush", "hair": True, "seed": 1}), blur=9)
    ref = await store.put("s", "fault", blurred, "image/png")
    out = await observe_images(
        router, store, session_id="s", refs=[{**ref.public(), "run_id": "r1"}], lane="domestic"
    )
    assert out.status == "ok"  # 软阈值没有拦下，模型跑过了
    assert out.fault_localization["image_quality"]["usable"] is False
    assert out.fault_localization["image_quality"]["reasons"] == ["blurry"]


# ---- A7 / A8：校验的触发条件不能来自被校验者；未验证的值不享受已验证的权限 ----


async def test_a_fabricated_hint_without_a_cell_is_marked_unverified(tmp_path):
    """2026-09-15 实测的那条：deepseek 给出假型号 `T2351` 且没给 cell。

    旧逻辑「有 cell 才复看」会让这种输出直接绕过校验；现在没法验就必须标成未验证。
    """
    router, fake = _router(tmp_path, CONFIG, [_loc(None, model_hint="T2351", model_hint_cell=None)])
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["model_hint"] == "T2351"
    assert out.fault_localization["model_hint_verified"] is False
    assert len(fake.calls) == 1, "没有 cell 就没法裁剪，不该白跑一次复看"


async def test_agreement_marks_verified_but_disagreement_does_not(tmp_path):
    router, _ = _router(
        tmp_path, CONFIG, [_loc(None, model_hint="X10 Pro", model_hint_cell="右下"), {"model_hint": "X10 Pro"}]
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["model_hint_verified"] is True

    router, _ = _router(
        tmp_path, CONFIG, [_loc(None, model_hint="T2351", model_hint_cell="右下"), {"model_hint": "X10 Pro"}]
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    # 两次不一致：取像素更多的那次的值，但不算已验证 —— 有一次是错的，得让用户确认
    assert out.fault_localization["model_hint"] == "X10 Pro"
    assert out.fault_localization["model_hint_verified"] is False


async def test_unverifiable_hint_keeps_its_value_but_never_claims_verified(tmp_path):
    """多图时裁的是最新一张，读不出只说明本次无结论：保留原值，但不能算验证过。"""
    router, _ = _router(
        tmp_path, CONFIG, [_loc(None, model_hint="X10 Pro", model_hint_cell="右下"), {"model_hint": ""}]
    )
    store, refs = await _store_with_decodable(2)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["model_hint"] == "X10 Pro"
    assert out.fault_localization["model_hint_verified"] is False


def test_image_limit_follows_the_model_that_will_actually_serve(tmp_path):
    """链上最小值会让首位的 4 张上限拖累整条链；应按第一个可用的视觉模型取值。"""
    from app.models.config import load_models_config
    from app.models.registry import ModelRegistry

    path = tmp_path / "m.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    cfg = load_models_config(path)
    chain = ModelRegistry(cfg, env={"K1": "x", "K2": "x"}).chain("diagnose.vision", "domestic")
    both = ModelRegistry(cfg, env={"K1": "x", "K2": "x"})
    assert image_limit(chain, both) == 2, "vl_small 可用时按它的 2 张"
    only_big = ModelRegistry(cfg, env={"K2": "x"})
    assert image_limit(chain, only_big) == 10, "vl_small 不可用时应放开到 vl_big 的 10 张"


def test_normalize_drops_duplicates_and_keeps_non_faults_out_of_observations(tmp_path):
    from app.diagnose.localization import normalize

    parsed = VisionObservation.model_validate(
        {
            "observations": [],
            "visible_parts": [],
            "findings": [
                {"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠满毛发"},
                {"part": "滚刷", "phenomenon": "缠绕", "evidence": "又说了一遍"},
                {"part": "吸口", "phenomenon": "正常", "evidence": "无异物"},
                {"part": "不可辨", "phenomenon": "不可辨"},
            ],
        }
    )
    loc = normalize(parsed)
    assert [(f["part"], f["phenomenon"]) for f in loc["findings"]] == [
        ("滚刷", "缠绕"),
        ("吸口", "正常"),
    ]


async def test_non_fault_findings_do_not_reach_observations(tmp_path):
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            _loc(
                None,
                findings=[
                    {"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠满毛发"},
                    {"part": "吸口", "phenomenon": "正常", "evidence": "无异物"},
                ],
            )
        ],
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.observations == ["滚刷缠绕"], "「吸口正常」不该进摘要与 issue facts"


# ---- 多图：cell 要挂图序号，否则「右下」不知道是哪张图的右下 ----


async def test_multi_image_reread_crops_the_image_the_model_pointed_at(tmp_path):
    router, fake = _router(
        tmp_path,
        CONFIG,
        [
            _loc(None, model_hint="X10 Pro", model_hint_cell="右下", model_hint_image=1),
            {"model_hint": "X10 Pro"},
        ],
    )
    store, refs = await _store_with_decodable(2)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["model_hint_verified"] is True
    assert out.reread_verdict == "confirmed"
    assert len(fake.calls) == 2


async def test_multi_image_without_an_index_is_not_guessed(tmp_path):
    """以前固定裁最新一张，铭牌在别的图里就必然读不出，复看形同虚设。现在不猜，直接标未验证。"""
    router, fake = _router(
        tmp_path, CONFIG, [_loc(None, model_hint="X10 Pro", model_hint_cell="右下")]
    )
    store, refs = await _store_with_decodable(2)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.reread_verdict == "skipped:no_image_index"
    assert out.fault_localization["model_hint"] == "X10 Pro"
    assert out.fault_localization["model_hint_verified"] is False
    assert len(fake.calls) == 1, "不该为了猜一张图白跑一次复看"


async def test_single_image_needs_no_index(tmp_path):
    router, _ = _router(
        tmp_path,
        CONFIG,
        [_loc(None, model_hint="X10 Pro", model_hint_cell="右下"), {"model_hint": "X10 Pro"}],
    )
    store, refs = await _store_with_decodable(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["model_hint_verified"] is True


def test_out_of_range_image_index_is_treated_as_missing():
    from app.diagnose.localization import normalize

    parsed = VisionObservation.model_validate(
        {
            "observations": [],
            "visible_parts": [],
            "model_hint": "X10 Pro",
            "model_hint_image": 5,
            "findings": [{"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠毛发", "image_index": 9}],
        }
    )
    loc = normalize(parsed, image_count=2)
    assert loc["model_hint_image"] is None
    assert loc["findings"][0]["image_index"] is None


# --------------------------------------------------------------------------
# 2026-10-09：附件用途与图片内容是两件事（P1-1）
#
# purpose 记的是「上传时系统在等什么」（前端按 pendingKind 填），不是图片内容。
# 两处消费端曾把它当内容读，于是客户在普通首问里传的订单截图既被当故障照片做曝光门控，
# 又被记成 SOP 的「故障图片/视频」证据，凑齐了换货四件套。
# 这组用例锁的是真实主办方附件，不是合成图。
# --------------------------------------------------------------------------

OFFICIAL_ATTACHMENTS = REPO_ROOT / "data" / "official" / "attachments"
# 白底单据 / 界面截图：clipped 0.77–0.96，人眼完全可读
OFFICIAL_DOCUMENTS = ("T38.jpg", "T45.jpg", "T46.jpg", "T53.jpg", "T55.jpg")
# 实物设备照
OFFICIAL_PHOTOS = ("T14.jpg", "T20.jpg", "T30.jpg", "T42.jpg", "T48.jpg")


def test_white_background_receipts_are_not_hard_rejected_as_overexposed():
    """真实订单截图 / 发票不得被像素层硬拦。

    修复前这 5 张全部 reject(too_bright) —— 客户上传凭证是 SOP 的必经步骤，
    硬拦意味着给每一张凭证都发一张补拍卡。
    """
    from app.images.quality import assess

    for name in OFFICIAL_DOCUMENTS:
        report = assess((OFFICIAL_ATTACHMENTS / name).read_bytes())
        assert report.verdict != "reject", f"{name} 被硬拦：{report.reasons} {report.metrics}"


def test_exposure_rejection_needs_saturation_and_collapsed_structure():
    """过曝判据是合取：亮部饱和「且」结构塌掉。

    单看饱和占比分不开「背景是白的」与「细节被烧掉了」：真实单据 clipped 0.77–0.96，
    与亮度 ×6 的真过曝照片同区间。区分它们的是画面里还剩不剩结构。
    """
    from app.images.quality import assess, measure, structure_floor

    doc = measure((OFFICIAL_ATTACHMENTS / "T55.jpg").read_bytes())
    assert doc["clipped"] > 0.5, "订单截图确实高度饱和"
    assert doc["focus"] >= structure_floor(), "但结构仍在，所以可读"

    sharp = (OFFICIAL_ATTACHMENTS / "T14.jpg").read_bytes()
    blown = _degrade(sharp, bright=6.0)
    m = measure(blown)
    assert m["clipped"] > 0.5 and m["focus"] < structure_floor()
    assert assess(blown).verdict == "reject" and assess(blown).reasons == ["too_bright"]
    # 真实设备照本身不受影响
    for name in OFFICIAL_PHOTOS:
        assert assess((OFFICIAL_ATTACHMENTS / name).read_bytes()).verdict == "ok", name


def test_underexposure_still_hard_rejects_regardless_of_structure():
    """结构条件只加在 too_bright 上，不加在 too_dark 上。

    too_dark 的硬阈值是「95% 的像素接近全黑」，没有被它误伤的合法输入类别：
    白底单据不会这样，曝光正常的深色机身 p95 ≈ 205 也不会。对称不是加条件的理由。
    """
    from app.images.quality import assess, measure, structure_floor

    dark = _degrade((OFFICIAL_ATTACHMENTS / "T14.jpg").read_bytes(), bright=0.12)
    assert measure(dark)["luma_p95"] < 60
    assert assess(dark).verdict == "reject" and assess(dark).reasons == ["too_dark"]
    # 即便是一张结构仍在的欠曝图（合成图梯度统计病态，focus 很高），也照样硬拦
    from PIL import Image, ImageDraw, ImageEnhance

    im = Image.new("RGB", (900, 700), (210, 210, 214))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([60, 180, 840, 470], radius=70, fill=(60, 60, 64))
    for x in range(90, 820, 26):
        draw.line([(x, 200), (x + 12, 450)], fill=(150, 150, 155), width=3)
    buf = io.BytesIO()
    ImageEnhance.Brightness(im).enhance(0.08).save(buf, "PNG")
    high_structure_but_dark = buf.getvalue()
    assert measure(high_structure_but_dark)["focus"] >= structure_floor()
    assert assess(high_structure_but_dark).verdict == "reject"


async def test_a_document_image_yields_no_fault_findings(tmp_path):
    """判为 document 的图不产生故障结论，即便模型仍为它写了 finding。

    约束的执行权不该握在被约束者手里：提示词要求只为 fault_photo 写 findings，
    这里按定性结果确定性地丢掉。
    """
    router, _ = _router(
        tmp_path,
        CONFIG,
        [
            {
                "observations": ["订单摘要页", "显示订单号 Anker016"],
                "content_kinds": [{"image_index": 1, "kind": "document"}],
                "findings": [
                    {"part": "喇叭罩", "phenomenon": "污渍", "evidence": "订单摘要页", "image_index": 1}
                ],
                "visible_parts": [],
            }
        ],
    )
    store, refs = await _store_with(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.status == "ok"
    assert out.fault_localization["content_kinds"] == ["document"]
    assert out.fault_localization["findings"] == []
    assert out.document_image_ids == [refs[0]["image_id"]]


async def test_mixed_upload_keeps_the_fault_photo_and_drops_only_the_document(tmp_path):
    """一次传订单截图 + 故障照：只排除单据那张，故障照仍然是证据。"""
    router, _ = _router(
        tmp_path,
        CONFIG.replace("max_images: 2", "max_images: 4"),
        [
            {
                "observations": ["第一张是订单页", "第二张喇叭罩有裂纹"],
                "content_kinds": [
                    {"image_index": 1, "kind": "document"},
                    {"image_index": 2, "kind": "fault_photo"},
                ],
                "findings": [
                    {"part": "喇叭罩", "phenomenon": "裂纹", "evidence": "喇叭罩有裂纹", "image_index": 2}
                ],
                "visible_parts": ["喇叭罩"],
            }
        ],
    )
    store, refs = await _store_with(2)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.document_image_ids == [refs[0]["image_id"]]
    assert [f["image_index"] for f in out.fault_localization["findings"]] == [2]


async def test_unreported_images_default_to_fault_photo(tmp_path):
    """模型漏填 content_kinds 时按 fault_photo 处理：读图只对 purpose=fault 的图调用，
    沿用调用语境是保守的一侧 —— 错判成单据会丢掉真证据，反之只是多收一次。"""
    router, _ = _router(
        tmp_path,
        CONFIG,
        [{"observations": ["滚刷缠毛"], "visible_parts": ["滚刷"]}],
    )
    store, refs = await _store_with(1)
    out = await observe_images(router, store, session_id="s", refs=refs, lane="domestic")
    assert out.fault_localization["content_kinds"] == ["fault_photo"]
    assert out.document_image_ids == []


def test_order_screenshot_does_not_satisfy_the_replacement_photo_evidence():
    """P1-1 的另一半：单据截图不得凑齐换货证据四件套。

    这条与 T55 无关 —— 任何客户在非 upload_receipt 时机上传的任何单据截图都曾被记为故障证据。
    """
    from app.actions.gate import missing_evidence
    from app.sessions.evidence import collect

    base = {
        "receipt": {"status": "order_verified", "verified_facts": {"order_no": "Anker016", "address": "1 Main St"}},
        "image_refs": [{"image_id": "img-doc", "purpose": "fault"}],
        "text": "SN: T8D04121ABCD0001",
    }
    # 读图判定这张是订单截图
    evidence = collect({**base, "document_image_ids": ["img-doc"]})
    assert "photo_or_video" not in evidence
    assert missing_evidence("replace", evidence) == ["photo_or_video"]
    # 同一张图若是故障照，证据齐全
    assert "photo_or_video" in collect(base)


def test_vision_outage_falls_back_to_upload_context_instead_of_blocking():
    """读图没跑 / 失败时不得把正常换货流程堵死：退回按上传时机判定，与修复前同行为。

    这里刻意不做成白名单（只认「确认是故障照」）：视觉链故障是运维事件，
    不该让每一单换货都因为无法测量而卡在缺证据上。
    """
    from app.sessions.evidence import collect

    state = {
        "receipt": {"status": "order_verified", "verified_facts": {"order_no": "Anker016", "address": "1 Main St"}},
        "image_refs": [{"image_id": "img-1", "purpose": "fault"}],
        "text": "SN: T8D04121ABCD0001",
    }
    assert collect(state)["photo_or_video"] == "images:img-1"
    assert collect({**state, "document_image_ids": []})["photo_or_video"] == "images:img-1"


# --------------------------------------------------------------------------
# P1-4：客户可见文案一律英文（D2，2026-10-08）
#
# 前端界面文字仍是中文（用户：「显示的先不用」），不在此约束内；
# 这里守的是**后端下发、直接显示给客户**的固定文案。
# --------------------------------------------------------------------------

CJK = __import__("re").compile(r"[一-鿿]")


def test_customer_facing_copy_from_the_backend_is_english():
    """补拍指引、步骤卡预期结果、读图回显都由后端下发并直接显示给客户。"""
    from app.diagnose.localization import echo_findings, vocabulary
    from app.plans.qa import EXPECTED

    for reason, text in vocabulary()["retake_guidance"].items():
        assert not CJK.search(text), f"retake_guidance.{reason} 仍是中文：{text}"
    assert not CJK.search(EXPECTED), EXPECTED

    echoed = echo_findings({
        "image_quality": {"usable": True},
        "findings": [{"part": "滚刷", "phenomenon": "缠绕", "evidence": "缠满毛发"}],
    })
    assert echoed and not CJK.search(echoed), echoed
    assert "roller brush tangled" in echoed
    # 「其他」说不出看到了什么（会话 dbc144 回显成「base station 其他」）：不回显
    assert echo_findings({"image_quality": {"usable": True},
                          "findings": [{"part": "基站", "phenomenon": "其他", "evidence": "基站坡道盖板敞开"}]}) is None


def test_official_qa_agent_voice_is_rewritten_for_the_customer():
    """官方 Q&A 是写给客服的内部指引，少数条目用了客服口吻；客户就是「用户」本人。

    qa.yaml 是 XLSX 的生成产物（文件头写明勿手改），所以在渲染层改人称，原文留在证据里不动。
    这里锁的是 data/official/qa.yaml 里真实存在的两句。
    """
    from app.plans.qa import customer_voice

    assert customer_voice(
        "Have the user shine a flashlight on the clean water tank pipe to check whether the pipe is damaged."
    ).startswith("Shine a flashlight")
    assert customer_voice(
        "The user can press the robot's start button to resume drying the mop."
    ).startswith("You can press")
    # 只改人称，不碰操作内容
    plain = "Remove the clean water tank from the base station and check the seal ring."
    assert customer_voice(plain) == plain


def test_no_agent_voice_survives_into_any_rendered_step():
    """全量扫一遍官方 Q&A：渲染后不应再有「让用户去做某事」的客服口吻。"""
    import re

    from app.official.qa_index import get_qa_index
    from app.plans.qa import customer_voice, plans_config

    agent_voice = re.compile(r"\b(?:have|ask|tell|instruct) the (?:user|customer)\b|\bthe (?:user|customer) (?:can|should|needs to)\b", re.IGNORECASE)
    cfg = plans_config(get_qa_index())
    offenders = [
        (key, ev.snippet[:80])
        for key, ev in cfg.evidence.items()
        if agent_voice.search(customer_voice(ev.snippet))
    ]
    assert not offenders, offenders
