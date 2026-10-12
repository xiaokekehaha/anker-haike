"""静态图拓扑：给管理端画 DAG 的底图。

拓扑不手工维护——直接从编译后的 StateGraph 导出，图改了这里自动跟着改。
节点怎么排列由前端按实际运行的平均步序决定（见 metrics/flow 的 avg_step），这里只给节点和边。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def topology() -> dict[str, Any]:
    """{nodes: [{id}], edges: [{source, target, conditional}]}。进程内缓存。"""
    from app.sessions.graph import build_graph

    data = build_graph(None).get_graph().to_json()
    nodes = [{"id": n["id"]} for n in data.get("nodes", [])]
    edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "conditional": bool(e.get("conditional", False)),
        }
        for e in data.get("edges", [])
    ]
    return {"nodes": nodes, "edges": edges}
