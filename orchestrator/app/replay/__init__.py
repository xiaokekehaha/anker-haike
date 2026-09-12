"""回放模式（票 43，09 §6 / 04 §1）：只在 REPLAY_CASE_ID 设置时启用。

- 录制包 `replay/<case_id>/manifest.json + events.jsonl`：清单绑定 {prompt_ver, models_ver, kb_ver, rules_ver}，
  事件为模型调用（invoke / stream）与知识检索的键值记录。
- 启动时清单任一项不符 → ReplayIncompatible（进程启动失败），不静默降级。
- ReplayRouter / ReplayKnowledgeAdapter 按输入键命中记录；未命中返回 unavailable / 抛 ModelInvokeError，
  不借用其他案例、不调真实模型或 WeKnora。
- 命中的检索证据 status=replay，前端显示「演示回放」。
"""

from app.replay.knowledge import RecordingKnowledgeAdapter, ReplayKnowledgeAdapter
from app.replay.package import (
    Recorder,
    ReplayIncompatible,
    ReplayManifest,
    ReplayPackage,
    current_versions,
    knowledge_key,
    load_package,
    model_key,
)
from app.replay.router import RecordingRouter, ReplayRouter

__all__ = [
    "Recorder",
    "RecordingKnowledgeAdapter",
    "RecordingRouter",
    "ReplayIncompatible",
    "ReplayKnowledgeAdapter",
    "ReplayManifest",
    "ReplayPackage",
    "ReplayRouter",
    "current_versions",
    "knowledge_key",
    "load_package",
    "model_key",
]
