"""Production-shaped context regression; providers are always FakeChatModel."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.context.budget import budget_error, measure_input
from app.context.builder import ContextBudgetExceeded, build_context, estimate_tokens
from app.context.config import ConversationConfig, conversation_config
from app.conversation.answers import conversation_view, render_answer
from app.conversation.business import BusinessContext
from app.conversation.history import ConversationEntry
from app.conversation.interpret import TurnInterpretation, interpret_turn
from app.conversation.summary_cache import extract_summary
from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter, _schema_hint
from app.settings import CONFIG_DIR


def incident_state():
    return json.loads(
        (Path(__file__).parent / "fixtures/conversation/context_budget.json").read_text()
    )


async def test_product_question_after_two_steps_reaches_production_json_model():
    # 会话 d524a2cf43c04f59b79467409343c301：短产品追问被固定状态挤出预算。
    state = incident_state()
    before = copy.deepcopy(state)
    cfg = load_models_config(CONFIG_DIR / "models.yaml")
    fake = FakeChatModel(script=[json.dumps({
        "primary_intent": "order_query",
        "business_reference": {"relation": "issue", "quote": state["text"]},
        "answer_request": {"fields": ["sku"], "quote": state["text"]},
    }, ensure_ascii=False)])
    router = ModelRouter(
        ModelRegistry(cfg, env={"DASHSCOPE_API_KEY": "test"}),
        model_factory=lambda resolved, route: fake,
    )
    meaning, context = await interpret_turn(router, state, lane="domestic")
    assert context["source"] == "model", context
    assert len(fake.calls) == 1
    assert fake.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}
    assert context["omitted_entries"] == 0
    # 护栏按当前实测值设定，留约 40 token 余量；再加解释字段或提示段落会先在这里失败。
    # 2026-09-18：operation_update 的策略说明使 system 从 2413 升到 2555。
    # 2026-09-19：pb_slow_input 故障族与两道判别题使 system 从 2555 升到 2593。
    # 2026-09-26：口述购买日期（context_field=purchase_date 与一句抽取规则）使 system 从 2593 升到 2641。
    # 2026-10-08：product_question 意图两段提示（见 docs/planning/2026-10-08-1921_product-knowledge-consult/）约 +150，
    #   设备安全说明补「噪音大、担心坏掉不算」（63 工单回放 T36 误判 R4）约 +15，system 从 2641 升到 2810。
    # 2026-10-09：R7 请求证据协议与并列维修提示使固定输入实测为 4573；
    # 仅更新固定开销回归阈值，生产输入预算（config/conversation.yaml）与下面的密集历史保护不变。
    assert context["token_breakdown"]["system"] + context["token_breakdown"]["authority"] <= 4630
    assert meaning.answer_request is not None
    assert "ANKER-A1289" in render_answer(meaning.answer_request, conversation_view(state, "issue"))
    assert state == before


def history(rounds: int, text: str = "请继续查询") -> list[ConversationEntry]:
    return [ConversationEntry(
        entry_id=f"{role}-{i}", session_id="capacity", run_id=f"run-{i}",
        kind="message", role=role, first_seq=i * 2 + j + 1, last_seq=i * 2 + j + 1,
        recorded_at="2026-09-17T00:00:00Z", text=text,
    ) for i in range(rounds) for j, role in enumerate(("user", "assistant"))]


@pytest.mark.parametrize("rounds", [30, 100])
@pytest.mark.parametrize("objects", [1, 5])
@pytest.mark.parametrize("input_chars", [7, 4000])
@pytest.mark.parametrize("density", [2, 12])
async def test_dense_context_preserves_required_state(rounds, objects, input_chars, density):
    state = incident_state()
    active = state["active_issue_id"]
    issue = state["issues"][active]
    issue["facts"] = [{
        "fact_id": f"fact-{i}", "kind": "observation", "value": f"现象{i}仍未消失",
        "status": "disputed" if i == 0 else "active", "quote": f"现象{i}仍未消失",
        "source_entry_ids": [f"user-{i}"],
    } for i in range(density)]
    state["steps_executed"] = [{
        "step_id": f"step-{i}", "title": f"检查线缆{i}", "outcome": "cannot_do",
        "instruction": "断开电源后查看接口", "at": state["at"], "evidence_ids": [f"manual-{i}"],
    } for i in range(density)]
    state["risk_cases"] = [{"rule_id": "R4", "status": "active", "quote": "之前冒烟了"}]
    issue["pending"] = {"kind": "step_feedback", "step_id": "step-0"}
    business = BusinessContext()
    for i in range(objects):
        business = business.accept(f"订单 Anker{i:03}", f"user-{i}")
        business = business.remember({"seller": f"商家{i}"}, f"user-{i}")
        if i:
            state["issues"][f"issue-{i}"] = {
                "title": f"设备{i}不启动", "facts": copy.deepcopy(issue["facts"][:2]),
                "device_ref": {"sku": f"device-{i}"},
            }
    state["business_context"] = business.model_dump()
    state["input_id"] = "current"
    state["input_seq"] = rounds * 2 + 1
    state["text"] = "我的产品是哪个" + "字" * (input_chars - 7)
    entries = history(rounds)
    entries.append(ConversationEntry(
        entry_id="current", session_id="capacity", run_id="current-run", kind="message",
        role="user", first_seq=state["input_seq"], last_seq=state["input_seq"],
        recorded_at=state["at"], text=state["text"],
    ))
    state["history"] = [e.as_dict() for e in entries]
    before = copy.deepcopy(state)
    fake = FakeChatModel(script=['{"primary_intent":"order_query"}'])
    router = ModelRouter(
        ModelRegistry(load_models_config(CONFIG_DIR / "models.yaml"), env={"DASHSCOPE_API_KEY": "test"}),
        model_factory=lambda resolved, route: fake,
    )
    _, context = await interpret_turn(router, state, lane="domestic")
    assert context["source"] == "model", context
    assert context["truncation"] is None
    authority = json.loads(context["messages"][1][1].split("\n", 1)[1])
    assert authority["facts"] == issue["facts"]
    assert authority["step_attempts"] == state["steps_executed"]
    assert authority["risks"] == state["risk_cases"]
    assert authority["pending"] == issue["pending"]
    assert len(authority["issue_index"]) == objects
    assert authority["business_subject"]["subjects"] == business.projection()["subjects"]
    assert len(authority["business_subject"]["subjects"]) == objects
    assert (len(context["source_entry_ids"]) - 1) % 2 == 0
    assert context["source_entry_ids"][-1] == "current"
    assert sum(context["token_breakdown"].values()) == context["tokens"]
    assert measure_input(fake.calls[0]["messages"])["text_tokens"] <= conversation_config().input_budget("intake")
    assert state == before


def test_cache_is_optional_but_required_recall_and_risks_are_not():
    entries = history(8)
    state = {"input_seq": 100, "context_revision": 1, "recall_entry_ids": ["user-0", "assistant-0"],
             "risk_cases": [{"rule_id": "R4", "quote": "曾经冒烟"}],
             "history_summary": {"source_context_revision": 1, "through_seq": 10, "text": "字" * 9000}}
    before = copy.deepcopy(state)
    bundle = build_context(entries, state=state, current_input_id="assistant-7", now="now", max_tokens=1800, task="intake")
    assert bundle.omitted_sections == ["historical_excerpts_cache"]
    assert {"user-0", "assistant-0"} <= set(bundle.source_entry_ids)
    assert "曾经冒烟" in bundle.messages[1][1]
    state["risk_cases"][0]["quote"] = "字" * 9000
    with pytest.raises(ContextBudgetExceeded, match="required_content") as exc:
        build_context(entries, state=state, current_input_id="assistant-7", now="now", max_tokens=1800, task="intake")
    assert exc.value.required_tokens > exc.value.max_tokens
    assert state["history_summary"] == before["history_summary"]


def test_summary_pressure_triggers_before_twelve_turns_without_partial_qa():
    entries = history(8)
    assert extract_summary(entries) is None
    cfg = conversation_config()
    # 后 4 轮（8 条）合计越过 intake 预算 × 触发比例：压力按配置计算，预算调整后仍然触发
    pressure = int(cfg.input_budget("intake") * cfg.summary_trigger_ratio / 8) + 1
    for entry in entries[4:]:
        entry.text = "字" * pressure
    result = extract_summary(entries)
    assert result["source_entry_ids"] == [e.entry_id for e in entries[:4]]
    assert result["through_seq"] == 4
    entries[1].status = "aborted"
    result = extract_summary(entries)
    assert "user-0" not in result["source_entry_ids"]


def test_budget_config_validates_task_names_and_bounds():
    cfg = ConversationConfig(input_budgets={"intake": 16000})
    assert cfg.input_budget("intake") == 16000
    assert cfg.input_budget("reply.stream") == cfg.input_budget() == 8000
    for values in ({"input_budgets": {"intkae": 16000}}, {"input_budgets": {"intake": 10}}, {"summary_trigger_ratio": 0}):
        with pytest.raises(ValidationError):
            ConversationConfig.model_validate(values)


@pytest.mark.parametrize("method", ["json_object", "json_schema", "tools"])
async def test_each_provider_window_is_checked_with_schema_and_output(method):
    cfg = load_models_config(CONFIG_DIR / "models.yaml")
    route = cfg.route("intake", "domestic")
    first, second = route.chain[:2]
    route.chain = [first, second]
    cfg.models[first].context_window = 1024
    fake = FakeChatModel(script=['{"primary_intent":"social"}'] if method == "json_object" else [{"primary_intent": "social"}])
    env = {p.api_key_env: "test" for p in cfg.providers.values()}
    router = ModelRouter(ModelRegistry(cfg, env=env), model_factory=lambda resolved, route: fake)
    result = await router.invoke("intake", [("human", "你好")], TurnInterpretation, method=method, lane="domestic", budget_ms=5000)
    assert [(a.alias, a.outcome) for a in result.attempts] == [(first, "skipped"), (second, "ok")]
    assert "model context window" in result.attempts[0].error
    assert len(fake.calls) == 1
    assert all(a.estimated_input_tokens > 1000 for a in result.attempts)


async def test_schema_retry_rechecks_budget_and_fallback_uses_clean_input(monkeypatch):
    cfg = load_models_config(CONFIG_DIR / "models.yaml")
    route = cfg.route("intake", "domestic")
    first, second = route.chain[:2]
    route.chain = [first, second]
    messages = [HumanMessage(content="字" * 1000)]
    cost = measure_input([SystemMessage(content=_schema_hint(TurnInterpretation)), *messages])["text_tokens"]
    monkeypatch.setattr("app.context.budget.conversation_config", lambda: ConversationConfig(input_budgets={"intake": cost + 1}))
    monkeypatch.setattr("app.models.router.conversation_config", lambda: ConversationConfig(input_budgets={"intake": cost + 1}))
    fakes = {first: FakeChatModel(script=["bad json"]), second: FakeChatModel(script=['{"primary_intent":"social"}'])}
    router = ModelRouter(ModelRegistry(cfg, env={p.api_key_env: "test" for p in cfg.providers.values()}), model_factory=lambda resolved, route: fakes[resolved.alias])
    result = await router.invoke("intake", messages, TurnInterpretation, lane="domestic", budget_ms=5000)
    assert [a.outcome for a in result.attempts] == ["schema_error", "skipped", "ok"]
    assert len(fakes[first].calls) == len(fakes[second].calls) == 1
    assert all(a.input_budget == cost + 1 for a in result.attempts)
    assert all("校验" not in m.content for m in fakes[second].calls[0]["messages"])


def test_intake_schema_preserves_null_fields_and_limits_fixed_overhead():
    schema = TurnInterpretation.model_json_schema()
    assert schema["properties"]["primary_intent"]["$ref"] == "#/$defs/Intent"
    assert TurnInterpretation.model_validate({"primary_intent": "social", "history_request": None}).history_request is None
    # 同上：2026-09-18 新增 operation_update（118 token）后由 2462 升到 2519。
    # 2026-10-09：增加有类型的 request_quotes 后实测 2599，保留 51 token 余量。
    # 2026-10-11：增加 search_query_en（英文现象描述只进检索）后实测 2689，保留 51 token 余量。
    assert estimate_tokens(json.dumps(schema, ensure_ascii=False, separators=(",", ":"))) <= 2740
    # 介于默认预算与 intake 预算之间的输入：intake 放得下，其他任务超限（预算以 config/conversation.yaml 为准）
    cfg = conversation_config()
    assert cfg.input_budget("intake") > cfg.input_budget("reply.stream")
    messages = [HumanMessage(content="字" * cfg.input_budget("reply.stream"))]
    spec = load_models_config(CONFIG_DIR / "models.yaml").models["qwen-flash"]
    assert budget_error(messages, spec, task="intake") is None
    assert budget_error(messages, spec, task="reply.stream") is not None


def test_required_recall_evicts_cache_even_when_fixed_content_alone_fits():
    entries = history(3, "字" * 400)
    state = {"input_seq": 100, "history_summary": {
        "source_context_revision": 0, "through_seq": 2, "text": "字" * 600,
    }}
    kwargs = {"current_input_id": "assistant-2", "now": "now", "task": "reply.stream", "max_tokens": 2400}
    without_recall = build_context(entries, state=state, **kwargs)
    assert without_recall.omitted_sections == []
    state["recall_entry_ids"] = ["user-0", "assistant-0"]
    bundle = build_context(entries, state=state, **kwargs)
    assert bundle.omitted_sections == ["historical_excerpts_cache"]
    assert set(state["recall_entry_ids"]) <= set(bundle.source_entry_ids)
    assert bundle.truncation is None


@pytest.mark.parametrize("module", ["app.context.builder", "app.context.config", "app.context.budget", "app.models.router"])
def test_context_imports_do_not_depend_on_pytest_startup_order(module, tmp_path):
    script = tmp_path / "import_check.py"
    script.write_text(f"import {module}\n")
    result = subprocess.run(
        [sys.executable, str(script)], env={**os.environ, "PYTHONPATH": str(CONFIG_DIR.parent / "orchestrator")},
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
