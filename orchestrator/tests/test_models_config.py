"""票 09：models.yaml 加载、校验、通道切换、路由表。"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from app.models.config import KNOWN_TASKS, ConfigError, load_models_config
from app.models.route_table import HEADER, render_route_table
from app.settings import REPO_ROOT

REAL_CONFIG = REPO_ROOT / "config" / "models.yaml"

MINIMAL = textwrap.dedent(
    """
    version: t.1
    default_lane: domestic
    providers:
      deepseek:  {sdk: openai, base_url: "https://api.deepseek.com/v1", api_key_env: T_DS}
      anthropic: {sdk: anthropic, api_key_env: T_AN, lane: overseas}
    models:
      deepseek: {provider: deepseek,  id: deepseek-chat, structured: json_object}
      sonnet:   {provider: anthropic, id: claude-sonnet-5, vision: true, structured: native}
      embed:    {provider: deepseek, id: e, kind: embedding, dim: 8}
      rerank:   {provider: deepseek, id: r, kind: rerank}
    lanes:
      domestic:
        intake:               {chain: [deepseek, sonnet], effort: low, max_tokens: 64}
        disambiguate.clarify: {chain: [deepseek]}
        diagnose.vision:      {chain: [sonnet], needs_vision: true}
        diagnose.synthesize:  {chain: [deepseek]}
        guide.step:           {chain: [deepseek]}
        reply.stream:         {chain: [deepseek], stream: true}
        escalate.summary:     {chain: [deepseek]}
        warranty.receipt_ocr: {chain: [sonnet], needs_vision: true}
      overseas:
        intake:               {chain: [sonnet]}
        disambiguate.clarify: {chain: [sonnet]}
        diagnose.vision:      {chain: [sonnet], needs_vision: true}
        diagnose.synthesize:  {chain: [sonnet]}
        guide.step:           {chain: [sonnet]}
        reply.stream:         {chain: [sonnet], stream: true}
        escalate.summary:     {chain: [sonnet]}
        warranty.receipt_ocr: {chain: [sonnet], needs_vision: true}
    """
)


def _write(tmp_path, text: str):
    p = tmp_path / "models.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _mutated(tmp_path, mutate):
    data = yaml.safe_load(MINIMAL)
    mutate(data)
    return _write(tmp_path, yaml.safe_dump(data, allow_unicode=True))


def test_repo_config_loads_and_covers_known_tasks():
    cfg = load_models_config(REAL_CONFIG)
    assert cfg.default_lane == "domestic"
    assert set(KNOWN_TASKS) <= set(cfg.lanes["domestic"])
    assert set(KNOWN_TASKS) <= set(cfg.lanes["overseas"])
    assert cfg.retry.sdk_max_retries == 0
    assert cfg.lane_of("sonnet") == "overseas" and cfg.lane_of("qwen-vl") == "domestic"


def test_minimal_config_loads(tmp_path):
    cfg = load_models_config(_write(tmp_path, MINIMAL))
    assert cfg.route("intake").max_tokens == 64
    assert cfg.route("intake", "overseas").chain == ["sonnet"]


def test_lane_override_switches_default(tmp_path):
    cfg = load_models_config(_write(tmp_path, MINIMAL), lane_override="overseas")
    assert cfg.default_lane == "overseas"
    assert cfg.route("intake").chain == ["sonnet"]


def test_lane_override_unknown_fails_with_name(tmp_path):
    with pytest.raises(ConfigError) as ei:
        load_models_config(_write(tmp_path, MINIMAL), lane_override="mars")
    assert "MODEL_LANE='mars'" in str(ei.value)


def test_missing_file():
    with pytest.raises(ConfigError, match="file not found"):
        load_models_config("/nonexistent/models.yaml")


def test_invalid_yaml_reports_line(tmp_path):
    with pytest.raises(ConfigError, match=r"invalid yaml at line 2"):
        load_models_config(_write(tmp_path, "version: 1\nproviders: {a: [}\n"))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda d: d["lanes"]["domestic"]["intake"]["chain"].append("ghost"),
            "unknown alias 'ghost'",
        ),
        (
            lambda d: d["models"]["deepseek"].__setitem__("provider", "nobody"),
            "provider 'nobody' not in providers",
        ),
        (
            lambda d: d["lanes"]["domestic"]["diagnose.vision"].__setitem__("chain", ["deepseek"]),
            "needs_vision but 'deepseek' has vision: false",
        ),
        (lambda d: d["lanes"]["domestic"].pop("guide.step"), "task 'guide.step' has no chain"),
        (lambda d: d["models"].pop("embed"), "no alias with kind: embedding"),
        (lambda d: d["models"].pop("rerank"), "no alias with kind: rerank"),
        (lambda d: d.__setitem__("default_lane", "eu"), "default_lane 'eu' not in lanes"),
        (
            lambda d: d["lanes"]["domestic"]["intake"].__setitem__("chain", ["embed"]),
            "'embed' is embedding, not a chat model",
        ),
        (
            lambda d: d["lanes"]["domestic"]["intake"].__setitem__("chain", ["deepseek"] * 4),
            "retry.chain_max is 3",
        ),
        (
            lambda d: d["models"]["deepseek"].__setitem__("typo", 1),
            "models.deepseek.typo: Extra inputs are not permitted",
        ),
        (
            lambda d: d["lanes"]["domestic"]["intake"].__setitem__("effort", "max"),
            "lanes.domestic.intake.effort",
        ),
        (
            lambda d: d["providers"]["deepseek"].pop("api_key_env"),
            "providers.deepseek.api_key_env: Field required",
        ),
    ],
)
def test_inconsistency_names_the_item(tmp_path, mutate, expected):
    with pytest.raises(ConfigError) as ei:
        load_models_config(_mutated(tmp_path, mutate))
    assert expected in str(ei.value)


def test_all_problems_reported_together(tmp_path):
    def both(d):
        d["lanes"]["domestic"]["intake"]["chain"].append("ghost")
        d["models"].pop("rerank")

    with pytest.raises(ConfigError) as ei:
        load_models_config(_mutated(tmp_path, both))
    assert len(ei.value.problems) == 2


def test_route_table_matches_model_selection_format(tmp_path):
    cfg = load_models_config(_write(tmp_path, MINIMAL))
    table = render_route_table(cfg)
    lines = table.strip().splitlines()
    assert lines[0:2] == HEADER.splitlines()
    assert "| intake | deepseek | sonnet（overseas） | — | 否 |" in lines
    assert "| diagnose.vision | sonnet（overseas） | — | — | 是 |" in lines
    assert "| embedding | embed（deepseek） | — | — | — |" in lines
    assert lines[-1].startswith("| rerank |")
    assert all(line.count("|") == 6 for line in lines)


def test_route_table_from_repo_config_lists_every_task():
    table = render_route_table(load_models_config(REAL_CONFIG))
    for task in KNOWN_TASKS:
        assert f"| {task} |" in table
    # 票 42（2026-09-13.2）：domestic 链尾改为本机实测达标的智谱位，跨通道降级只留在 overseas 通道本身；
    # 跨通道标注的渲染由下面的合成配置断言，不再绑定仓库配置里某一条链
    overseas = render_route_table(load_models_config(REAL_CONFIG, lane_override="overseas"))
    assert "| intake | haiku |" in overseas


def test_route_table_marks_cross_lane_fallback():
    cfg = load_models_config(REAL_CONFIG)
    domestic = cfg.lanes["domestic"]["intake"]
    cross = cfg.model_copy(deep=True)
    cross.lanes["domestic"]["intake"] = domestic.model_copy(
        update={"chain": [domestic.chain[0], domestic.chain[1], "haiku"]}
    )
    assert "haiku（overseas）" in render_route_table(cross)
