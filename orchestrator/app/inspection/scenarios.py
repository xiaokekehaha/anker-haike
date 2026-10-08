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
from haike_contracts.actions import parse_action

from app.diagnose import should_rewrite
from app.diagnose.config import get_retrieval_config
from app.inspection.harness import (
    A1_PLAN,
    A1_TEXT,
    EMPTY_SCOPE,
    INTAKE_A1,
    NO_MATCH,
    OBS_HAIR,
    OBS_SMOKE,
    OK_A1,
    OK_HAIR,
    REDX,
    SYNTH_A1,
    UNAVAILABLE,
    Events,
    Harness,
    ScriptedAdapter,
    hit,
    rewrite_config,
)
from app.knowledge.adapter import ToolResult
from app.replay.package import ReplayIncompatible, load_package
from app.replay.runtime import versions_now
from app.sessions.clarify import FIXED_QUESTIONS
from app.sessions.manager import RunManager
from app.settings import settings

# A1 = 主办方工单 T11（S1 Pro App 报错 EB1L → 官方 Q&A rv-0481，5 步），见 harness.A1_TEXT
A1_SCRIPTS = {"intake": [INTAKE_A1] * 4, "diagnose.synthesize": [SYNTH_A1] * 4, "reply.stream": [["好的，"], ["好的，"], ["好的，"], ["好的，"]]}
# 没有错误码的扫地机描述：候选只能来自 kb_qa 语义检索（X10 Pro Omni 滚刷缠发 → rv-0272）
HAIR_TEXT = "eufy X10 Pro Omni 扫地机不吸了，滚刷缠了很多头发"
INTAKE_HAIR = {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
               "facts": [{"value": "不吸了", "quote": "$current"}, {"value": "滚刷缠头发", "quote": "$current"}]}
SYNTH_HAIR = {"hypotheses": [{"plan_id": "qa_rv_0272", "confidence": 0.85, "evidence_ids": ["c21"]}]}


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
    async with Harness(ctx.dir("dup"), scripts={"intake": [{**INTAKE_A1, "facts": [{"value": "不吸了", "quote": "$current"}]}], **{k: v for k, v in A1_SCRIPTS.items() if k != "intake"}}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "我的 S1 Pro 不吸了")
        p = h.pending(ev)
        _check(p["kind"] == "select_product", f"应等待产品卡：{p}")
        body = h.select(p, "T2080")
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


@scenario("cannot_do_x3", "boundary", "「无法操作」不计执行、不烧计划，先追问操作限制；请求人工时摘要保留真实反馈", "09 §3.4；票 35 / 39；会话 c9e11 / 7a0077")
async def scn_cannot_do_x3(ctx: Ctx):
    # 原「连续三次无法操作 → R1b」已随操作条件追问（operation_conditions）移除：无法操作是可逆的限制，
    # 不是排障失败；场景名保留以维持巡检目录。
    async with Harness(ctx.dir("cd3"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        last = await h.action(sid, h.feedback(p, "cannot_do"))
        _check(last.status_code == 200, f"cannot_do 失败：{last.headers.get('_body')}")
        _check("step_card" not in last.types and "escalation_summary" not in last.types, f"不应自动换卡或升级：{last.types}")
        st = await h.state(sid)
        _check(st["counters"]["skipped"] == 1 and st["counters"]["executed"] == 0, f"计数器 {st['counters']}")
        _check(not st["steps_executed"] and not st["exhausted_plans"], "无法操作不算已执行、不消耗计划")
        _check(st["substage"] == "await_operation_conditions" and last.text(), f"应追问操作限制：{st['substage']}")
        r = await h.action(sid, h.request_human(version=(await h.snapshot(sid))["version"]))
        summary = r.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R3", f"应 R3 摘要：{r.types}")
        _check([s["feedback"] for s in summary["summary"]["steps"]] == ["cannot_do"], summary["summary"]["steps"])
        return {"counters": st["counters"], "substage": st["substage"], "summary_steps": summary["summary"]["steps"]}


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
    safety = {"primary_intent": "report_problem", "device_relation": "current", "device_safety_assertion": "reported",
              "device_safety_quote": "$current", "facts": [{"value": "烧焦味", "quote": "$current"}]}
    async with Harness(ctx.dir("sf2"), scripts={**A1_SCRIPTS, "intake": [INTAKE_A1, safety]}) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        fb = await h.action(sid, h.feedback(p, "not_solved"))  # 先执行一步，摘要里应带这条记录
        _check(fb.status_code == 200 and h.pending(fb)["kind"] == "step_feedback", "应下发第二张卡")
        n_calls, n_search = len(h.fake.tasks_called), len(h.adapter.calls)
        ev2 = await h.send(sid, "刚才拆的时候闻到烧焦味了")
        stages = [s for s, _ in ev2.progress]
        # 2026-10 起中途补充统一走 intake（语义解释一次）后直接分流，不再有单独的 rediagnose 子阶段
        _check(stages[:1] == ["intake"] and "escalate" in stages and "diagnose" not in stages, f"应 intake → escalate：{ev2.progress}")
        summary = ev2.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R4", "应 R4")
        _check(h.fake.tasks_called[n_calls:] == ["intake"] and len(h.adapter.calls) == n_search, f"R4 只应有一次语义判断、不检索：{h.fake.tasks_called[n_calls:]}")
        _check(len(summary["summary"]["steps"]) == 1, "摘要应含已下发步骤记录")
        return {"rule": "R4", "steps_in_summary": len(summary["summary"]["steps"])}


@scenario("safety_image_observation", "boundary", "图片观察含冒烟 → CP-in R4，不再检索 / 汇总", "09 §1；票 30")
async def scn_safety_image(ctx: Ctx):
    async with Harness(ctx.dir("sf3"), scripts={"intake": [INTAKE_HAIR], "diagnose.vision": [OBS_SMOKE]}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "扫地机 X10 Pro Omni 有点味道", images=1)
        summary = ev.first("escalation_summary")
        _check(summary is not None and summary["summary"]["reason"]["rule_id"] == "R4", f"应 R4：{ev.types}")
        _check("retrieve" not in [s for _, s in ev.progress], "不应检索")
        _check(h.fake.tasks_called == ["intake", "diagnose.vision"], f"模型调用 {h.fake.tasks_called}")
        st = await h.state(sid)
        flag = next(f for f in st["safety_flags"] if f["rule_id"] == "R4")
        _check(flag["source"] == "observation", "标记来源应为图片观察")
        return {"rule": "R4", "source": flag["source"], "model_calls": h.fake.tasks_called}


def _ocr(order_no: str | None, seller: str | None, conf: float) -> dict:
    return {"order_no": order_no, "seller": seller, "purchase_date": "2026-03-15", "amount": None,
            "confidence": {"order_no": conf, "seller": 0.9, "purchase_date": 0.9}, "unreadable": ["amount"]}


async def _to_receipt_card(h: Harness, ocr: dict) -> tuple[str, dict, Events]:
    """A1 → 官方 5 步全部 not_solved（R2）→ SOP 订单质保判断查不到订单 → upload_receipt → 上传凭证图 → OCR → receipt_card。"""
    h.fake.by_task["warranty.receipt_ocr"] = [json.dumps(ocr, ensure_ascii=False)]
    h.fake.by_task.setdefault("intake", []).append(json.dumps({"primary_intent": "supplement", "device_relation": "current"}))
    sid, ev, p = await _a1_to_step_card(h)
    last = ev
    for _ in range(6):
        last = await h.action(sid, h.feedback(p, "not_solved"))
        if h.pending(last)["kind"] != "step_feedback":
            break
        p = h.pending(last)
    _check(h.pending(last)["kind"] == "upload_receipt", f"应等待凭证上传：{h.pending(last)['kind']}")
    up = await h.send(sid, "订单截图", images=1, purpose="receipt")
    card = up.first("receipt_card")
    _check(card is not None and h.pending(up)["kind"] == "confirm_receipt", f"应出凭证确认卡：{up.types}")
    return sid, h.pending(up), up


@scenario("wrong_device_receipt", "boundary", "S1 Pro 扫地机会话上传吸奶器订单（Anker016）→ order_product_mismatch，只列事实不下结论", "09 §5；票 41")
async def scn_wrong_device_receipt(ctx: Ctx):
    async with Harness(ctx.dir("rc1"), scripts=A1_SCRIPTS) as h:
        sid, p, _up = await _to_receipt_card(h, _ocr("Anker016", "任意店铺", 0.95))
        fields = {"order_no": "Anker016", "seller": "任意店铺", "country": None, "purchase_date": "2026-03-15", "amount": None}
        r = await h.action(sid, h.card_action(p, "confirm_receipt", {"fields": fields, "edited": []}))
        _check(r.status_code == 200, r.headers.get("_body"))
        receipt = (await h.state(sid))["receipt"]
        _check(receipt.get("conflicts"), "应记录产品冲突")
        _check(receipt["status"] == "order_product_mismatch", f"status={receipt['status']} reply={r.text()[:120]}")
        _check("质保期内" not in r.text(), f"不得按另一台设备的订单下质保结论：{r.text()[:120]}")
        return {"receipt_status": receipt["status"], "conflicts": receipt.get("conflicts")}


@scenario("low_confidence_order_hit", "boundary", "OCR 低置信订单号恰好命中一张同型号订单（Anker002）→ 未经确认修改不得核实，needs_manual_check", "09 §5；票 41")
async def scn_low_conf_order(ctx: Ctx):
    async with Harness(ctx.dir("rc2"), scripts=A1_SCRIPTS) as h:
        sid, p, up = await _to_receipt_card(h, _ocr("Anker002", "Amazon", 0.5))
        card = up.first("receipt_card")
        _check(card["confidence"]["order_no"] == 0.5, "卡片应带低置信")
        fields = {"order_no": "Anker002", "seller": "Amazon", "country": None, "purchase_date": "2026-03-15", "amount": None}
        r = await h.action(sid, h.card_action(p, "confirm_receipt", {"fields": fields, "edited": []}))
        _check(r.status_code == 200, r.headers.get("_body"))
        receipt = (await h.state(sid))["receipt"]
        _check(receipt["status"] == "needs_manual_check", f"status={receipt['status']} reply={r.text()[:120]}")
        _check("质保期内" not in r.text(), f"低置信未修改不得核实订单：{r.text()[:120]}")
        return {"receipt_status": receipt["status"], "confidence": card["confidence"]["order_no"]}


@scenario("disconnect_refresh_after_feedback", "boundary", "反馈已提交后断网刷新：run 继续、快照可恢复、续接不漏不重、同 action_id 重放", "08 §6–7；票 08 / 23")
async def scn_disconnect_refresh(ctx: Ctx):
    async with Harness(ctx.dir("dc"), scripts=A1_SCRIPTS) as h:
        sid, _ev, p = await _a1_to_step_card(h)
        body = h.feedback(p, "not_solved")
        # 与 HTTP 入口同口径：动作先经契约解析（补默认字段）再入账，重试的 payload 摘要才一致
        handle = await h.manager.start(sid, entry_action=parse_action(body).model_dump(mode="json"))
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


@scenario("weknora_down", "boundary", "WeKnora 断开：tool_call failed，错误码仍由本地官方 Q&A 索引精确命中并出卡", "09 §4；票 28 / 33")
async def scn_weknora_down(ctx: Ctx):
    async with Harness(ctx.dir("wk"), scripts=A1_SCRIPTS, adapter=ScriptedAdapter({}, default=UNAVAILABLE)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, A1_TEXT)
        tools = ev.all("tool_call")
        _check(any(t["status"] == "failed" for t in tools), f"应有 failed tool_call：{tools}")
        card = ev.first("step_card")
        _check(card is not None and card["step"]["plan_id"] == A1_PLAN, f"知识库不可用仍应按错误码出官方步骤：{ev.types}")
        st = await h.state(sid)
        _check(st["knowledge_status"] == "unavailable", st["knowledge_status"])
        _check(st["diagnose_outcome"]["mode"] == "exact_code", st["diagnose_outcome"])
        return {"knowledge_status": st["knowledge_status"], "mode": st["diagnose_outcome"]["mode"], **_metrics(h, ev.run_id)}


@scenario("all_models_down", "boundary", "全部模型不可用：流程降级完成、不崩溃，告警 model_chain_failed 触发", "04 §1；票 11 / 50")
async def scn_all_models_down(ctx: Ctx):
    # 不用 A1（T11 原文）：其 Push 文案「Click to contact customer service」在模型不可用时被规则兜底当成转人工（见报告）
    text = "eufy Omni E28 扫地机不吸了，App 显示 error 3212"
    async with Harness(ctx.dir("md"), fail_all_models=True, adapter=ScriptedAdapter({}, default=NO_MATCH)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, text)
        _check(ev.done["reason"] in ("awaiting_input", "completed"), f"run 应正常结束：{ev.done}")
        _check("error" not in ev.types, f"不应有 error 事件：{ev.types}")
        card = ev.first("step_card")
        _check(card is not None and card["step"]["plan_id"] == "qa_rv_0147",
               f"型号由规则查表确认、错误码由本地官方 Q&A 精确命中 → 仍应出卡：{ev.types}")
        st = await h.state(sid)
        _check(st["product_confirmed"]["sku"] == "T2352", st.get("product_confirmed"))
        if h.alerts.rules["model_chain_failed"].fired_total < 1:
            await h.send(sid, "还是不行")  # 告警按连续失败 ≥ 3 次计：再来一轮语义解释失败
        _check(h.alerts.rules["model_chain_failed"].fired_total >= 1, f"应触发 model_chain_failed 告警：{h.fake.tasks_called}")
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


INTAKE_VAGUE = {"primary_intent": "report_problem", "device_relation": "current", "facts": []}
INTAKE_NO_SUCTION = {"primary_intent": "report_problem", "device_relation": "current", "facts": [{"value": "不吸了", "quote": "$current"}]}


@scenario("vague_input", "routing", "模糊输入「这个又不行了」无上下文 → 追问品类 / 型号，不检索", "09 §1.1；票 24")
async def scn_vague(ctx: Ctx):
    # 语义解释由模型给出（无产品、无现象）；规则兜底认不出「这个又不行了」是报障，那是另一条降级路径
    async with Harness(ctx.dir("vg"), scripts={"intake": [INTAKE_VAGUE]}) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "这个又不行了")
        _check(ev.text() == FIXED_QUESTIONS["product"], ev.text())
        _check(h.adapter.calls == [], "不应检索")
        st = await h.state(sid)
        return {"clarification": st["clarification"], "question": ev.text()}


@scenario("product_ambiguity", "routing", "「S1 Pro 不吸了」→ 产品确认卡两候选（扫地机 T2080 / 吸奶器 T8D04）", "09 §2；票 20 / 21")
async def scn_ambiguity(ctx: Ctx):
    async with Harness(ctx.dir("amb"), no_router=True) as h:
        sid = await h.new_session()
        ev = await h.send(sid, "我的 S1 Pro 不吸了")
        card = ev.first("product_card")
        _check(card is not None and len(card["candidates"]) >= 2, f"应出产品卡：{ev.types}")
        _check(len({c["category"] for c in card["candidates"]}) >= 2, "两候选应属不同品类（扫地机器人 / 吸奶器）")
        return {"candidates": [c["sku"] for c in card["candidates"]], **_metrics(h, ev.run_id)}


@scenario("user_correction_and_stale_button", "routing", "用户纠正型号 → 消歧重新确认；旧卡按序 409（stale_version / stale_card），计数不变", "09 §1.1；票 37 / 23")
async def scn_correction(ctx: Ctx):
    # 重诊后让另一计划排首位：步骤卡 card_id = uuid5(session, plan, step)，同计划同步骤会得到同一张卡（只是版本更新），
    # 换计划才能同时验证 stale_version 与 stale_card 两条 409
    # X10 Pro Omni 滚刷缠发（rv-0272）→ 纠正为 Omni E28：新型号检索命中 E28 的滚刷卡住条目（rv-0189），计划随之更换
    e28_hit = ToolResult("ok", [hit("c22", "Omni E28 has 2112 Error: Roller brush stuck. Check whether the rolling brush is entangled with hair.", doc="rv-0189")], allowed_count=2)
    synth_e28 = {"hypotheses": [{"plan_id": "qa_rv_0189", "confidence": 0.8, "evidence_ids": ["c22"]}]}
    scripts = {**A1_SCRIPTS, "intake": [INTAKE_HAIR, {**REDX, "product_hints": ["Omni E28"]}],
               "diagnose.synthesize": [SYNTH_HAIR, synth_e28]}
    async with Harness(ctx.dir("corr"), scripts=scripts, adapter=ScriptedAdapter({"kb_qa": [OK_HAIR(), e28_hit]})) as h:
        sid = await h.new_session()
        ev1 = await h.send(sid, HAIR_TEXT)
        _check("step_card" in ev1.types, f"首轮应出步骤卡：{ev1.types}")
        p = h.pending(ev1)
        before = await h.state(sid)
        ev2 = await h.send(sid, "说错了，我的是 Omni E28")
        st = await h.state(sid)
        _check(st["product_confirmed"]["sku"] == "T2352", f"应重新确认 Omni E28：{st['product_confirmed']}")
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
    scripts = {"intake": [INTAKE_NO_SUCTION, INTAKE_NO_SUCTION, INTAKE_VAGUE]}
    async with Harness(ctx.dir("r7"), scripts=scripts) as h:
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
        wrong_kind = await h.action(sid, h.card_action(p, "select_product", {"sku": "T2351"}))
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
        "cfg": cfg_on, "per_kb_status": {"kb_qa": "no_match"},
        "allowed_counts": {"kb_qa": 30}, "has_hits": False, "remaining_ms": 20000,
        "quota_used": False, "product_state": "confirmed_sku", "router_available": True,
    }
    rows = {
        "normal_no_match": {},
        "disabled": {"cfg": cfg_on.model_copy(update={"enabled": False})},
        "hits_sufficient": {"has_hits": True, "coverage": "sufficient"},
        "hits_insufficient": {"has_hits": True, "coverage": "insufficient"},
        "hits_assessment_unknown": {"has_hits": True},
        "kb_unavailable": {"per_kb_status": {"kb_qa": "unavailable"}},
        "empty_scope": {"allowed_counts": {"kb_qa": 0}},
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


INTAKE_DEBRIS = {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"], "facts": [{"value": "跑完了地上还是一堆渣", "quote": "$current", "symptom_code": "suction_low"}]}
DEBRIS_TEXT = "eufy X10 Pro Omni 它跑完了，地上还是一堆渣"
# 改写须保留原症状词（「渣」）；中文同义词表已随自建手册删除，不再靠同义映射放行
REWRITE_GOOD = {"query": "扫地机器人 清扫后地上还有渣"}
REWRITE_BAD = {"query": "扫地机器人 清扫后地上还有渣 电机损坏"}  # 新增原因词 → 拒绝
SYNTH_ONE = {"hypotheses": [{"plan_id": "qa_rv_0272", "confidence": 0.7, "evidence_ids": ["c21"]}]}


@scenario("rewrite_decision_table", "rewrite", "改写决策表：十一种上下文的触发 / 跳过原因（充分性取代「有命中即不改写」）", "09 §4.1；票 32")
async def scn_rewrite_table(ctx: Ctx):
    table = _decision_table()
    expect = {"normal_no_match": "triggered", "disabled": "disabled", "hits_sufficient": "sufficient",
              "hits_insufficient": "triggered", "hits_assessment_unknown": "triggered",
              "kb_unavailable": "unavailable", "empty_scope": "empty_scope",
              "unknown_product": "product_state", "quota_used": "quota_used", "router_unavailable": "router_unavailable"}
    for k, v in expect.items():
        _check(table[k] == v, f"{k}: {table[k]} != {v}")
    _check(table["budget_insufficient"].startswith("budget"), table["budget_insufficient"])
    return table


@scenario("rewrite_off_no_call", "rewrite", "开关关闭：真实无命中不调 query.rewrite，一轮即走无候选出口（R5）", "03 §1.4.2；票 32")
async def scn_rewrite_off(ctx: Ctx):
    async with Harness(ctx.dir("rw0"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({}, default=NO_MATCH), retrieval=rewrite_config(False)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check(stats["rewrite_invokes"] == 0 and stats["retrieval_rounds"] == 1, stats)
        _check(stats["decision"]["reason"] == "disabled", stats["decision"])
        # 计划全部来自官方 Q&A 命中：无命中即无候选计划，不再有「品类通用预写计划」可回退
        _check(stats["fallback"] == "escalate" and "step_card" not in ev.types, stats)
        return stats


@scenario("rewrite_on_no_match_rescued", "rewrite", "开关开启：真实无命中 → 一次改写 → 同 scope 第二轮命中 → 计划来自证据", "03 §1.4.2；票 32")
async def scn_rewrite_on_ok(ctx: Ctx):
    async with Harness(ctx.dir("rw1"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "diagnose.synthesize": [SYNTH_ONE], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_qa": [NO_MATCH(), OK_HAIR()]}), retrieval=rewrite_config(True)) as h:
        sid = await h.new_session()
        ev = await h.send(sid, DEBRIS_TEXT)
        st = await h.state(sid)
        stats = _rewrite_stats(st, h, ev)
        _check(stats["rewrite_invokes"] == 1 and stats["retrieval_rounds"] == 2 and stats["rewrite_used"] is True, stats)
        _check(stats["rewrite_result"]["accepted"] is True, stats["rewrite_result"])
        scopes = {(c[2].product_state, c[2].sku) for c in h.adapter.calls}
        _check(scopes == {("confirmed_sku", "T2351")}, f"scope 应不变：{scopes}")
        _check(stats["knowledge_status"] == "ok" and stats["plan"] == "qa_rv_0272", stats)
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


@scenario("rewrite_on_partial_unavailable", "rewrite", "开关开启，知识库 unavailable → 不改写（故障不算正常无命中）", "09 §4.1")
async def scn_rewrite_partial(ctx: Ctx):
    # 2026-10-08 起只有一个库（kb_qa），「一库 no_match 一库 unavailable」退化为整库 unavailable；决策表仍覆盖该原因
    async with Harness(ctx.dir("rw3"), scripts={"intake": [INTAKE_DEBRIS], "query.rewrite": [REWRITE_GOOD], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_qa": [UNAVAILABLE()]}), retrieval=rewrite_config(True)) as h:
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
        _check(stats["fallback"] == "escalate", stats)
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
    d = should_rewrite(cfg=cfg_on, per_kb_status={"kb_qa": "no_match"}, allowed_counts={"kb_qa": 30},
                       has_hits=False, remaining_ms=cfg_on.min_remaining_ms - 1, quota_used=False, product_state="confirmed_sku", router_available=True)
    _check(d.triggered is False and d.reason.startswith("budget"), d)
    return {"reason": d.reason, "min_remaining_ms": cfg_on.min_remaining_ms}


@scenario("rewrite_on_image_contention", "rewrite", "图片补检索与改写共享名额：含图 run 至多两轮检索，不叠加成三轮", "03 §1.4.1 规则 4；票 30 / 32")
async def scn_rewrite_image(ctx: Ctx):
    async with Harness(ctx.dir("rw6"), scripts={"intake": [INTAKE_DEBRIS], "diagnose.vision": [OBS_HAIR], "query.rewrite": [REWRITE_GOOD], "diagnose.synthesize": [SYNTH_ONE], "reply.stream": [["好"]]},
                       adapter=ScriptedAdapter({"kb_qa": [NO_MATCH(), OK_HAIR()]}), retrieval=rewrite_config(True)) as h:
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
    scripts = {"intake": [INTAKE_A1] * n, "diagnose.synthesize": [SYNTH_A1] * n, "reply.stream": [["好的，"]] * n}
    adapter = ScriptedAdapter({"kb_qa": [OK_A1() for _ in range(n)]})
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
    _check(out["step"]["plan_id"] == A1_PLAN, f"语义样例：EB1L 首卡应为官方 Q&A rv-0481，实际 {out['step']}")
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
