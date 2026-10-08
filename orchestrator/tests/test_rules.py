"""票 15：规则字典热加载、CP-in 判定、safety_flags 形状、结构化日志、图内不调模型直跳 escalate。"""

from __future__ import annotations

import logging
import os
import re
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.rules import RulesError, RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form

REAL = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


@pytest.fixture
def rules() -> RulesService:
    return RulesService(REAL, hot_reload=False)


def test_dictionary_loads_with_numbered_rules(rules):
    assert {"R3", "R4", "R6"} <= set(rules.rules)
    assert rules.rules["R4"].action == "escalate" and rules.rules["R6"].action == "flag"
    assert next(iter(rules.rules)) == "R4"  # 优先级排序：安全最先


@pytest.mark.parametrize(
    ("text", "rule_ids", "escalate"),
    [
        ("扫地机刚才冒烟了！", ["R4"], True),
        ("底部有一股烧焦的味道", ["R4"], True),
        ("机身有焦味", ["R4"], True),
        ("电池 鼓包 了还能用吗", ["R4"], True),
        ("我要转人工", ["R3"], True),
        ("这个能保修吗", ["R6"], False),
        ("吸力变小了", [], False),
        ("", [], False),
    ],
)
def test_cp_in_text(rules, text, rule_ids, escalate):
    res = rules.check_in(text=text)
    assert res.rule_ids == rule_ids and res.escalate is escalate


def test_cp_in_observations_actions_and_notes(rules):
    res = rules.check_in(observations=["visible smoke near the brush", "dust on filter"])
    assert (
        res.rule_ids == ["R4"]
        and res.hits[0].source == "observation"
        and res.hits[0].term == "smoke"
    )
    res = rules.check_in(action_kind="request_human")
    assert res.rule_ids == ["R3"] and res.hits[0].source == "action" and res.escalate
    res = rules.check_in(action_kind="step_feedback", action_note="按了之后有火花")
    assert res.rule_ids == ["R4"] and res.hits[0].source == "action_note"


def test_safety_flag_shape_and_dedup(rules):
    res = rules.check_in(text="冒烟还起火了，转人工", observations=["smoke"], session_id="s1")
    flags = res.flags
    assert [f["rule_id"] for f in flags] == ["R4", "R4", "R3"]  # R4 文本一条、R4 观察一条、R3
    assert {"rule_id", "source", "term", "ts"} == set(flags[0])
    assert flags[0]["ts"].endswith("+00:00")
    assert res.escalate


def test_rule_hits_are_structured_logs(rules, caplog):
    caplog.set_level(logging.INFO, logger="rules")
    rules.check_in(text="冒烟", session_id="sess-9")
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "rule_hit")
    assert rec.rule_id == "R4" and rec.source == "text" and rec.checkpoint == "cp_in"
    assert rec.session_id == "sess-9" and rec.rules_version == rules.version
    assert "rule_id=R4" in rec.getMessage()


def test_step_warning_is_logged_as_step_drop_not_user_risk(rules, caplog):
    caplog.set_level(logging.INFO, logger="rules")
    result = rules.check_pre_step(instruction="若有焦味请立即关机。", caution=None)
    assert result.action == "drop"
    hits = [r for r in caplog.records if getattr(r, "event", None) == "rule_hit"]
    assert len(hits) == 1
    assert (hits[0].checkpoint, hits[0].source, hits[0].action) == (
        "cp_pre_step", "step", "drop"
    )
    assert hits[0].term == "焦味"


def test_hot_reload_on_file_change(tmp_path):
    p = tmp_path / "safety_terms.yaml"
    p.write_text(REAL.read_text(encoding="utf-8"), encoding="utf-8")
    svc = RulesService(p)
    assert svc.check_in(text="机器会发光").rule_ids == []
    text = p.read_text(encoding="utf-8").replace("text_terms: [冒烟,", "text_terms: [发光, 冒烟,")
    p.write_text(re.sub(r"^version: .*$", "version: hot-reload-test", text, flags=re.MULTILINE), encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))  # 保证 mtime 变化
    assert svc.check_in(text="机器会发光").rule_ids == ["R4"] and svc.version == "hot-reload-test"
    # 改坏文件：保留旧字典继续工作
    p.write_text("version: [", encoding="utf-8")
    os.utime(p, (time.time() + 10, time.time() + 10))
    assert svc.check_in(text="机器会发光").rule_ids == ["R4"]


def test_bad_config_errors(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("version: x\nrules: {bogus: {name: n, action: escalate}}\n", encoding="utf-8")
    with pytest.raises(RulesError, match="bad rule ids"):
        RulesService(p)
    with pytest.raises(RulesError, match="not found"):
        RulesService(tmp_path / "none.yaml")


# ---- 图内：首句含安全词 → 不进入任何模型节点，直接 escalate ----


from typing import ClassVar


class _ForbiddenRouter:
    calls: ClassVar[list] = []

    async def invoke(self, *a, **k):
        self.calls.append((a, k))
        raise AssertionError("model must not be called after CP-in hit")

    stream = invoke


async def test_first_message_with_safety_term_skips_models(mem_runtime, monkeypatch):
    set_rules_service(RulesService(REAL, hot_reload=False))
    app.state.model_router = _ForbiddenRouter()  # 假 router：任何调用即失败
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            resp = await client.post(
                f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "扫地机充电时冒烟了，怎么办"})
            )
            events = sse.parse(resp.text)
            snap = (await client.get(f"/sessions/{sid}")).json()
    finally:
        set_rules_service(None)
        app.state.model_router = None
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["intake", "escalate"]  # 没有 diagnose：reply 及之后的模型节点未执行
    assert events[-1]["type"] == "done" and events[-1]["reason"] == "completed"
    assert _ForbiddenRouter.calls == []
    assert snap["stage"] == "escalate" and snap["substage"] == "summarize"
    state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
    flags = state.values["safety_flags"]
    assert flags[0]["rule_id"] == "R4" and flags[0]["source"] == "text" and flags[0]["ts"]
    assert state.values["escalate_reason"] == "R4"


async def test_normal_message_still_goes_to_reply(mem_runtime):
    set_rules_service(RulesService(REAL, hot_reload=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            resp = await client.post(
                f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": "扫地机 X10 吸力变小了"})
            )
    finally:
        set_rules_service(None)
    events = sse.parse(resp.text)
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages[:2] == ["intake", "disambiguate"] and "diagnose" in stages
    assert "escalate" not in stages and all(e["type"] != "escalation_summary" for e in events)


# ---- 否定语义（2026-09-16）：视觉模型会写「未见冒烟烧焦鼓包漏液火花」这类否定清单，
# 子串匹配把它当成风险事实，正常的滚刷缠绕照片会被误升级 R4 并终止排障。----


@pytest.mark.parametrize(
    "observation",
    [
        "未见冒烟烧焦鼓包漏液火花",  # 实测样本：data/demo-photos/1_滚刷缠绕_正常曝光.png
        "未见明显冒烟",
        "无冒烟、烧焦迹象",
        "没有漏液",
        "滚刷无鼓包",
        "no smoke or burning smell",
        "no signs of swollen battery",
    ],
)
def test_cp_in_observation_negated_safety_terms_do_not_escalate(rules, observation):
    res = rules.check_in(observations=[observation])
    assert res.rule_ids == [] and not res.escalate, res.flags


@pytest.mark.parametrize(
    "observation",
    [
        "未见冒烟，滚刷烧焦",  # 否定只管到标点为止
        "无线充电座冒烟",  # 「无」后面不是安全词串，不是否定
        "没有办法关机，机身冒烟",
        "未见冒烟但有火花",
        "visible smoke near the brush",
        "battery swollen, no leaking",
        "滚刷烧焦",
    ],
)
def test_cp_in_observation_real_safety_terms_still_escalate(rules, observation):
    res = rules.check_in(observations=[observation])
    assert res.rule_ids == ["R4"] and res.escalate, observation


@pytest.mark.parametrize(
    ("text", "rule_ids"),
    [
        ("没有焦味", []),
        ("机器不冒烟，就是吸力小", []),
        ("未见鼓包", []),
        ("没有异味但有火花", ["R4"]),  # 否定只遮住紧邻的那个词
        ("没有办法关机，机器冒烟了", ["R4"]),
        ("不小心闻到焦味", ["R4"]),
    ],
)
def test_cp_in_text_negated_safety_terms(rules, text, rule_ids):
    res = rules.check_in(text=text)
    assert res.rule_ids == rule_ids, text
