"""容器布局下仍应读取显式挂载的检索配置，而非静默使用默认值。"""

from app.diagnose.config import load_retrieval_config


def test_retrieval_config_uses_environment_path(monkeypatch, tmp_path):
    config = tmp_path / "retrieval.yaml"
    config.write_text("version: mounted\nretrieval:\n  top_k: 9\n")
    monkeypatch.setenv("RETRIEVAL_CONFIG_PATH", str(config))
    loaded = load_retrieval_config()
    assert loaded.version == "mounted"
    assert loaded.retrieval.top_k == 9


def test_explicit_path_overrides_environment(monkeypatch, tmp_path):
    config = tmp_path / "explicit.yaml"
    config.write_text("version: explicit\n")
    monkeypatch.setenv("RETRIEVAL_CONFIG_PATH", str(tmp_path / "missing.yaml"))
    assert load_retrieval_config(config).version == "explicit"
