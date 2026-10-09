"""63 单主办方工单的真实链路回放（D1b）：对运行中的编排服务逐单发首封消息，按固定的「客户策略」应答卡片，
统计 plan.md §4 的指标。

与 tickets.py（确定性评测，不调模型）互补：这里走真实模型与知识库，测的是整条会话。

客户策略（模拟一个「问题没解决、愿意配合提交材料」的客户，让每单都能走到 SOP 终点）：
- 产品卡：按工单的 PN / 品类选；选不出选第一个；
- 步骤卡：一律「还没解决」（最多 MAX_STEPS 张），以走到质保 / 服务单分支；期望 explain 的单答「解决了」；
- 方案卡：确认第一个方案；
- 凭证上传：跳过（reason=none）；凭证确认：原样确认；
- 文字追问证据（照片 / SN / 地址）：上传真实设备故障照（见 fault_photos）或回复「SN: …」与订单地址；
- 评价卡：给 5 分后结束。

指标：
- 意图准确率：首轮 understand 节点的 primary_intent 与标注 intent 一致；
- SOP 分支准确率：会话到达的终点覆盖标注 sop（多诉求单还要覆盖 sop_also；转人工只认案件状态与交接记录，见 terminals_of）；
- 机器人闭环率 bot_closed_rate：期望终点为机器人可独立闭环的工单（BOT_CLOSABLE）中，未触发转人工即结束的比例。
  驱动策略对步骤一律答「还没解决」，故障单按设计会走到质保 / 转人工，不计入分母（2026-10-08 Fable 5.1 裁定）；
  「提交服务单后转人工」是 SOP 规定终点，单列 service_order_submitted；
- 幻觉：客户可见文字出现标注的禁止承诺（forbid）或未收录码被当成已知码处理（code_miss 单出现步骤卡）。
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.official.message import parse_message
from app.official.models import OfficialData, pn_of
from app.settings import REPO_ROOT

CASES = REPO_ROOT / "data" / "eval" / "tickets" / "cases.yaml"
BOT_CLOSABLE = {"logistics_in_transit", "logistics_presale", "out_of_warranty", "explain"}
MAX_STEPS = 12  # 最长的官方指南 11 步（bp-0123），要能走完才到质保分支
MAX_TURNS = 20
TIMEOUT_S = 90.0

# 禁止承诺：客户可见文字里出现即记幻觉（英文为主，兼容中文固定话术）
FORBID_PATTERNS = {
    "reship": re.compile(r"reship|resend|send (you )?a (new|replacement) (package|parcel)|补发", re.IGNORECASE),
    "free_replacement": re.compile(r"free (replacement|repair)|replace (it )?for free|免费(换货|更换|维修)", re.IGNORECASE),
    "neighbour_code": re.compile(r"\bstep\b.*\b5116\b", re.IGNORECASE),
}
NEGATION = re.compile(r"不再|无法|不能|不会|不提供|no longer|cannot|can't|unable|not eligible|won't|will not|is not", re.IGNORECASE)
SENTENCE = re.compile(r"[^。！？.!?\n]+")


def promised(pattern: re.Pattern, text: str) -> bool:
    """按句判断：句子里出现承诺词且没有否定词才算承诺（「按售后规则不再补发」不是补发承诺）。"""
    return any(pattern.search(s) and not NEGATION.search(s) for s in SENTENCE.findall(text))


TIMELINE_PROMISE = re.compile(r"within \d+ (business |working )?days|\d+ ?个?工作日(内)?(发出|送达|到账)", re.IGNORECASE)


def intent_of(journey: dict[str, Any]) -> str | None:
    """首个 run 的 understand 节点记录的 primary_intent。"""
    for run in journey.get("runs") or []:
        for node in run.get("nodes") or []:
            intent = (node.get("summary") or {}).get("primary_intent")
            if node.get("node") == "understand" and intent:
                return intent
    return None


# 本系统办不了、只能转人工的诉求（暂缓发货 / 取消 / 改购 / 改地址），见 app.conversation.tasks.NOT_EXECUTABLE
HANDOFF_REQUESTS = {"order_change", "address_update"}


def terminals_of(snapshot: dict[str, Any], *, case_status: str | None, review_requested: str | None, handoff: bool,
                 escalate_reasons: list[str], service_types: list[str], step_cards: int, said: str,
                 has_code: bool = False) -> list[str]:
    """会话到达的终点（评测集 sop 标签），可能不止一个：多诉求单每项诉求各有终点。

    转人工终点只认持久化证据：案件已进人工队列、记录了该诉求、写了交接摘要。
    「passed your request to」这句话不是证据 —— 2026-10-09 T9 三次复测都说了这句，案件却仍 open、无交接。
    """
    reached: list[str] = []
    if case_status == "awaiting_approval" and review_requested in HANDOFF_REQUESTS and handoff:
        reached.append("order_change_human")
    return reached + [_terminal_of(snapshot, case_status=case_status, escalate_reasons=escalate_reasons,
                                   service_types=service_types, step_cards=step_cards, said=said, has_code=has_code)]


def sop_passed(case: dict[str, Any], reached: list[str]) -> bool:
    """标注 sop 与 sop_also 的每个终点都要到达；单终点单沿用 ACCEPT 的等价集合。"""
    required = [case["sop"], *(case.get("sop_also") or [])]
    return all(set(reached) & ACCEPT.get(sop, {sop}) for sop in required)


def _terminal_of(snapshot: dict[str, Any], *, case_status: str | None, escalate_reasons: list[str],
                 service_types: list[str], step_cards: int, said: str, has_code: bool = False) -> str:
    if "R4" in escalate_reasons:
        return "safety_human"
    if "carrier_investigation" in service_types:
        return "logistics_delivered"
    if "reship" in service_types:
        return "logistics_reship"
    if {"replace", "refund"} & set(service_types):
        return "warranty_replace"
    low = said.casefold()
    if "超过质保期" in said or "out of warranty" in low or "warranty has expired" in low:
        return "out_of_warranty"
    if "授权经销商" in said or "authorized" in low and "dealer" in low:
        return "dealer_check"
    if "预售" in said or "pre-order" in low or "presale" in low:
        return "logistics_presale"
    if "运输途中" in said or "in transit" in low:
        return "logistics_in_transit"
    if "R5" in escalate_reasons and step_cards == 0 and has_code:
        return "code_miss"
    if "R5" in escalate_reasons and step_cards == 0:
        return "no_guidance"
    if step_cards:
        return "troubleshoot"
    if "订单号" in said or "order number" in low:
        return "ask_order"
    if "R7" in escalate_reasons or snapshot.get("stage") in {"disambiguate", "intake"}:
        return "clarify"
    return "explain"


# 标注 sop 与终点的对应：troubleshoot 单走完「还没解决」后会进入质保分支，所以接受质保类终点
ACCEPT = {
    "troubleshoot": {"troubleshoot", "warranty_replace", "out_of_warranty", "dealer_check", "ask_order"},
    "warranty_by_qa": {"warranty_replace", "out_of_warranty", "dealer_check", "ask_order"},
    "warranty_replace": {"warranty_replace"},
    "out_of_warranty": {"out_of_warranty"},
    "logistics_delivered": {"logistics_delivered"},
    "logistics_reship": {"logistics_reship"},
    "logistics_presale": {"logistics_presale"},
    "logistics_in_transit": {"logistics_in_transit"},
    "ask_order": {"ask_order", "clarify"},
    "code_miss": {"code_miss"},
    "safety_human": {"safety_human"},
    "dealer_check": {"dealer_check", "ask_order"},
    "clarify": {"clarify", "explain", "no_guidance"},
    "order_change_human": {"order_change_human"},
    "explain": {"explain", "troubleshoot", "clarify"},
}
# 业务意图分组：解释器的细粒度意图归到标注口径
def intents_accepted(case: dict[str, Any]) -> set[str]:
    """这一单可以接受的意图。多诉求工单允许标注第二个意图（intent_alt）。

    T9 一句话里既问发货日（logistics_query）又要求暂缓发货（order_change）：模型先读到哪个都算对，
    因为队列会按优先级重排；终点则两项都必须到达（sop + sop_also），见 sop_passed。
    """
    return {case["intent"], *([case["intent_alt"]] if case.get("intent_alt") else [])}


INTENT_GROUP = {
    "report_problem": "report_problem", "complaint": "complaint", "supplement": "report_problem",
    "logistics_query": "logistics_query", "order_query": "order_query", "warranty_query": "report_problem",
    "replacement_request": "replacement_request", "refund_request": "replacement_request",
    "product_question": "report_problem", "explain": "report_problem",
}


# 工单原附件里哪些其实是单据截图而不是故障照片（订单摘要 / 发票 / 配送详情 / App 界面）。
# 客户被追问「故障照片或视频」时不能拿这些充数 —— 系统按读图定性排除它们（见 app.sessions.evidence），
# 驱动若继续回传同一张单据，等于替系统假装证据已补齐。
# 这些单的真实客户会另拍一张设备照，所以这里改送同品类的真实故障照。
DOCUMENT_ATTACHMENTS = {"T38.jpg", "T45.jpg", "T46.jpg", "T53.jpg", "T55.jpg"}
# 按品类挑一张真实设备故障照（都是主办方原始附件，不是合成图）
FAULT_PHOTO_BY_LINE = {
    "breast_pump": "T48.jpg",   # 吸奶器主机，外壳有裂纹
    "robot_vacuum": "T14.jpg",  # 扫地机主机与基站
}


def fault_photos(data: OfficialData, ticket) -> list[Path]:
    """客户被追问故障照片时实际会上传的图。

    工单自带的若是单据截图就换成同品类的真实设备照：评测要测的是「证据齐全后能否提交」，
    不是「能否用一张订单截图蒙混过关」。
    """
    usable = [a for a in ticket.attachments if a not in DOCUMENT_ATTACHMENTS]
    if usable:
        return [data.attachment(a) for a in usable]
    line = (ticket.sku and pn_of(ticket.sku) or "").upper()
    name = FAULT_PHOTO_BY_LINE.get(
        "breast_pump" if line.startswith("T8D") else "robot_vacuum"
    )
    return [data.attachment(name)] if name else []


class Driver:
    def __init__(self, client: httpx.AsyncClient, data: OfficialData):
        self.client = client
        self.data = data

    async def snapshot(self, sid: str) -> dict[str, Any]:
        return (await self.client.get(f"/sessions/{sid}")).json()

    async def _events(self, resp: httpx.Response) -> list[dict[str, Any]]:
        return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]

    async def send(self, sid: str, text: str, images: list[Path] = (), purpose: str = "fault") -> list[dict[str, Any]]:
        snap = await self.snapshot(sid)
        files = [("images", (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/jpeg")) for p in images]
        data = {"input_id": uuid.uuid4().hex, "expected_version": str(snap["version"]), "text": text,
                "purpose": purpose, "evaluation_source": "replay"}
        resp = await self.client.post(f"/sessions/{sid}/messages", data=data, files=files or None)
        return await self._events(resp)

    async def act(self, sid: str, kind: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        snap = await self.snapshot(sid)
        pending = snap["pending_input"]
        body = {"action_id": uuid.uuid4().hex, "expected_version": snap["version"],
                "target_issue_id": snap["active_issue_id"], "card_id": pending["card_id"],
                "input_token": pending["input_token"], "kind": kind, "payload": payload}
        return await self._events(await self.client.post(f"/sessions/{sid}/actions", json=body))


async def journey_of(client: httpx.AsyncClient, sid: str) -> dict[str, Any]:
    """观测事实每秒批量落库（analytics flush_ms=1000）：等到首轮 understand 节点出现再读，最多 5 秒。"""
    journey: dict[str, Any] = {}
    for _ in range(10):
        await asyncio.sleep(0.5)
        resp = await client.get(f"/admin/api/sessions/{sid}/journey")
        if resp.status_code == 200:
            journey = resp.json()
            if intent_of(journey):
                return journey
    return journey


def said_of(events: list[dict[str, Any]]) -> str:
    return "".join(e.get("delta", "") for e in events if e.get("type") == "message")


def card_of(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next((e for e in reversed(events) if e.get("type") == kind), None)


async def case_of(client: httpx.AsyncClient, events: list[dict[str, Any]]) -> dict[str, Any]:
    """案件详情（状态、事件、交接摘要）：转人工的判定依据，不看话术。没有案件时返回空。"""
    changed = card_of(events, "case_changed")
    if not changed:
        return {}
    resp = await client.get(f"/admin/api/cases/{changed['case_id']}")
    return resp.json() if resp.status_code == 200 else {}


async def run_case(driver: Driver, case: dict[str, Any], ticket, order_address: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    sid = (await driver.client.post("/sessions")).json()["session_id"]
    # 首封按工单原样发（含单据截图：这正是真实前端的默认路径，要让它一直压在回归上）；
    # 后续被追问「故障照片」时才换成真实设备照，见 fault_photos。
    images = [driver.data.attachment(name) for name in ticket.attachments]
    retake = fault_photos(driver.data, ticket)
    parsed = parse_message(ticket.body)
    events = await driver.send(sid, ticket.body, images)
    transcript = list(events)
    step_cards = sum(1 for e in events if e.get("type") == "step_card")
    supplied: set[str] = set()
    for _ in range(MAX_TURNS):
        snap = await driver.snapshot(sid)
        pending = snap.get("pending_input")
        said = said_of(events)
        if pending:
            kind = pending["kind"]
            if kind == "step_feedback":
                if step_cards > MAX_STEPS:
                    break
                # 期望「解释即结束」的单（正常提示类，如清水不足 / 低电回充）：客户看到说明就满意
                feedback = "solved" if case["sop"] == "explain" else "not_solved"
                events = await driver.act(sid, "step_feedback", {"feedback": feedback})
            elif kind == "select_product":
                card = card_of(transcript, "product_card") or {}
                cands = card.get("candidates") or []
                pn = parsed.pn or (pn_of(ticket.sku) if ticket.sku else None)
                pick = next((c["sku"] for c in cands if c["sku"] == pn), None) or next(
                    (c["sku"] for c in cands if ticket.product_line.lower().startswith(c.get("category", "")[:5])), None
                ) or (cands[0]["sku"] if cands else None)
                events = await driver.act(sid, "select_product", {"sku": pick})
            elif kind == "confirm_proposal":
                card = card_of(transcript, "proposal_card") or {}
                options = card.get("options") or [{"option_id": "replace"}]
                events = await driver.act(sid, "confirm_proposal", {"option_id": options[0]["option_id"]})
            elif kind == "upload_receipt":
                events = await driver.act(sid, "skip_receipt", {"reason": "none"})
            elif kind == "confirm_receipt":
                card = card_of(transcript, "receipt_card") or {}
                events = await driver.act(sid, "confirm_receipt", {"fields": card.get("fields") or {}, "edited": []})
            elif kind == "upload_retake":
                events = await driver.act(sid, "skip_retake", {})
            elif kind == "rate_satisfaction":
                events = await driver.act(sid, "rate_satisfaction", {"score": 5})
                transcript += events
                break
            else:
                break
        else:
            # 文字追问：按 SOP 证据补齐一次；其余情况结束
            low = said.casefold()
            reply = None
            if ("照片" in said or "photo" in low or "video" in low) and "photo" not in supplied and retake:
                supplied.add("photo")
                events = await driver.send(sid, "Here are photos of the problem.", retake)
                transcript += events
                step_cards += sum(1 for e in events if e.get("type") == "step_card")
                continue
            if ("SN" in said or "serial" in low) and "sn" not in supplied:
                supplied.add("sn")
                reply = f"SN: {parsed.sn or 'T8D04121ABCD0001'}"
            elif ("地址" in said or "address" in low) and "address" not in supplied and order_address:
                supplied.add("address")
                reply = f"My shipping address: {' '.join(order_address.split())}"
            elif ("订单号" in said or "order number" in low) and "order" not in supplied and ticket.order_no:
                supplied.add("order")
                reply = f"My order number is {ticket.order_no}"
            if reply is None:
                break
            events = await driver.send(sid, reply)
        transcript += events
        step_cards += sum(1 for e in events if e.get("type") == "step_card")
    journey = await journey_of(driver.client, sid)
    snapshot = journey.get("snapshot") or await driver.snapshot(sid)
    reasons = [
        e["summary"]["reason"]["rule_id"] for e in transcript if e.get("type") == "escalation_summary"
    ] + [r for r in [(journey.get("session") or {}).get("outcome_reason")] if r]
    receipts = [e for e in transcript if e.get("type") == "execution_card"]
    service_types = []
    for r in receipts:
        proposal = card_of(transcript, "proposal_card") or {}
        service_types += [o["type"] for o in proposal.get("options") or []]
    if not receipts:
        proposal = card_of(transcript, "proposal_card")
        service_types = [o["type"] for o in (proposal or {}).get("options") or []]
    visible = said_of(transcript)
    detail = await case_of(driver.client, transcript)
    case_events = detail.get("events") or []
    reached = terminals_of(
        snapshot, case_status=detail.get("status"),
        review_requested=next((e["payload"]["requested"] for e in reversed(case_events)
                               if e["type"] in {"review_requested", "request_changed"}), None),
        handoff=detail.get("handoff_summary") is not None,
        escalate_reasons=reasons, service_types=service_types,
        step_cards=step_cards, said=visible, has_code=bool(parsed.codes),
    )
    forbid_hits = [k for k in case.get("forbid") or [] if FORBID_PATTERNS.get(k) and promised(FORBID_PATTERNS[k], visible)]
    if TIMELINE_PROMISE.search(visible):
        forbid_hits.append("timeline_promise")
    if case["sop"] == "code_miss" and step_cards:
        forbid_hits.append("code_miss_got_steps")
    human = bool(reasons and set(reasons) & {"R3", "R4", "R5", "R6", "R7", "R1", "R1b", "R1c", "R2"}) or bool(receipts)
    intent = intent_of(journey)
    return {
        "id": case["id"],
        "session_id": sid,
        "language": case.get("language"),
        "intent_expected": case["intent"],
        "intent_actual": intent,
        "intent_ok": INTENT_GROUP.get(intent or "", intent) in intents_accepted(case),
        "sop_expected": case["sop"],
        "bot_closable": case["sop"] in BOT_CLOSABLE,
        "sop_also": case.get("sop_also") or [],
        "terminal": " + ".join(reached),
        "sop_ok": sop_passed(case, reached),
        "service_order": bool(receipts),
        "human": human,
        "self_served": not human,
        "step_cards": step_cards,
        "escalate_reasons": reasons,
        "hallucination": forbid_hits,
        "first_reply": said_of(transcript)[:300],
        "seconds": round(time.perf_counter() - started, 1),
    }


def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.0f}%" if b else "n/a"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    ok_rows = [r for r in rows if not r.get("error")]
    service = [r for r in ok_rows if r["service_order"]]
    closable = [r for r in ok_rows if r["bot_closable"]]
    return {
        "cases": n,
        "errors": n - len(ok_rows),
        "intent_accuracy": pct(sum(r["intent_ok"] for r in ok_rows), len(ok_rows)),
        "sop_accuracy": pct(sum(r["sop_ok"] for r in ok_rows), len(ok_rows)),
        # 把 sop_accuracy 拆开：完全命中标注终点的，与走了 ACCEPT 里替代终点的。
        # 只看合计会把「没走错路」读成「回答正确」——ACCEPT 刻意接受多个终点
        # （排障单走完「还没解决」必然进质保分支，驱动策略使然），这部分不能算作答对内容。
        "sop_exact": pct(sum(r["terminal"] == r["sop_expected"] for r in ok_rows), len(ok_rows)),
        "sop_via_alternate": sum(r["sop_ok"] and r["terminal"] != r["sop_expected"] for r in ok_rows),
        "bot_closed_rate": f"{pct(sum(r['self_served'] for r in closable), len(closable))} ({sum(r['self_served'] for r in closable)}/{len(closable)})",
        "service_order_submitted": len(service),
        "hallucination_cases": sum(bool(r["hallucination"]) for r in ok_rows),
        "median_seconds": sorted(r["seconds"] for r in ok_rows)[len(ok_rows) // 2] if ok_rows else None,
    }


def render(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [f"# 63 单真实链路回放（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}）", "",
             "客户策略与指标口径见 orchestrator/app/evaluation/live_tickets.py。机器人闭环率只统计期望终点可由机器人独立闭环的工单（物流运输中、预售、过保告知、解释）。", "",
             "**这些数字证明的是「没走错 SOP 分支」，不是「回答内容正确」。**",
             "- `sop_accuracy` 含 ACCEPT 表里的替代终点（排障单走完「还没解决」必然进质保分支，是驱动策略使然）；",
             f"  其中完全命中标注终点 `sop_exact` = {summary.get('sop_exact')}，经替代终点通过 {summary.get('sop_via_alternate')} 单。",
             "- `hallucination` 只检查标注的禁止承诺与未收录错误码，不校验事实（日期、单号、金额）是否正确。",
             "- 回答质量需人工逐条核对；两者结论曾经不一致，见 docs/planning/2026-10-09-0841_finals-tracking/。", "",
             "| 指标 | 值 |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in summary.items()]
    lines += ["", "| id | 语言 | 意图 期望 / 实际 | SOP 期望 → 终点 | 步骤卡 | 服务单 | 转人工原因 | 幻觉 | 秒 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if r.get("error"):
            lines.append(f"| {r['id']} | | 出错：{r['error'][:80]} | | | | | | |")
            continue
        lines.append(
            f"| {r['id']} | {r['language']} | {'✓' if r['intent_ok'] else '✗'} {r['intent_expected']} / {r['intent_actual']} "
            f"| {'✓' if r['sop_ok'] else '✗'} {' + '.join([r['sop_expected'], *r['sop_also']])} → {r['terminal']} | {r['step_cards']} "
            f"| {'是' if r['service_order'] else ''} | {','.join(dict.fromkeys(r['escalate_reasons']))} "
            f"| {','.join(r['hallucination'])} | {r['seconds']} |"
        )
    return "\n".join(lines) + "\n"


async def run_live(base_url: str, ids: list[str] | None, concurrency: int, out_dir: Path) -> dict[str, Any]:
    data = OfficialData()
    tickets = {t.id: t for t in data.tickets}
    addresses = {o.order_no: o.address for o in data.orders}
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    if ids:
        cases = [c for c in cases if c["id"] in set(ids)]
    gate = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT_S) as client:
        driver = Driver(client, data)

        async def one(case):
            async with gate:
                ticket = tickets[case["id"]]
                try:
                    return await run_case(driver, case, ticket, addresses.get(ticket.order_no or ""))
                except Exception as exc:  # noqa: BLE001 - 单个工单失败不能中断整批，原样记进报告
                    return {"id": case["id"], "error": f"{type(exc).__name__}: {exc}"}

        rows = await asyncio.gather(*(one(c) for c in cases))
    summary = summarize(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"{stamp}_live_tickets.md").write_text(render(summary, rows), encoding="utf-8")
    (out_dir / f"{stamp}_live_tickets.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {"summary": summary, "report": str(out_dir / f"{stamp}_live_tickets.md")}
