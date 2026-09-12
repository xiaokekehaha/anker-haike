"""模型层（票 09–12）：models.yaml 加载校验、别名 → LangChain 实例、路由表。

LangGraph 节点只认 task 名；模型选择、降级链、参数映射全部由 config/models.yaml 决定。
"""

from app.models.config import ConfigError, ModelsConfig, load_models_config
from app.models.registry import ModelNotConfigured, ModelRegistry, ResolvedModel
from app.models.router import Attempt, ModelInvokeError, ModelResult, ModelRouter

__all__ = [
    "Attempt",
    "ConfigError",
    "ModelInvokeError",
    "ModelNotConfigured",
    "ModelRegistry",
    "ModelResult",
    "ModelRouter",
    "ModelsConfig",
    "ResolvedModel",
    "load_models_config",
]
