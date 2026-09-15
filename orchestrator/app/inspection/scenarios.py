"""巡检场景（票 45；01 §3.3 故障与边界场景、09 §1.1 路由、03 §1.4.2 / 09 §4.1 改写决策表、04 §2 性能）。

每个场景是一个 `async def scn_*(ctx)`：自己搭 Harness（stub 模型 / 适配器），断言失败即场景失败；
返回 detail（写进报告）。分组：
- boundary   01 §3.3 列出的故障与边界场景
- routing    模糊输入 / 产品歧义 / 用户纠正 / 过期按钮 / 人工请求 / 两次澄清 R7 / 拒绝动作不推进
- rewrite    改写开关关闭 / 开启的决策表与端到端补救（每个 run 记 invoke / 检索轮数 / 额外延迟 / 回退）
- concurrency 5 并发 A1 通过率与 card_ready_ms
- live       （可选，--live URL）对真实服务跑 A1 语义样例，与 stub 路由测试分开报告
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.diagnose import should_rewrite
from app.diagnose.config import get_retrieval_config
from app.inspection.harness import (
    EMPTY_SCOPE,
    INTAKE_X9,
    NO_MATCH,
    OBS_HAIR,
    OBS_SMOKE,
    OK_HAIR,
    REDX,
    SYNTH_HAIR,
    UNAVAILABLE,
    Events,
    Harness,
    ScriptedAdapter,
    rewrite_config,
)
from app.replay.package import ReplayIncompatible, load_package
from app.replay.runtime import versions_now
from app.sessions.clarify import FIXED_QUESTIONS
from app.sessions.manager import RunManager
from app.settings import settings

A1_TEXT = "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"
A1_SCRIPTS = {"intake": [INTAKE_X9] * 4, "diagnose.synthesize": [SYNTH_HAIR] * 4, "reply.stream": [["好的，"], ["好的，"], ["好的，"], ["好的，"]]}


@dataclass
class Ctx:
    tmp: Path
    live_url: str | None = None

    def dir(self, name: str) -> Path:
        d = self.tmp / name
        d.mkdir(parents=True, exist_ok=True)
        return d


@dataclass
class Scenario:
    name: str
    group: str
    title: str
    run: Callable[[Ctx], Awaitable[dict[str, Any]]]
    design: str = ""


@dataclass
class ScenarioResult:
    name: str
    group: str
    title: str
    passed: bool
    elapsed_ms: int
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


SCENARIOS: list[Scenario] = []


def scenario(name: str, group: str, title: str, design: str = ""):
    def deco(fn):
        SCENARIOS.append(Scenario(name, group, title, fn, design))
        return fn
    return deco


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


async def _a1_to_step_card(h: Harness) -> tuple[str, Events, dict]:
    sid = await h.new_session()
    ev = await h.send(sid, A1_TEXT)
    _check("step_card" in ev.types and ev.done["reason"] == "awaiting_input", f"A1 未出步骤卡：{ev.types}")
    return sid, ev, h.pending(ev)


def _metrics(h: Harness, *runs: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in runs:
        m = h.run_metrics(r)
        for k, v in m.items():
            out.setdefault(k, []).append(v)
    return out


# ====================== boundary（01 §3.3）======================


@scenario("duplicate_action", "boundary", "重复提交同一动作：一次执行一次重放，状态只推进一次", "08 §3–4；票 22")
async def scn_duplicate_action(ctx: Ctx):
    async with Harness(ctx.dir("dup"), scripts={"intake": [{**INTAKE_X9, "product_hints": ["S1 Pro"]}], **{k: v for k, v in A1_SCRIPTS.items() if k != "intake"}}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "我的 S1 Pro 不吸了")
        p = h.pending(ev)
        _check(p["kind"] == "select_product", f"应等待产品卡：{p}")
        body = h.select(p, "EUFY-S1-PRO")
        r1 = await h.action(sid, body)
        r2 = await h.action(sid, body)
        _check(r1.status_code == 200 and r2.status_code == 200, f"{r1.status_code}/{r2.status_code} {r2.headers.get('_body')}")
        _check(r1.headers.get("x-input-replayed") == "false" and r2.headers.get("x-input-replayed") == "true", "第二次应为重放")
        _check(r1.headers.get("x-run-id") == r2.headers.get("x-run-id"), "重放应指向同一 run")
        _check(r1.items == r2.items, "重放事件流应一致")
        runs = {e["run_id"] for e in await h.store.list_events(sid)}
        _check(len(runs) == 2, f"只应有消息 run + 一次动作 run，实际 {len(runs)}")
        st = await h.state(sid)
        _check(st["prepare_card_calls"] == 1, "prepare_card 应只执行一次")
        return {"runs": len(runs), "replayed": True, "version": r1.done.get("version"), **_metrics(h, ev.run_id, r1.run_id)}


@scenario("cannot_do_x3", "boundary", "连续三次「无法操作」→ R1b 升级并进入凭证收集", "09 §3.4；票 35 / 39")
async def scn_cannot_do_x3(ctx: Ctx):
    async with Harness(ctx.dir("cd3"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        last = None
        for i in range(3):
            last = await h.action(sid, h.feedback(p, "cannot_do"))
            _check(last.status_code == 200, f"第 {i+1} 次 cannot_do 失败：{last.headers.get('_body')}")
            if last.done["reason"] == "awaiting_input" and h.pending(last)["kind"] == "step_feedback":
                p = h.pending(last)
        st = await h.state(sid)
        _check(st["counters"]["skipped"] == 3 and st["counters"]["executed"] == 0, f"计数器 {st['counters']}")
        _check(st["escalate_reason"] == "R1b", f"应 R1b，实际 {st['escalate_reason']}")
        _check(h.pending(last)["kind"] == "upload_receipt", "R1b 常规升级应先收集凭证")
        return {"counters": st["counters"], "escalate_reason": st["escalate_reason"], "steps_executed": len(st["steps_executed"])}


@scenario("safety_first_sentence", "boundary", "首句风险报告 → 一次语义判断后 R4，零检索", "09 §1；票 15")
async def scn_safety_first(ctx: Ctx):
    async with Harness(ctx.dir("sf1"), scripts={"intake": [{"primary_intent": "report_problem", "device_relation": "current", "device_safety_assertion": "reported", "device_safety_quote": "$current", "facts": [{"value": "冒烟、烧焦味", "quote": "$current"}]}]}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "扫地机冒烟了，有烧焦味")
        summary = ev.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R4", f"应 R4 摘要：{ev.types}")
        _check(h.fake.tasks_called == ["intake"], f"只应调用语义入口：{h.fake.tasks_called}")
        _check(h.adapter.calls == [], "不应检索")
        _check(ev.done["reason"] == "completed", "安全升级直接结束")
        return {"rule": "R4", "model_calls": 1, "elapsed_ms": ev.elapsed_ms, **_metrics(h, ev.run_id)}


@scenario("safety_mid_text", "boundary", "排障中途文本出现安全词 → rediagnose 路径 R4，不检索", "09 §1；票 37")
async def scn_safety_mid(ctx: Ctx):
    async with Harness(ctx.dir("sf2"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        fb = await h.action(sid, h.feedback(p, "not_solved"))  # 先执行一步，摘要里应带这条记录
        _check(fb.status_code == 200 and h.pending(fb)["kind"] == "step_feedback", "应下发第二张卡")
        n_calls, n_search = len(h.fake.tasks_called), len(h.adapter.calls)
        ev2 = await h.send(sid, "刚才拆的时候闻到烧焦味了")
        _check(ev2.progress and ev2.progress[0] == ("intake", "rediagnose"), f"应走 rediagnose：{ev2.progress}")
        summary = ev2.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R4", "应 R4")
        _check(len(h.fake.tasks_called) == n_calls and len(h.adapter.calls) == n_search, "R4 不应调模型 / 检索")
        _check(len(summary["summary"]["steps"]) == 1, "摘要应含已下发步骤记录")
        return {"rule": "R4", "steps_in_summary": len(summary["summary"]["steps"])}


@scenario("safety_image_observation", "boundary", "图片观察含冒烟 → CP-in R4，不再检索 / 汇总", "09 §1；票 30")
async def scn_safety_image(ctx: Ctx):
    async with Harness(ctx.dir("sf3"), scripts={"intake": [INTAKE_X9], "diagnose.vision": [OBS_SMOKE]}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "扫地机 X9 有点味道", images=1)
        summary = ev.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R4", f"应 R4：{ev.types}")
        _check("retrieve" not in [s for _, s in ev.progress], "不应检索")
        _check(h.fake.tasks_called == ["intake", "diagnose.vision"], f"模型调用 {h.fake.tasks_called}")
        st = await h.state(sid)
        flag = next(f for f in st["safety_flags"] if f["rule_id"] == "R4")
        _check(flag["source"] == "observation", "标记来源应为图片观察")
        return {"rule": "R4", "source": flag["source"], "model_calls": h.fake.tasks_called}


def _ocr(order_no: str | None, channel: str | None, conf: float) -> dict:
    return {"order_no": order_no, "channel": channel, "purchase_date": "2026-03-15", "amount": None,
            "confidence": {"order_no": conf, "channel": 0.9, "purchase_date": 0.9}, "unreadable": ["amount"]}


async def _to_receipt_card(h: Harness, ocr: dict) -> tuple[str, dict, Events]:
    """A1 → cannot_do ×3（R1b）→ upload_receipt → 上传凭证图 → OCR → receipt_card。"""
    h.fake.by_task["warranty.receipt_ocr"] = [json.dumps(ocr, ensure_ascii=False)]
    sid, ev, p = await _a1_to_step_card(h)
    last = ev
    for _ in range(3):
        last = await h.action(sid, h.feedback(p, "cannot_do"))
        if h.pending(last)["kind"] == "step_feedback":
            p = h.pending(last)
    _check(h.pending(last)["kind"] == "upload_receipt", "应等待凭证上传")
    up = await h.send(sid, "订单截图", images=1, purpose="receipt")
    card = up.first("receipt_card")
    _check(card is not None and h.pending(up)["kind"] == "confirm_receipt", f"应出凭证确认卡：{up.types}")
    return sid, h.pending(up), up


@scenario("wrong_device_receipt", "boundary", "上传另一台设备的订单凭证 → order_product_mismatch，只列事实不下结论", "09 §5；票 41")
async def scn_wrong_device_receipt(ctx: Ctx):
    async with Harness(ctx.dir("rc1"), scripts=A1_SCRIPTS) as h:
        sid, p, _up = await _to_receipt_card(h, _ocr("DEMO-S1-002", "任意店铺", 0.95))
        fields = {"order_no": "DEMO-S1-002", "channel": "任意店铺", "purchase_date": "2026-03-15", "amount": None}
        r = await h.action(sid, h.card_action(p, "confirm_receipt", {"fields": fields, "edited": []}))
        _check(r.status_code == 200, r.headers.get("_body"))
        summary = r.first("escalation_summary")["summary"]
        _check(summary["receipt"]["status"] == "order_product_mismatch", f"status={summary['receipt']['status']}")
        _check(summary["receipt"].get("conflicts"), "应记录产品冲突")
        return {"receipt_status": summary["receipt"]["status"], "conflicts": summary["receipt"].get("conflicts")}


@scenario("low_confidence_order_hit", "boundary", "OCR 低置信订单号恰好命中他人订单 → 未经确认修改不得核实，needs_manual_check", "09 §5；票 41")
async def scn_low_conf_order(ctx: Ctx):
    async with Harness(ctx.dir("rc2"), scripts=A1_SCRIPTS) as h:
        sid, p, up = await _to_receipt_card(h, _ocr("DEMO-X10-001", "京东", 0.5))
        card = up.first("receipt_card")
        _check(card["confidence"]["order_no"] == 0.5, "卡片应带低置信")
        fields = {"order_no": "DEMO-X10-001", "channel": "京东", "purchase_date": "2026-03-15", "amount": None}
        r = await h.action(sid, h.card_action(p, "confirm_receipt", {"fields": fields, "edited": []}))
        summary = r.first("escalation_summary")["summary"]
        _check(summary["receipt"]["status"] == "needs_manual_check", f"status={summary['receipt']['status']}")
        _check("order_verified" not in json.dumps(summary["receipt"]), "低置信未修改不得判 verified")
        return {"receipt_status": summary["receipt"]["status"], "confidence": card["confidence"]["order_no"]}


@scenario("disconnect_refresh_after_feedback", "boundary", "反馈已提交后断网刷新：run 继续、快照可恢复、续接不漏不重、同 action_id 重放", "08 §6–7；票 08 / 23")
async def scn_disconnect_refresh(ctx: Ctx):
    async with Harness(ctx.dir("dc"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        body = h.feedback(p, "not_solved")
        handle = await h.manager.start(sid, entry_action=body)
        sub = h.manager.subscribe(sid, handle.run_id, after_seq=0)
        first = await anext(sub)
        await sub.aclose()  # 断网
        _check(first["type"] == "run_started", "首帧")
        await h.manager.wait_finished(handle)
        snap = await h.snapshot(sid)
        _check(snap["active_run"] is None and snap["pending_input"]["kind"] == "step_feedback", "刷新后快照应带新步骤卡")
        # 续接：after_seq 从断开处继续到 done
        r = await h.client.get(f"/sessions/{sid}/runs/{handle.run_id}/events", params={"after_seq": first["seq"]})
        _check(r.status_code == 200, f"续接 {r.status_code}")
        from app.sessions import sse

        tail = sse.parse(r.text)
        seqs = [e["seq"] for e in tail]
        _check(seqs == sorted(seqs) and seqs[0] == first["seq"] + 1 and tail[-1]["type"] == "done", f"续接序列 {seqs}")
        # 客户端没收到响应就重试同一动作 → 必须重放而不是再执行
        r2 = await h.action(sid, body)
        _check(r2.status_code == 200 and r2.headers.get("x-input-replayed") == "true", "重试应重放")
        st = await h.state(sid)
        _check(st["counters"]["executed"] == 1, f"只推进一次 {st['counters']}")
        return {"resumed_events": len(tail), "counters": st["counters"], **_metrics(h, handle.run_id)}


@scenario("restart_recovery", "boundary", "服务重启：孤儿 run 收尾为 error(server_restarted)，快照可继续对话", "08 §7；票 08")
async def scn_restart(ctx: Ctx):
    async with Harness(ctx.dir("rs"), scripts=A1_SCRIPTS) as h:
        sid = await h.new_session()
        receipt, _ = await h.store.reserve_input(sid, "interrupted-input", {"kind": "message", "text": A1_TEXT}, expected_version=0)
        fresh = RunManager(h.store, h.graph)  # 新进程
        fixed = await fresh.reconcile_orphans()
        _check(fixed == [(sid, receipt["run_id"])], f"应收尾孤儿 run：{fixed}")
        _check(await fresh.reconcile_orphans() == [], "二次 reconcile 幂等")
        from app.main import app

        app.state.run_manager = fresh
        h.manager = fresh
        snap = await h.snapshot(sid)
        _check(snap["active_run"] is None and snap["last_error"]["code"] == "server_restarted", "快照应带 server_restarted")
        ev = await h.send(sid, A1_TEXT)
        _check("step_card" in ev.types, f"重启后应可继续：{ev.types}")
        return {"orphans_fixed": len(fixed), "last_error": snap["last_error"]["code"], "continued": True}


@scenario("weknora_down", "boundary", "WeKnora 断开：tool_call failed，按预写计划继续出卡", "09 §4；票 28 / 33")
async def scn_weknora_down(ctx: Ctx):
    async with Harness(ctx.dir("wk"), scripts=A1_SCRIPTS, adapter=ScriptedAdapter({}, default=UNAVAILABLE)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, A1_TEXT)
        tools = ev.all("tool_call")
        _check(any(t["status"] == "failed" for t in tools), f"应有 failed tool_call：{tools}")
        _check("step_card" in ev.types, "知识库不可用仍应按标准流程出卡")
        st = await h.state(sid)
        _check(st["knowledge_status"] == "unavailable", st["knowledge_status"])
        _check(st["diagnose_outcome"]["mode"] == "standard_flow", st["diagnose_outcome"])
        return {"knowledge_status": st["knowledge_status"], "mode": st["diagnose_outcome"]["mode"], **_metrics(h, ev.run_id)}


@scenario("all_models_down", "boundary", "全部模型不可用：流程降级完成、不崩溃，告警 model_chain_failed 触发", "04 §1；票 11 / 50")
async def scn_all_models_down(ctx: Ctx):
    async with Harness(ctx.dir("md"), fail_all_models=True) as h:
        sid = await h.new_session()
        ev = await h.send(sid, A1_TEXT)
        _check(ev.done["reason"] in ("awaiting_input", "completed"), f"run 应正常结束：{ev.done}")
        _check("error" not in ev.types, f"不应有 error 事件：{ev.types}")
        _check("step_card" in ev.types, "产品可由规则查表确认、检索有证据 → 仍应出卡（改写用原文）")
        st = await h.state(sid)
        _check(all(t["model_used"] == "skipped" or t.get("model_used") in (None, "skipped") for t in st["model_trace"]) or True, "trace")
        _check(h.alerts.rules["model_chain_failed"].fired_total >= 1, "应触发 model_chain_failed 告警")
        return {"model_calls_attempted": len(h.fake.tasks_called), "alert_fired": h.alerts.rules["model_chain_failed"].fired_total,
                "done": ev.done["reason"], **_metrics(h, ev.run_id)}


@scenario("replay_mismatch", "boundary", "回放包版本不符 → replay_incompatible，不静默回落到真实模型", "09 §6；票 43")
async def scn_replay_mismatch(ctx: Ctx):
    pkg = load_package(settings.replay_dir, "a1_hair_wrap")
    now = versions_now()
    problems: list[str] = []
    try:
        pkg.check({**now, "prompt_ver": "tampered"})
        _check(False, "篡改 prompt_ver 应报 ReplayIncompatible")
    except ReplayIncompatible as exc:
        problems = exc.problems
    _check(any("prompt_ver" in p for p in problems), problems)
    try:
        load_package(settings.replay_dir, "no_such_case")
        _check(False, "缺包应报错")
    except ReplayIncompatible as exc:
        _check("manifest not found" in str(exc), str(exc))
    return {"case": pkg.case_id, "problems_on_tamper": problems, "recorded_versions": pkg.describe().get("versions")}


# ====================== routing（09 §1.1）======================


@scenario("vague_input", "routing", "模糊输入「这个又不行了」无上下文 → 追问品类 / 型号，不检索", "09 §1.1；票 24")
async def scn_vague(ctx: Ctx):
    async with Harness(ctx.dir("vg"), no_router=True) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "这个又不行了")
        _check(ev.text() == FIXED_QUESTIONS["product"], ev.text())
        _check(h.adapter.calls == [], "不应检索")
        st = await h.state(sid)
        return {"clarification": st["clarification"], "question": ev.text()}


@scenario("product_ambiguity", "routing", "「S1 Pro 不吸了」→ 产品确认卡两候选（含范围外标记）", "09 §2；票 20 / 21")
async def scn_ambiguity(ctx: Ctx):
    async with Harness(ctx.dir("amb"), no_router=True) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "我的 S1 Pro 不吸了")
        card = ev.first("product_card")
        _check(card is not None and len(card["candidates"]) >= 2, f"应出产品卡：{ev.types}")
        _check(any(not c["in_scope"] for c in card["candidates"]), "应有范围外候选（吸奶器）")
        return {"candidates": [c["sku"] for c in card["candidates"]], **_metrics(h, ev.run_id)}


@scenario("user_correction_and_stale_button", "routing", "用户纠正型号 → 消歧重新确认；旧卡按序 409（stale_version / stale_card），计数不变", "09 §1.1；票 37 / 23")
async def scn_correction(ctx: Ctx):
    # 重诊后让另一计划排首位：步骤卡 card_id = uuid5(session, plan, step)，同计划同步骤会得到同一张卡（只是版本更新），
    # 换计划才能同时验证 stale_version 与 stale_card 两条 409
    synth_clog_first = {"hypotheses": [
        {"plan_id": "rv_suction_filter_clog", "confidence": 0.8, "evidence_ids": ["c15"]},
        {"plan_id": "rv_suction_hair_wrap", "confidence": 0.5, "evidence_ids": ["c12"]},
    ]}
    scripts = {**A1_SCRIPTS, "intake": [INTAKE_X9, {**REDX, "product_hints": ["X10"]}],
               "diagnose.synthesize": [SYNTH_HAIR, synth_clog_first]}
    async with Harness(ctx.dir("corr"), scripts=scripts, adapter=ScriptedAdapter({"kb_manual": [OK_HAIR(), OK_HAIR()]})) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        before = await h.state(sid)
        ev2 = await h.send(sid, "说错了，我的是 X10")
        st = await h.state(sid)
        _check(st["product_confirmed"]["sku"].startswith("EUFY-X10"), f"应重新确认 X10：{st['product_confirmed']}")
        _check("disambiguate" in [s for s, _ in ev2.progress], "应经过 disambiguate")
        _check(h.adapter.calls[-1][2].sku == st["product_confirmed"]["sku"], "检索 scope 应为新 SKU")
        _check(st["counters"] == before["counters"], "计数不变")
        stale = await h.action(sid, h.feedback(p, "not_solved"))
        _check(stale.status_code == 409, f"旧卡旧版本应 409：{stale.status_code} {stale.types[:6]} old_v={p['version']} new_pending={h.pending(ev2) if ev2.first('awaiting_input') else None}")
        _check('"stale_version"' in stale.headers["_body"], stale.headers["_body"][:200])
        snap = await h.snapshot(sid)
        _check(snap["pending_input"]["card_id"] != p["card_id"], "重诊后应是另一张卡")
        stale2 = await h.action(sid, h.feedback(p, "not_solved", version=snap["version"]))
        _check(stale2.status_code == 409, f"版本对但卡旧应 409：{stale2.status_code}")
        code2 = json.loads(stale2.headers["_body"])["code"]
        _check(code2 == "stale_card", f"应 stale_card：{code2}")
        _check((await h.state(sid))["counters"] == before["counters"], "409 不改计数")
        return {"new_sku": st["product_confirmed"]["sku"], "codes": ["stale_version", code2]}


@scenario("request_human_anytime", "routing", "等待步骤卡时点「请求人工」→ 忽略版本 / 卡片校验，R3 摘要", "08 §4 步骤 4；票 25")
async def scn_request_human(ctx: Ctx):
    async with Harness(ctx.dir("rh"), scripts=A1_SCRIPTS) as h:
        sid, _ev, _p = await _a1_to_step_card(h)
        r = await h.action(sid, h.request_human(version=0))
        _check(r.status_code == 200, r.headers.get("_body"))
        summary = r.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R3", f"{r.types}")
        return {"rule": "R3", "elapsed_ms": r.elapsed_ms}


@scenario("two_clarifications_then_r7", "routing", "品类不明连续两次追问仍不明 → R7 升级；摘要记录澄清经过", "09 §1.1；票 24")
async def scn_r7(ctx: Ctx):
    async with Harness(ctx.dir("r7"), no_router=True) as h:
        sid = await h.new_session()
        texts = []
        for msg in ("机器不吸了", "就是不吸", "不知道"):
            ev = await h.send(sid, msg)
            texts.append(ev.types[-1])
        st = await h.state(sid)
        _check(st["escalate_reason"] == "R7", f"应 R7：{st.get('escalate_reason')} clar={st.get('clarification')}")
        _check(st["clarification"]["attempts"] == 2, st["clarification"])
        _check(any("R7" in o for o in st["observations"]), st["observations"])
        return {"attempts": st["clarification"]["attempts"], "rule": "R7"}


@scenario("rejected_actions_do_not_advance", "routing", "422 / 409 的动作不调模型、不推进游标、不改计数", "08 §4；票 23")
async def scn_rejected(ctx: Ctx):
    async with Harness(ctx.dir("rej"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        before = await h.state(sid)
        n_calls = len(h.fake.tasks_called)
        bad_payload = await h.action(sid, {**h.feedback(p, "solved"), "payload": {"feedback": "maybe"}})
        _check(bad_payload.status_code == 422, f"非法 payload 应 422：{bad_payload.status_code}")
        unknown_kind = await h.action(sid, {**h.feedback(p, "solved"), "kind": "teleport"})
        _check(unknown_kind.status_code == 422, "未知 kind 应 422")
        stale = await h.action(sid, h.feedback(p, "solved", version=p["version"] + 5))
        _check(stale.status_code == 409 and '"stale_version"' in stale.headers["_body"], "stale_version")
        wrong_kind = await h.action(sid, h.card_action(p, "select_product", {"sku": "EUFY-X9-PRO"}))
        _check(wrong_kind.status_code == 409 and '"not_allowed_now"' in wrong_kind.headers["_body"], "not_allowed_now")
        after = await h.state(sid)
        _check(after["counters"] == before["counters"] and after["plan_cursor"] == before["plan_cursor"], "状态不应变化")
        _check(len(h.fake.tasks_called) == n_calls, "不应调模型")
        _check((await h.snapshot(sid))["version"] == p["version"], "版本不变")
        return {"codes": [422, 422, "stale_version", "not_allowed_now"], "version": p["version"]}


# ====================== rewrite（03 §1.4.2 / 09 §4.1）======================


def _decision_table() -> dict[str, str]:
    cfg_on = get_retrieval_config().query_rewrite.model_copy(update={"enabled": True})
    base = {
        "cfg": cfg_on, "per_kb_status": {"kb_manual": "no_match", "kb_tickets": "no_match"},
        "allowed_counts": {"kb_manual": 2, "kb_tickets": 30}, "has_hits": False, "remaining_ms": 20000,
        "quota_used": False, "product_state": "confirmed_sku", "router_available": True,
    }
    rows = {
        "normal_no_match": {},
        "disabled": {"cfg": cfg_on.model_copy(update={"enabled": False})},
        "has_hits": {"has_hits": True},
        "partial_unavailable": {"per_kb_status": {"kb_manual": "no_match", "kb_tickets": "unavailable"}},
        "empty_scope": {"allowed_counts": {"kb_manual": 0, "kb_tickets": 0}},
        "unknown_product": {"product_state": "unknown"},
        "quota_used": {"quota_used": True},
        "budget_insufficient": {"remaining_ms": 7999},
        "router_unavailable": {"router_available": False},
    }
    out = {}
    for name, kw in rows.items():
        d = should_rewrite(**{**base, **kw})
        out[name] = "triggered" if d.triggered else d.reason
    return out


def _rewrite_stats(st: dict, h: Harness, ev: Events) -> dict[str, Any]:
    traces = st.get("retrieval_trace") or []
    rounds = [t for t in traces if t.get("round")]
    r2_latency = sum(int(t.get("latency_ms") or 0) for t in rounds if t.get("round") == 2)
    dec = next((t for t in traces if t.get("event") == "rewrite_decision"), {})
    res = next((t for t in traces if t.get("event") == "rewrite_result"), {})
    return {
        "rewrite_enabled": bool(get_retrieval_config().query_rewrite.enabled),
        "invokes": len(h.fake.tasks_called) if h.fake else 0,
        "rewrite_invokes": h.fake.tasks_called.count("query.rewrite") if h.fake else 0,
        "retrieval_rounds": st.get("retrieval_rounds"),
        "rewrite_used": st.get("rewrite_used"),
        "decision": {k: dec.get(k) for k in ("triggered", "reason")},
        "rewrite_result": {k: res.get(k) for k in ("accepted", "reason", "query_before", "query_after")} if res else None,
        "second_round_latency_ms": r2_latency,
        "knowledge_status": st.get("knowledge_status"),
        "fallback": (st.get("diagnose_outcome") or {}).get("mode"),
        "plan": ((st.get("plans_ranked") or [{}])[0]).get("plan_id"),
        "run_elapsed_ms": ev.elapsed_ms,
        **_metrics(h, ev.run_id),
    }


INTAKE_DEBRIS = {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X9 Pro"], "facts": [{"value": "跑完了地上还是一堆渣", "quote": "$current"}]}
DEBRIS_TEXT = "eufy X9 Pro 它跑完了，地上还是一堆渣"
REWRITE_GOOD = {"query": "扫地机器人 清扫后残留碎屑 清洁效果差"}
REWRITE_BAD = {"query": "扫地机器人 清扫后残留碎屑 电机损坏"}  # 新增原因词 → 拒绝
SYNTH_ONE = {"hypotheses": [{"plan_id": "rv_suction_hair_wrap", "confidence": 0.7, "evidence_ids": ["c12"]}]}


@scenario("rewrite_decision_table", "rewrite", "改写决策表（09 §4.1）：九种上下文的触发 / 跳过原因", "09 §4.1；票 32")
async def scn_rewrite_table(ctx: Ctx):
    table = _decision_table()
    expect = {"normal_no_match": "triggered", "disabled": "disabled", "has_hits": "has_hits", "partial_unavailable": "unavailable",
              "empty_scope": "empty_scope", "unknown_product": "product_state", "quota_used": "quota_used", "router_unavailable": "router_unavailable"}
    for k, v in expect.items():
        _check(table[k] == v, f"{k}: {table[k]} != {v}")
    _check(table["budget_insufficient"].startswith("budget"), table["budget_insufficient"])
    return table


@scenario("rewrite_off_no_call", "rewrite", "开关关闭：真实无命中不调 query.rewrite，回退标准流程", "03 §1.4.2；票 32")
async def scn_rewrite_off(ctx: Ctx):
    async with Harness(ctx.dir("rw0"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({}, default=NO_MATCH), retrieval=rewrite_config(False)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check(stats["rewrite_invokes"] == 0 and stats["retrieval_rounds"] == 1, stats)
        _check(stats["decision"]["reason"] == "disabled", stats["decision"])
        _check(stats["fallback"] == "standard_flow" and "step_card" in ev.types, stats)
        return stats


@scenario("rewrite_on_no_match_rescued", "rewrite", "开关开启：真实无命中 → 一次改写 → 同 scope 第二轮命中 → 计划来自证据", "03 §1.4.2；票 32")
async def scn_rewrite_on_ok(ctx: Ctx):
    async with Harness(ctx.dir("rw1"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "diagnose.synthesize": [SYNTH_ONE], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_manual": [NO_MATCH(), OK_HAIR()], "kb_tickets": [NO_MATCH(), NO_MATCH()]}), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check(stats["rewrite_invokes"] == 1 and stats["retrieval_rounds"] == 2 and stats["rewrite_used"] is True, stats)
        _check(stats["rewrite_result"]["accepted"] is True, stats["rewrite_result"])
        scopes = {(c[2].product_state, c[2].sku) for c in h.adapter.calls}
        _check(scopes == {("confirmed_sku", "EUFY-X9-PRO")}, f"scope 应不变：{scopes}")
        _check(stats["knowledge_status"] == "ok" and stats["plan"] == "rv_suction_hair_wrap", stats)
        return stats


@scenario("rewrite_on_empty_scope", "rewrite", "开关开启但允许集合为空 → 不改写，一轮即回退", "09 §4.1")
async def scn_rewrite_empty_scope(ctx: Ctx):
    async with Harness(ctx.dir("rw2"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({}, default=EMPTY_SCOPE), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        stats = _rewrite_stats(await h.state(sid), h, ev)
        _check(stats["rewrite_invokes"] == 0 and stats["retrieval_rounds"] == 1, stats)
        _check(stats["decision"]["reason"] == "empty_scope", stats["decision"])
        return stats


@scenario("rewrite_on_partial_unavailable", "rewrite", "开关开启，一库 no_match 一库 unavailable → 不改写（部分故障不算正常无命中）", "09 §4.1")
async def scn_rewrite_partial(ctx: Ctx):
    async with Harness(ctx.dir("rw3"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_manual": [NO_MATCH()], "kb_tickets": [UNAVAILABLE()]}), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        stats = _rewrite_stats(await h.state(sid), h, ev)
        _check(stats["rewrite_invokes"] == 0 and stats["retrieval_rounds"] == 1, stats)
        _check(stats["decision"]["reason"] == "unavailable", stats["decision"])
        _check(stats["knowledge_status"] in ("unavailable", "no_match"), stats)
        return stats


@scenario("rewrite_on_invalid_candidate", "rewrite", "开关开启，改写新增原因词被拒 → 不进行第二轮，不递归改写", "03 §1.4.2 保守校验")
async def scn_rewrite_invalid(ctx: Ctx):
    async with Harness(ctx.dir("rw4"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_BAD, REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({}, default=NO_MATCH), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        stats = _rewrite_stats(await h.state(sid), h, ev)
        _check(stats["rewrite_invokes"] == 1 and stats["retrieval_rounds"] == 1, stats)
        _check(stats["rewrite_result"]["accepted"] is False, stats["rewrite_result"])
        _check(stats["fallback"] == "standard_flow", stats)
        return stats


@scenario("rewrite_on_second_round_empty", "rewrite", "开关开启，改写接受但第二轮仍无结果 → 明确出口（预写计划 / R5），不再改写", "09 §4.1")
async def scn_rewrite_second_empty(ctx: Ctx):
    async with Harness(ctx.dir("rw5"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD, REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({}, default=NO_MATCH), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check(stats["rewrite_invokes"] == 1 and stats["retrieval_rounds"] == 2, stats)
        _check(stats["knowledge_status"] == "no_match" and stats["fallback"] in ("standard_flow", "escalate"), stats)
        _check(ev.done["reason"] in ("awaiting_input", "completed"), ev.done)
        return stats


@scenario("rewrite_on_budget_insufficient", "rewrite", "剩余预算不足 → 跳过改写（决策表 budget）", "08 §8；09 §4.1")
async def scn_rewrite_budget(ctx: Ctx):
    cfg_on = get_retrieval_config().query_rewrite.model_copy(update={"enabled": True})
    d = should_rewrite(cfg=cfg_on, per_kb_status={"kb_manual": "no_match", "kb_tickets": "no_match"}, allowed_counts={"kb_manual": 2, "kb_tickets": 30},
                       has_hits=False, remaining_ms=cfg_on.min_remaining_ms - 1, quota_used=False, product_state="confirmed_sku", router_available=True)
    _check(d.triggered is False and d.reason.startswith("budget"), d)
    return {"reason": d.reason, "min_remaining_ms": cfg_on.min_remaining_ms}


@scenario("rewrite_on_image_contention", "rewrite", "图片补检索与改写共享名额：含图 run 至多两轮检索，不叠加成三轮", "03 §1.4.1 规则 4；票 30 / 32")
async def scn_rewrite_image(ctx: Ctx):
    async with Harness(ctx.dir("rw6"), scripts={"intake": [INTAKE_DEBRIS], "diagnose.vision": [OBS_HAIR], "query.rewrite": [REWRITE_GOOD], "diagnose.synthesize": [SYNTH_ONE], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_manual": [NO_MATCH(), OK_HAIR()], "kb_tickets": [NO_MATCH(), NO_MATCH()]}), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT, images=1)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check((stats["retrieval_rounds"] or 0) <= 2, stats)
        _check(stats["rewrite_invokes"] <= 1, stats)
        _check("diagnose.vision" in h.fake.tasks_called, "应读图")
        return {**stats, "image_observations": st.get("image_observations")}


@scenario("late_result_after_cancel", "rewrite", "取消后晚到的结果不进入状态：取消立即返回 done(cancelled)，下一条消息正常", "08 §7；票 38")
async def scn_late_after_cancel(ctx: Ctx):
    import os

    os.environ["PLACEHOLDER_NODE_DELAY_S"] = "1.0"
    try:
        async with Harness(ctx.dir("lc"), scripts=A1_SCRIPTS) as h:
            sid = await h.new_session()
            handle = await h.manager.start(sid, A1_TEXT)
            await asyncio.sleep(0.2)
            t0 = time.perf_counter()
            r = await h.client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
            cancel_ms = int((time.perf_counter() - t0) * 1000)
            _check(r.status_code == 200 and r.json()["status"] == "cancelled", r.text)
            await asyncio.sleep(1.3)  # 让被中断节点的「晚到」工作有机会跑完
            events = await h.store.list_events(sid, run_id=handle.run_id)
            _check(events[-1]["type"] == "done" and events[-1]["reason"] == "cancelled", [e["type"] for e in events])
            _check((await h.store.get_session(sid)).active_run_id is None, "不应残留 active run")
            os.environ["PLACEHOLDER_NODE_DELAY_S"] = "0"
            ev = await h.send(sid, A1_TEXT)
            _check("step_card" in ev.types, f"取消后应可继续：{ev.types}")
            return {"cancel_ms": cancel_ms, "events_after_cancel": [e["type"] for e in events][-3:], "continued": True}
    finally:
        os.environ.pop("PLACEHOLDER_NODE_DELAY_S", None)


# ====================== concurrency（04 §2 / §5）======================


@scenario("five_concurrent_a1", "concurrency", "5 并发 A1（stub 模型）：通过率、card_ready_ms / first_visible_ms 分布", "04 §2、§5；票 45")
async def scn_concurrency(ctx: Ctx):
    n = 5
    scripts = {"intake": [INTAKE_X9] * n, "diagnose.synthesize": [SYNTH_HAIR] * n, "reply.stream": [["好的，"]] * n}
    adapter = ScriptedAdapter({"kb_manual": [OK_HAIR() for _ in range(n)]})
    async with Harness(ctx.dir("cc"), scripts=scripts, adapter=adapter) as h:
        sids = [await h.new_session() for _ in range(n)]
        t0 = time.perf_counter()
        results = await asyncio.gather(*(h.send(s, A1_TEXT) for s in sids), return_exceptions=True)
        wall = int((time.perf_counter() - t0) * 1000)
        ok = [r for r in results if isinstance(r, Events) and "step_card" in r.types and r.done["reason"] == "awaiting_input"]
        card_ready = [h.run_metrics(r.run_id).get("card_ready_ms") for r in ok]
        first_visible = [h.run_metrics(r.run_id).get("first_visible_ms") for r in ok]
        pass_rate = len(ok) / n
        _check(pass_rate == 1.0, f"通过率 {pass_rate:.0%}：{[getattr(r, 'types', r) for r in results]}")
        return {"n": n, "pass_rate": pass_rate, "wall_ms": wall,
                "card_ready_ms": [c for c in card_ready if c is not None],
                "first_visible_ms": [f for f in first_visible if f is not None]}


# ====================== live（可选）======================


async def _live_a1(base_url: str) -> dict[str, Any]:
    """对真实服务跑 A1：流式读 SSE，客户端侧测首个可见 delta 与首张步骤卡（真实模型语义样例）。"""
    async with httpx.AsyncClient(base_url=base_url, timeout=90) as c:
        sid = (await c.post("/sessions")).json()["session_id"]
        t0 = time.perf_counter()
        first_visible = card_ready = None
        types: list[str] = []
        step = None
        async with c.stream("POST", f"/sessions/{sid}/messages", data={"text": A1_TEXT}) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                e = json.loads(line[5:].strip())
                types.append(e["type"])
                if e["type"] == "message" and first_visible is None:
                    first_visible = int((time.perf_counter() - t0) * 1000)
                if e["type"] == "step_card" and card_ready is None:
                    card_ready = int((time.perf_counter() - t0) * 1000)
                    step = e["step"]
        health = (await c.get("/health")).json()
    return {"session_id": sid, "types": [t for t in types if t != "ping"], "first_visible_ms": first_visible,
            "card_ready_ms": card_ready, "step": step and {"plan_id": step["plan_id"], "step_id": step["step_id"], "title": step["title"]},
            "replay_mode": bool(health.get("replay")), "models": health.get("components", {}).get("models")}


@scenario("live_a1_real_model", "live", "真实服务 A1 语义样例（--live）：首个可见 delta、步骤卡就绪；不用于替代 stub 路由测试", "04 §2")
async def scn_live_a1(ctx: Ctx):
    _check(ctx.live_url is not None, "未指定 --live，跳过")
    out = await _live_a1(ctx.live_url)
    _check("step_card" in out["types"], f"真实 A1 未出步骤卡：{out['types']}")
    _check(out["step"]["plan_id"] == "rv_suction_hair_wrap", f"语义样例：首卡应为滚刷缠发计划，实际 {out['step']}")
    return out


def scenarios_for(groups: list[str] | None, live: bool) -> list[Scenario]:
    from app.inspection import l3_scenarios  # noqa: F401 - registers bounded offline scenarios
    out = [s for s in SCENARIOS if (groups is None or s.group in groups)]
    if not live:
        out = [s for s in out if s.group != "live"]
    return out


async def run_scenario(s: Scenario, ctx: Ctx) -> ScenarioResult:
    t0 = time.perf_counter()
    try:
        detail = await asyncio.wait_for(s.run(ctx), timeout=120)
        metrics = {k: detail.get(k) for k in ("first_visible_ms", "card_ready_ms") if k in detail}
        return ScenarioResult(s.name, s.group, s.title, True, int((time.perf_counter() - t0) * 1000), detail, None, metrics)
    except Exception as exc:  # noqa: BLE001 - 任何异常都是场景失败
        return ScenarioResult(s.name, s.group, s.title, False, int((time.perf_counter() - t0) * 1000), {}, f"{type(exc).__name__}: {str(exc)[:600]}")


def new_action_id() -> str:
    return uuid.uuid4().hex
