"""静态图拓扑：给管理端画 DAG 的底图。

拓扑不手工维护——直接从编译后的 StateGraph 导出，图改了这里自动跟着改。
节点 → 阶段的归类是展示用的分组（着色 / 泳道），取自各节点实际发出的 progress.stage。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

log = logging.getLogger("admin.graph")

# 节点 → 展示阶段。依据：graph.py 各节点 writer({"type": "progress", "stage": ...}) 的实际取值；
# 不发 progress 的节点（await_input / apply_action / reassure / clarify）归入其所在流程段。
NODE_STAGE: dict[str, str] = {
    "__start__": "start",
    "service_context": "context", "propose": "propose", "authorize": "execute",
    "execute": "execute", "track": "track", "await_human": "awaiting_human",
    "consult": "consult", "apply_human_decision": "awaiting_human",
    "product_help": "consult",
    "advance_tasks": "done", "prepare_retake": "diagnose", "vision_conflict": "diagnose",
    "apply_case_command": "awaiting_human", "reopen_case": "context",
    "understand": "intake",
    "dialogue": "intake",
    "commit_issue": "done",
    "disambiguate": "disambiguate",
    "prepare_card": "disambiguate",
    "clarify": "disambiguate",
    "vision": "diagnose",  # progress: diagnose/vision
    "retrieve": "diagnose",  # progress: diagnose/retrieve
    "reply": "diagnose",  # progress: diagnose
    "guide": "guide",
    "reassess": "guide",  # progress: guide（依据反馈与操作条件重新决策）
    "ask_operation": "guide",  # progress: guide / await_operation_conditions
    "await_input": "wait",  # 发布持久待办，本轮正常结束
    "apply_action": "wait",
    "escalate": "escalate",
    "summarize": "escalate",  # progress: escalate/summarize
    "prepare_receipt": "escalate",  # progress: escalate/collect_receipt
    "receipt_extract": "escalate",  # progress: escalate/extract
    "out_of_scope": "out_of_scope",
    "close": "done",  # progress: done
    "__end__": "end",
}

# 展示顺序，前端据此排泳道
STAGE_ORDER = [
    "start",
    "intake",
    "disambiguate",
    "diagnose",
    "guide",
    "consult", "context", "propose", "execute", "track", "awaiting_human",
    "wait",
    "escalate",
    "out_of_scope",
    "done",
    "end",
]


@lru_cache(maxsize=1)
def topology() -> dict[str, Any]:
    """{nodes: [{id, stage}], edges: [{source, target, conditional}], stage_order}。进程内缓存。"""
    from app.sessions.graph import build_graph

    data = build_graph(None).get_graph().to_json()
    nodes = [
        {"id": n["id"], "stage": NODE_STAGE.get(n["id"], "other")} for n in data.get("nodes", [])
    ]
    edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "conditional": bool(e.get("conditional", False)),
        }
        for e in data.get("edges", [])
    ]
    unmapped = [n["id"] for n in nodes if n["stage"] == "other"]
    if unmapped:  # 图里加了新节点但没归类：能画，但没有阶段着色
        log.warning("nodes missing a stage mapping: %s", unmapped)
    return {"nodes": nodes, "edges": edges, "stage_order": STAGE_ORDER}
