"""config/ 下的加载必须统一走 CONFIG_DIR。

容器内 app 装在 /srv/app，settings.REPO_ROOT 解析成 /，任何 `REPO_ROOT / "config/..."`
都会指向不存在的 /config——本机开发与单测都正常，只有镜像里会炸，且症状是连接池
起不来导致 /sessions 与 /admin/api 全部 503（/health 仍报 ok）。
"""

import os
import re
from pathlib import Path

from app.settings import CONFIG_DIR

APP_DIR = Path(__file__).resolve().parents[1] / "app"
REPO_ROOT_CONFIG = re.compile(r"""REPO_ROOT\s*/\s*["']config""")


def test_config_dir_points_at_a_real_config_tree():
    assert CONFIG_DIR.is_dir()
    assert (CONFIG_DIR / "models.yaml").is_file()


def test_config_dir_honours_env_override():
    assert os.environ.get("CONFIG_DIR") in (None, str(CONFIG_DIR))


def test_no_module_resolves_config_via_repo_root():
    offenders = [
        f"{path.relative_to(APP_DIR)}:{lineno}"
        for path in APP_DIR.rglob("*.py")
        if path.name != "settings.py"  # CONFIG_DIR 自身的定义处
        for lineno, line in enumerate(path.read_text().splitlines(), 1)
        if REPO_ROOT_CONFIG.search(line)
    ]
    assert not offenders, (
        "这些地方仍用 REPO_ROOT 拼 config/，容器内会解析到 /config，改用 CONFIG_DIR："
        + "、".join(offenders)
    )


def test_every_config_yaml_is_reachable_under_config_dir():
    """新增配置只要落在 config/ 下就该被找到——这是 CONFIG_DIR 存在的意义。"""
    for name in (
        "actions.yaml",
        "emotion_policy.yaml",
        "symptom_taxonomy.yaml",
        "vision_vocab.yaml",
        "conversation.yaml",
        "rules/complaint_terms.yaml",
        "rules/intent_terms.yaml",
    ):
        assert (CONFIG_DIR / name).is_file(), f"{name} 不在 CONFIG_DIR 下"
