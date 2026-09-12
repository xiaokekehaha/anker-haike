"""票 37：rediagnose 中途补充与纠正（03 §1.2 多轮、§1.4.1 多轮更新规则、08 §4、09 §1.1）。

场景基于票 34 / 35 的 A1 链路：X9 Pro 不吸 → 步骤卡 s1 → 「仍有问题」→ s2 等待反馈时用户改发自由文本。
假 router：fast = intake 任务（首轮 IntakeExtraction，之后为 RediagnoseExtraction 增量），main = synthesize / reply / guide.step。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.intake.rediagnose import merge_symptoms
from app.knowledge.adapter import ToolResult
from app.models.fake import ScriptExhausted
from app.sessions.clarify import FIXED_QUESTIONS
from tests.test_diagnose import INTAKE_X9, NO_MATCH, OK_HAIR, ScriptedAdapter, hit
from tests.test_guide import SYNTH, Session, pending_of
from tests.test_guide import runtime as runtime  # noqa: PLC0414 - 复用票 34 的 fixture


def _redx(**over) -> str:
    base = {
        "emotion_level": "calm",
        "product_hints": [],
        "new_symptoms": [],
        "negated_symptoms": [],
        "wants_human": False,
        "needs_clarification": False,
    }
    return json.dumps({**base, **over}, ensure_ascii=False)


def SKIP():
    """占位：让 guide.step 改写 / disambiguate.clarify 文案这类可选调用失败并走固定回退，不吞掉后面的脚本项。"""
    return ScriptExhausted("optional task skipped")


# main 脚本顺序：synthesize → reply.stream → guide.step(s1) ；反馈后 guide.step(s2)；rediagnose 轮：synthesize → reply → guide.step
def MAIN(second_synth: str = SYNTH) -> list:
    return [SYNTH, ["x"], SKIP(), SKIP(), second_synth, ["y"], SKIP()]


SYNTH_CLOG_FIRST = json.dumps(
    {
        "hypotheses": [
            {"plan_id": "rv_suction_filter_clog", "confidence": 0.8, "evidence_ids": ["c15"]},
            {"plan_id": "rv_suction_hair_wrap", "confidence": 0.5, "evidence_ids": ["c12"]},
        ]
    }
)


def ok_clog() -> ToolResult:
    return ToolResult(
        "ok",
        [
            hit("c15", "manual_rv_v1", "取出滤网清洗", 0.6),
            hit("c12", "manual_rv_v1", "翻转主机取出滚刷，割断缠绕的毛发", 0.3),
        ],
        allowed_count=2,
    )


class ScopedAdapter(ScriptedAdapter):
    """额外记录每次检索的 scope（票 37：纠正型号后 evidence 必须按新 scope 校验）。"""

    def __init__(self, plan):
        super().__init__(plan)
        self.scopes = []

    async def hybrid_search(self, kb, query, top_k, allow):
        self.scopes.append((kb, allow))
        return await super().hybrid_search(kb, query, top_k, allow)


def _adapter(rounds: int = 3, second=ok_clog) -> ScopedAdapter:
    return ScopedAdapter(
        {
            "kb_manual": [OK_HAIR(), *[second() for _ in range(rounds - 1)]],
            "kb_tickets": [NO_MATCH() for _ in range(rounds)],
        }
    )


def _types(events):
    return [e["type"] for e in events]


def _progress(events):
    return [(e["stage"], e.get("substage")) for e in events if e["type"] == "progress"]


def _human_texts(calls) -> list[str]:
    """假模型每次调用的 human 消息文本。"""
    out = []
    for c in calls:
        human = [m for m in c["messages"] if getattr(m, "type", "") == "human"]
        out.append(human[-1].content if human else "")
    return out


async def _to_s2(s: Session) -> tuple[dict, dict]:
    """A1 前半：发文本 → s1 卡；仍有问题 → s2 卡。返回 (s1 pending, s2 pending)。"""
    p1 = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    p2 = pending_of(await s.feedback(p1, "not_solved", note="还是没吸力"))
    return p1, p2


def _rediagnose_action(version: int, **payload) -> dict:
    return {
        "action_id": uuid.uuid4().hex,
        "expected_version": version,
        "kind": "rediagnose",
        "payload": payload,
    }


# ---------------- 单元：增量合并 ----------------


def test_merge_symptoms_incremental_semantics():
    merged, added, removed = merge_symptoms(["不吸了", "滚刷缠头发"], added=["异响"], negated=[])
    assert (merged, added, removed) == (["不吸了", "滚刷缠头发", "异响"], ["异响"], [])
    # 否定只删对得上的旧症状；对不上的否定被忽略（不能凭空撤销）
    merged, added, removed = merge_symptoms(
        ["吸力小", "滚刷缠头发"], added=["异响"], negated=["吸力小", "漏水"]
    )
    assert merged == ["滚刷缠头发", "异响"] and removed == ["吸力小"]
    # 空抽取 = 未提及 = 保持
    assert merge_symptoms(["不吸了"], added=[], negated=[])[0] == ["不吸了"]
    # 重复新增不计为变化
    assert merge_symptoms(["不吸了"], added=["不吸了"], negated=[])[1] == []


# ---------------- 端到端：/messages 在 guide / verify 阶段即 rediagnose ----------------


async def test_supplement_symptom_rediagnoses_and_issues_new_step_card(runtime):
    """排障中补充「其实还有异响」→ 症状增补 → 重新检索 / 汇总 → plans_ranked 变化 → 新步骤卡；
    steps_executed / counters 保留，旧 s2 卡作废（不记反馈、不计数）。（验收项 1、3、9）"""
    adapter = _adapter()
    s, fakes = await runtime(
        fast=[INTAKE_X9, _redx(new_symptoms=["异响"])],
        main=MAIN(SYNTH_CLOG_FIRST),
        adapter=adapter,
    )
    _, p2 = await _to_s2(s)
    before = await s.state()
    assert before["stage"] == "guide" and before["counters"]["executed"] == 1
    plans_before = [p["plan_id"] for p in before["plans_ranked"]]

    ev = await s.send("其实还有异响")
    assert _progress(ev)[0] == ("intake", "rediagnose")
    assert "step_card" in _types(ev) and ev[-1]["reason"] == "awaiting_input"
    st = await s.state()
    assert st["symptoms"] == ["不吸了", "滚刷缠头发", "异响"]
    assert [p["plan_id"] for p in st["plans_ranked"]] != plans_before
    assert st["plans_ranked"][0]["plan_id"] == "rv_suction_filter_clog"
    # 保留：已执行步骤与计数器；作废：旧 s2 卡不算反馈也不计数
    assert st["steps_executed"] == before["steps_executed"] and len(st["steps_executed"]) == 1
    assert st["counters"] == before["counters"]
    assert st["card_results"][p2["card_id"]] == {"superseded": "rediagnose"}
    new_card = next(e for e in ev if e["type"] == "step_card")
    assert new_card["card_id"] != p2["card_id"]
    assert (new_card["step"]["plan_id"], new_card["step"]["step_id"]) not in {
        (x["plan_id"], x["step_id"]) for x in st["steps_executed"]
    }
    assert new_card["step"]["plan_id"] == "rv_suction_filter_clog"
    # query 是产品 + 有效症状（含新增），不是孤立的补充句
    q = adapter.calls[-1][1]
    assert q.startswith("eufy X9 Pro") and "异响" in q and "不吸了" in q and "其实" not in q
    # 抽取上下文带已确认产品 / 有效症状 / 最近步骤（一次 intake 调用）
    human = _human_texts(fakes["fast"].calls)[-1]
    assert "eufy X9 Pro" in human and "滚刷缠头发" in human and "not_solved" in human
    assert "其实还有异响" in human
    # 快照：用户补充进 timeline，旧卡无反馈，新卡 pending
    snap = await s.snap()
    assert [i.text for i in snap.timeline if i.kind == "user_message"][-1] == "其实还有异响"
    assert snap.pending_input.card_id == new_card["card_id"]
    old = next(i for i in snap.timeline if i.kind == "step_card" and i.card_id == p2["card_id"])
    assert old.feedback is None


async def test_deictic_followup_inherits_product_and_unsolved_symptoms(runtime):
    """「还是不吸」不是新故障：不追问，query 承接已确认产品与未解决症状（验收项 5、10）。"""
    adapter = _adapter()
    s, _ = await runtime(fast=[INTAKE_X9, _redx()], main=MAIN(), adapter=adapter)
    await _to_s2(s)
    ev = await s.send("还是不吸")
    assert "step_card" in _types(ev)
    st = await s.state()
    assert st["symptoms"] == ["不吸了", "滚刷缠头发"] and st["clarification"] is None
    q = adapter.calls[-1][1]
    assert q == "eufy X9 Pro 不吸了 滚刷缠头发"


async def test_negation_replaces_symptom_and_synthesize_input_drops_it(runtime):
    """「不是吸力小，是有异响」：被否定的现象从有效症状、query 与 synthesize 输入中移除；原话留在消息记录（验收项 6）。"""
    adapter = _adapter()
    s, fakes = await runtime(
        fast=[INTAKE_X9, _redx(new_symptoms=["异响"], negated_symptoms=["不吸了"])],
        main=MAIN(SYNTH_CLOG_FIRST),
        adapter=adapter,
    )
    await _to_s2(s)
    n_main = len(fakes["main"].calls)
    await s.send("不是吸力小，是有异响")
    st = await s.state()
    assert st["symptoms"] == ["滚刷缠头发", "异响"]
    assert "不吸了" not in adapter.calls[-1][1]
    synth_human = _human_texts(fakes["main"].calls)[n_main]  # 本轮第一次 main 调用 = synthesize
    assert "异响" in synth_human and "症状：滚刷缠头发、异响" in "".join(
        m.content for m in fakes["main"].calls[n_main]["messages"]
    )
    assert [m["text"] for m in st["messages"] if m["role"] == "user"][-1] == "不是吸力小，是有异响"
    # 「还有异响」类补充不删旧现象（对照，见 test_supplement_symptom_...）


async def test_safety_term_in_supplement_escalates_r4_without_model_or_retrieval(runtime):
    """补充文本含安全词 → CP-in R4 直接升级：不调模型、不检索；摘要含已执行步骤（验收项 2、3、9）。"""
    adapter = _adapter()
    s, fakes = await runtime(fast=[INTAKE_X9], main=[SYNTH, ["x"]], adapter=adapter)
    await _to_s2(s)
    n_fast, n_main, n_adapter = len(fakes["fast"].calls), len(fakes["main"].calls), len(adapter.calls)
    ev = await s.send("刚才拆的时候闻到烧焦味了")
    # 安全升级直接摘要（不收集凭证，票 39）；摘要含已执行步骤与规则编号
    assert ev[-1]["reason"] == "completed" and "escalation_summary" in _types(ev)
    summary = next(e for e in ev if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R4"
    assert [x["title"] for x in summary["steps"]] and summary["steps"][0]["feedback"] == "not_solved"
    st = await s.state()
    assert st["escalate_reason"] == "R4" and st["stage"] == "escalate"
    assert len(fakes["fast"].calls) == n_fast and len(fakes["main"].calls) == n_main
    assert len(adapter.calls) == n_adapter
    assert len(st["steps_executed"]) == 1  # 保留，供摘要
    assert st["safety_flags"][-1]["rule_id"] == "R4"


async def test_rediagnose_rejected_while_run_active(runtime, monkeypatch):
    """有 active run 时 rediagnose → 409 run_active 附快照（08 §4 顺序里 run_active 先于其他校验）。"""
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    s, _ = await runtime(fast=[INTAKE_X9, _redx()], main=MAIN(), adapter=_adapter())
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0")
    _, p2 = await _to_s2(s)
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "1.5")
    task = asyncio.create_task(s.send("还是不吸"))
    await asyncio.sleep(0.3)
    r = await s.client.post(
        f"/sessions/{s.sid}/actions", json=_rediagnose_action(p2["version"], text="还有异响")
    )
    assert r.status_code == 409 and r.json()["code"] == "run_active"
    assert r.json()["snapshot"]["active_run"] is not None
    monkeypatch.setenv("PLACEHOLDER_NODE_DELAY_S", "0")
    await task


async def test_rediagnose_action_endpoint_timing_and_validation(runtime):
    """/actions kind=rediagnose：等待步骤卡时 200 并走同一路径；A1 完成后 not_allowed_now；
    空载荷 422；未知 image_ids 422（验收项 4、12）。"""
    adapter = _adapter()
    s, _ = await runtime(
        fast=[INTAKE_X9, _redx(new_symptoms=["异响"])],
        main=MAIN(SYNTH_CLOG_FIRST),
        adapter=adapter,
    )
    _, p2 = await _to_s2(s)
    # 空载荷 → 422，不产生 run
    r = await s.client.post(f"/sessions/{s.sid}/actions", json=_rediagnose_action(p2["version"]))
    assert r.status_code == 422
    r = await s.client.post(
        f"/sessions/{s.sid}/actions", json=_rediagnose_action(p2["version"], image_ids=["nope"])
    )
    assert r.status_code == 422 and "image_ids" in r.json()["detail"]["message"]
    # 版本过旧 → stale_version（先于时机校验）
    r = await s.client.post(
        f"/sessions/{s.sid}/actions", json=_rediagnose_action(p2["version"] - 1, text="还有异响")
    )
    assert r.status_code == 409 and r.json()["code"] == "stale_version"
    # 正常：等待 s2 时补充 → Command(resume) → 旧卡作废 → 新步骤卡
    r = await s.client.post(
        f"/sessions/{s.sid}/actions", json=_rediagnose_action(p2["version"], text="还有异响")
    )
    assert r.status_code == 200 and r.headers["X-Action-Replayed"] == "false"
    from app.sessions import sse

    ev = sse.parse(r.text)
    assert ev[0]["resumed"] is True and _progress(ev)[0] == ("intake", "rediagnose")
    assert "step_card" in _types(ev)
    st = await s.state()
    assert st["card_results"][p2["card_id"]]["superseded"] == "rediagnose"
    assert st["symptoms"][-1] == "异响" and len(st["steps_executed"]) == 1
    # 动作 run 里补充的消息归入本 run（run_id 取当前 run，而不是上一条消息 run），快照 timeline 两条用户消息都在
    assert st["messages"][-1]["run_id"] == ev[0]["run_id"] == st["run_id"]
    snap = await s.snap()
    assert [i.text for i in snap.timeline if i.kind == "user_message"] == [
        "eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发", "还有异响"
    ]
    # 点「已解决」→ done → 之后 rediagnose 不再允许（stage=done，用户应发新消息）
    p3 = pending_of(ev)
    ev2 = await s.feedback(p3, "solved")
    assert ev2[-1]["reason"] == "completed"
    r = await s.client.post(
        f"/sessions/{s.sid}/actions", json=_rediagnose_action(ev2[-1]["version"], text="又不吸了")
    )
    assert r.status_code == 409 and r.json()["code"] == "not_allowed_now"


async def test_product_correction_goes_through_disambiguate_and_invalidates_old_card(runtime):
    """用户纠正型号：先回 disambiguate 重新确认；旧证据清空、新检索按新 scope；旧步骤卡失效，
    再点旧卡按校验顺序返回 409 与快照，业务计数不变（验收项 7、11）。"""
    adapter = _adapter()
    s, _ = await runtime(
        fast=[INTAKE_X9, _redx(product_hints=["X10"])],
        main=MAIN(SYNTH_CLOG_FIRST),
        adapter=adapter,
    )
    _, p2 = await _to_s2(s)
    before = await s.state()
    assert before["product_confirmed"]["sku"] == "EUFY-X9-PRO"
    ev = await s.send("说错了，我的是 X10")
    st = await s.state()
    assert st["product_confirmed"]["sku"].startswith("EUFY-X10") and st["evidence"]
    assert "disambiguate" in [p[0] for p in _progress(ev)]
    # 新 scope：本轮检索的 allow.sku 是新型号；证据全部来自本轮
    _kb, scope = adapter.scopes[-1]
    assert scope.sku == st["product_confirmed"]["sku"] and scope.product_state == "confirmed_sku"
    new_card = next(e for e in ev if e["type"] == "step_card")
    assert set(new_card["step"]["evidence_ids"]) <= set(st["evidence"])
    # 计数与步骤保留
    assert st["counters"] == before["counters"] and st["steps_executed"] == before["steps_executed"]
    # 旧卡：版本已过 → stale_version（校验顺序 version → card），快照带新 pending
    r = await s.client.post(
        f"/sessions/{s.sid}/actions",
        json={
            "action_id": uuid.uuid4().hex,
            "interrupt_id": p2["interrupt_id"],
            "card_id": p2["card_id"],
            "expected_version": p2["version"],
            "kind": "step_feedback",
            "payload": {"feedback": "not_solved"},
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "stale_version"
    assert r.json()["snapshot"]["pending_input"]["card_id"] == new_card["card_id"]
    # 版本对了但卡是旧的 → stale_card；业务计数仍不变
    r = await s.client.post(
        f"/sessions/{s.sid}/actions",
        json={
            "action_id": uuid.uuid4().hex,
            "interrupt_id": p2["interrupt_id"],
            "card_id": p2["card_id"],
            "expected_version": r.json()["snapshot"]["version"],
            "kind": "step_feedback",
            "payload": {"feedback": "not_solved"},
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "stale_card"
    assert (await s.state())["counters"] == before["counters"]


async def test_product_correction_with_multiple_hits_shows_product_card_first(runtime):
    """「说错了，是 S1 Pro」多命中 → 先出产品卡；新确认前不下发旧 SKU 步骤（验收项 7、12）。"""
    s, _ = await runtime(
        fast=[INTAKE_X9, _redx(product_hints=["S1 Pro"])],
        main=MAIN(),
        adapter=_adapter(),
    )
    await _to_s2(s)
    ev = await s.send("说错了，是 S1 Pro")
    assert "product_card" in _types(ev) and "step_card" not in _types(ev)
    st = await s.state()
    assert st["product_confirmed"] is None and st["pending_card"]["kind"] == "select_product"
    assert len(st["steps_executed"]) == 1  # 历史保留


async def test_extraction_failure_keeps_product_and_symptoms(runtime):
    """上下文抽取失败：不清空已确认产品与症状；原文含具体故障描述时按原文回退补一条症状（验收项 8）。"""
    adapter = _adapter()
    s, _ = await runtime(
        fast=[INTAKE_X9, ScriptExhausted("boom")],
        main=MAIN(),
        adapter=adapter,
    )
    await _to_s2(s)
    ev = await s.send("其实还有异响")
    st = await s.state()
    assert st["product_confirmed"]["sku"] == "EUFY-X9-PRO" and st["product_state"] == "confirmed_sku"
    assert st["symptoms"][:2] == ["不吸了", "滚刷缠头发"] and st["symptoms"][-1] == "其实还有异响"
    assert st["model_trace"][-1]["model_used"] == "skipped" or any(
        t.get("model_used") == "skipped" for t in st["model_trace"]
    )
    assert "step_card" in _types(ev)
    assert adapter.calls[-1][1].startswith("eufy X9 Pro 不吸了 滚刷缠头发")


async def test_ambiguous_reference_clarifies_then_r7(runtime):
    """指代无唯一对象（模型标 needs_clarification 且无事实增量）→ 先澄清，不推进；
    连续两次仍不明 → R7，摘要观察说明未知项（验收项 10）。"""
    s, _ = await runtime(
        # 每轮：抽取（redx）→ clarify 文案（disambiguate.clarify 也在 fast 链，SKIP → 固定文案）
        fast=[INTAKE_X9, _redx(needs_clarification=True), SKIP(), _redx(needs_clarification=True), SKIP(),
              _redx(needs_clarification=True)],
        main=MAIN(),
        adapter=_adapter(),
    )
    await _to_s2(s)
    ev1 = await s.send("不是那个，是另一个")
    assert "step_card" not in _types(ev1) and ev1[-1]["reason"] == "completed"
    assert "".join(e["delta"] for e in ev1 if e["type"] == "message") == FIXED_QUESTIONS["symptom"]
    st1 = await s.state()
    assert st1["clarification"]["attempts"] == 1 and st1["steps_executed"]
    ev2 = await s.send("就是另一个")
    assert "".join(e["delta"] for e in ev2 if e["type"] == "message") == FIXED_QUESTIONS["symptom"]
    assert (await s.state())["clarification"]["attempts"] == 2
    ev3 = await s.send("另一个啊")
    st3 = await s.state()
    assert st3["escalate_reason"] == "R7"
    assert any("R7" in o for o in st3["observations"])
    assert "awaiting_input" in _types(ev3) or "escalation_summary" in _types(ev3)


async def test_plain_message_after_completion_is_normal_intake(runtime):
    """A1 完成（stage=done）后再发消息：不是 rediagnose，走常规 intake（新一轮）。"""
    s, _ = await runtime(fast=[INTAKE_X9, INTAKE_X9], main=MAIN(), adapter=_adapter())
    p1 = pending_of(await s.send("eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发"))
    assert (await s.feedback(p1, "solved"))[-1]["reason"] == "completed"
    ev = await s.send("eufy X9 Pro 又不吸了")
    assert _progress(ev)[0] == ("intake", None)


@pytest.mark.parametrize("text", ["拆开后有焦味", "机器冒烟了"])
def test_cp_in_terms_are_rule_r4(text):
    from app.rules import RulesService
    from app.settings import REPO_ROOT

    cp = RulesService(REPO_ROOT / "config" / "rules" / "safety_terms.yaml", hot_reload=False).check_in(
        text=text, session_id="t"
    )
    assert cp.escalate and any(h.rule_id == "R4" for h in cp.hits)
