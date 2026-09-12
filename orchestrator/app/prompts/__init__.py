"""Prompt 文件化（03 §4）：系统提示三层 + <data> 包裹。带版本号，缓存键与录制包引用 PROMPT_VERSION。"""

from app.prompts.reply import REPLY_PROMPT_VERSION, reassurance_messages, reply_messages
from app.prompts.system import (
    PROMPT_VERSION,
    ROLE_LAYER,
    SIMPLIFIED_LAYER,
    compose_system_prompt,
    emotion_layer,
    state_layer,
    wrap_data,
)

__all__ = [
    "PROMPT_VERSION",
    "REPLY_PROMPT_VERSION",
    "ROLE_LAYER",
    "SIMPLIFIED_LAYER",
    "compose_system_prompt",
    "emotion_layer",
    "reassurance_messages",
    "reply_messages",
    "state_layer",
    "wrap_data",
]
