"""票 09：别名 → LangChain 实例、key 只读环境变量且不进日志、探测别名选择。"""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.models.cli import DEFAULT_PROBE_ALIAS, pick_probe_alias
from app.models.config import load_models_config
from app.models.registry import (
    EFFORT_TEMPERATURE,
    ModelNotConfigured,
    ModelRegistry,
    provider_params,
)
from tests.test_models_config import MINIMAL, REAL_CONFIG

SECRET = "sk-test-secret-should-not-leak"


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(MINIMAL, encoding="utf-8")
    return load_models_config(p)


def test_chain_resolution(cfg):
    reg = ModelRegistry(cfg, env={})
    chain = reg.chain("intake")
    assert [r.alias for r in chain] == ["deepseek", "sonnet"]
    assert [r.lane for r in chain] == ["domestic", "overseas"]
    assert chain[0].model_used == "deepseek/deepseek-chat"


def test_build_openai_compatible_uses_base_url_and_zero_retries(cfg):
    reg = ModelRegistry(cfg, env={"T_DS": SECRET})
    m = reg.build_for_task("intake", "deepseek")
    assert isinstance(m, ChatOpenAI)
    assert m.model_name == "deepseek-chat"
    assert m.openai_api_base == "https://api.deepseek.com/v1"
    assert m.max_retries == 0
    assert m.max_tokens == 64
    assert m.temperature == EFFORT_TEMPERATURE["low"]
    assert m.openai_api_key.get_secret_value() == SECRET


def test_build_anthropic_passes_effort(cfg):
    reg = ModelRegistry(cfg, env={"T_AN": SECRET})
    m = reg.build("sonnet", effort="high")
    assert isinstance(m, ChatAnthropic)
    assert m.max_retries == 0
    assert m.output_config == {"effort": "high"}


def test_provider_params_mapping_table():
    assert provider_params("anthropic", "medium") == {"output_config": {"effort": "medium"}}
    assert provider_params("openai", "low") == {"temperature": 0.0}
    assert provider_params("openai", "medium") == {"temperature": 0.2}
    assert provider_params("google_genai", "high") == {"temperature": 0.3}


def test_missing_key_raises_without_leaking(cfg):
    reg = ModelRegistry(cfg, env={})
    with pytest.raises(ModelNotConfigured, match="missing env T_DS"):
        reg.build("deepseek")
    assert reg.unavailable_reason("sonnet") == "missing env T_AN"


def test_pending_model_id_is_unavailable(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(MINIMAL.replace("id: deepseek-chat", "id: TBD"), encoding="utf-8")
    reg = ModelRegistry(load_models_config(p), env={"T_DS": SECRET})
    assert "TBD" in (reg.unavailable_reason("deepseek") or "")
    with pytest.raises(ModelNotConfigured):
        reg.build("deepseek")


def test_describe_never_contains_key(cfg):
    reg = ModelRegistry(cfg, env={"T_DS": SECRET, "T_AN": SECRET})
    text = repr(reg.describe())
    assert SECRET not in text
    assert reg.describe()["providers"]["deepseek"]["key"] == "set"
    assert reg.describe()["providers"]["anthropic"]["lane"] == "overseas"


def test_probe_alias_defaults_to_deepseek_when_no_other_keys():
    reg = ModelRegistry(load_models_config(REAL_CONFIG), env={"DEEPSEEK_API_KEY": SECRET})
    # intake 链首 qwen-flash 无 key（且 id 为 TBD）→ 链上第一个可用即 deepseek
    assert pick_probe_alias(reg, "intake", None) == "deepseek"
    # 链上没有 deepseek 的 task（reply.stream）也回落到默认测试别名
    assert pick_probe_alias(reg, "reply.stream", None) == DEFAULT_PROBE_ALIAS
    assert pick_probe_alias(reg, "intake", "sonnet") == "sonnet"


def test_probe_alias_prefers_first_available_in_chain(cfg):
    reg = ModelRegistry(cfg, env={"T_AN": SECRET})
    assert pick_probe_alias(reg, "intake", None) == "sonnet"
