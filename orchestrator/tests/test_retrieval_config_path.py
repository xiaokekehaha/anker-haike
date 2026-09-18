"""容器布局下仍应读取显式挂载的检索配置，而非静默使用默认值。"""

import pytest

from app.diagnose.config import load_retrieval_config
from app.settings import REPO_ROOT


def test_retrieval_config_uses_environment_path(monkeypatch, tmp_path):
    config = tmp_path / "retrieval.yaml"
    config.write_text("version: mounted\nretrieval:\n  candidate_k: 19\n  final_k: 9\n")
    monkeypatch.setenv("RETRIEVAL_CONFIG_PATH", str(config))
    loaded = load_retrieval_config()
    assert loaded.version == "mounted"
    assert loaded.retrieval.candidate_k == 19 and loaded.retrieval.final_k == 9


def test_explicit_path_overrides_environment(monkeypatch, tmp_path):
    config = tmp_path / "explicit.yaml"
    config.write_text("version: explicit\n")
    monkeypatch.setenv("RETRIEVAL_CONFIG_PATH", str(tmp_path / "missing.yaml"))
    assert load_retrieval_config(config).version == "explicit"


@pytest.mark.parametrize("path", sorted((REPO_ROOT / "data/eval/retrieval/configs").glob("*.yaml")), ids=lambda p: p.stem)
def test_evaluation_presets_load_with_current_schema(path):
    cfg = load_retrieval_config(path)
    assert cfg.version == "2026-09-18.1"
    assert cfg.retrieval.candidate_k >= cfg.retrieval.final_k
    assert "刷子" not in cfg.query_rewrite.synonyms.get("滚刷", [])
