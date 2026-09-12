"""票 45：巡检脚本本身的回归——场景可跑、失败能被指出并让退出码非零、报告与 findings 回填。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.inspection import cli
from app.inspection.report import BLOCK_END, BLOCK_START, summarize, update_findings, write_reports
from app.inspection.scenarios import SCENARIOS, Ctx, Scenario, run_scenario, scenarios_for

pytestmark = pytest.mark.usefixtures("mem_runtime")


def test_scenario_catalogue_covers_required_groups_and_names():
    names = {s.name for s in SCENARIOS}
    # 01 §3.3 故障与边界
    for n in ("duplicate_action", "cannot_do_x3", "safety_first_sentence", "safety_mid_text", "safety_image_observation",
              "wrong_device_receipt", "low_confidence_order_hit", "disconnect_refresh_after_feedback", "restart_recovery",
              "weknora_down", "all_models_down", "replay_mismatch"):
        assert n in names, n
    # 09 §1.1 路由
    for n in ("vague_input", "product_ambiguity", "user_correction_and_stale_button", "request_human_anytime",
              "two_clarifications_then_r7", "rejected_actions_do_not_advance"):
        assert n in names, n
    # 改写开关关闭 / 开启
    for n in ("rewrite_off_no_call", "rewrite_on_no_match_rescued", "rewrite_on_empty_scope", "rewrite_on_partial_unavailable",
              "rewrite_on_invalid_candidate", "rewrite_on_second_round_empty", "rewrite_on_budget_insufficient",
              "rewrite_on_image_contention", "late_result_after_cancel"):
        assert n in names, n
    assert "five_concurrent_a1" in names
    assert [s.group for s in scenarios_for(None, live=False)].count("live") == 0
    assert any(s.group == "live" for s in scenarios_for(None, live=True))


@pytest.mark.parametrize("name", ["duplicate_action", "safety_first_sentence", "rewrite_on_no_match_rescued", "five_concurrent_a1", "user_correction_and_stale_button"])
async def test_selected_scenarios_pass_in_process(name, tmp_path):
    s = next(x for x in SCENARIOS if x.name == name)
    r = await run_scenario(s, Ctx(tmp=tmp_path))
    assert r.passed, r.error
    if name == "five_concurrent_a1":
        assert r.detail["pass_rate"] == 1.0 and len(r.detail["card_ready_ms"]) == 5


async def test_failing_scenario_is_reported_with_name_and_error(tmp_path):
    async def boom(ctx):
        raise AssertionError("场景断言失败示例")

    r = await run_scenario(Scenario("demo_fail", "boundary", "demo", boom), Ctx(tmp=tmp_path))
    assert r.passed is False and "场景断言失败示例" in (r.error or "")
    summary = summarize([r], live_url=None, groups=None)
    assert summary["failed"] == ["demo_fail"] and summary["passed"] == 0
    js, md = write_reports(tmp_path / "out", summary, [r])
    assert json.loads(js.read_text())["summary"]["failed"] == ["demo_fail"]
    assert "❌" in md.read_text() and "demo_fail" in md.read_text()


def test_update_findings_block_is_idempotent(tmp_path):
    findings = tmp_path / "findings.md"
    findings.write_text("# 实现阶段发现\n\n## 环境\n- x\n", encoding="utf-8")
    from app.inspection.scenarios import ScenarioResult

    ok = ScenarioResult("a", "boundary", "A", True, 1, {"first_visible_ms": [3], "card_ready_ms": [7]})
    conc = ScenarioResult("five_concurrent_a1", "concurrency", "C", True, 1, {"n": 5, "pass_rate": 1.0, "wall_ms": 9, "card_ready_ms": [1, 2]})
    summary = summarize([ok, conc], live_url=None, groups=None)
    update_findings(summary, [ok, conc], tmp_path / "r.md", findings=findings)
    text1 = findings.read_text(encoding="utf-8")
    assert text1.count(BLOCK_START) == 1 and "可冻结" in text1 and "5 并发通过率 100%" in text1
    bad = ScenarioResult("b", "routing", "B", False, 1, {}, "AssertionError: x")
    update_findings(summarize([ok, bad], live_url=None, groups=None), [ok, bad], tmp_path / "r2.md", findings=findings)
    text2 = findings.read_text(encoding="utf-8")
    assert text2.count(BLOCK_START) == 1 and text2.count(BLOCK_END) == 1
    assert "不可冻结" in text2 and "失败：b" in text2 and "## 环境" in text2


def test_cli_exit_code_and_group_filter(tmp_path, monkeypatch, capsys):
    out = tmp_path / "reports"
    rc = cli.main(["--group", "rewrite", "--no-findings", "--out", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "rewrite_decision_table" in captured.out and "passed" in captured.out
    assert (out / "latest.md").exists()

    async def boom(ctx):
        raise RuntimeError("stub down")

    monkeypatch.setattr("app.inspection.scenarios.SCENARIOS", [Scenario("must_fail", "boundary", "x", boom)])
    rc = cli.main(["--no-findings", "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 1 and "FAILED scenarios: must_fail" in captured.err


def test_default_report_dir_is_under_repo_reports():
    assert cli.DEFAULT_OUT.parts[-2:] == ("reports", "inspection") and Path(cli.DEFAULT_OUT).is_absolute()
