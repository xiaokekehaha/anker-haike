"""会话执行契约的唯一 Python 定义。修改后运行 `make contracts` 重新生成 Schema 与前端类型。"""

from haike_contracts.actions import ActionKind, ActionRequest, ActionResult
from haike_contracts.common import PendingInput, PendingKind, Stage
from haike_contracts.events import EVENT_TYPES, ServerEvent, ServerEventAdapter
from haike_contracts.snapshot import SessionSnapshot, TimelineItem

__all__ = [
    "EVENT_TYPES",
    "ActionKind",
    "ActionRequest",
    "ActionResult",
    "PendingInput",
    "PendingKind",
    "ServerEvent",
    "ServerEventAdapter",
    "SessionSnapshot",
    "Stage",
    "TimelineItem",
]
