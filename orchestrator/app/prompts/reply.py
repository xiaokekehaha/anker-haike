"""用户可见文本的 Prompt 模板（reply.stream 任务）。带版本号；主 / 简化两套仅系统提示层不同（07 §6）。"""

from __future__ import annotations

from typing import Any

from app.prompts.system import compose_system_prompt, state_layer, wrap_data

REPLY_PROMPT_VERSION = "2026-09-12.1"

REASSURANCE_INSTRUCTION = (
    "用户情绪需要先安抚。请只输出一到两句中文安抚与承诺（不超过 40 字），不要给步骤、不要提问、不要用 Markdown。"
    "语气真诚、不夸张。"
)

REPLY_INSTRUCTION = (
    "根据 <data> 段里的检索片段与用户描述，用中文回应：先一句话确认理解，再给出最可能的原因与一个立即可做的动作。"
    "只能引用检索片段里出现的操作；片段不足时说明将按标准排障流程处理。不要编造型号、政策或质保结论。"
    "使用简洁 Markdown（最多一个短列表），不要输出代码块。"
)


def _msgs(
    strategy: str, summary: dict[str, Any] | None, human: str, *, simplified: bool
) -> list[tuple[str, str]]:
    return [
        ("system", compose_system_prompt(strategy, summary, simplified=simplified)),
        ("human", wrap_data(state_layer(summary or {}), kind="session_state") + "\n" + human),
    ]


def reassurance_messages(text: str, *, strategy: str, summary: dict[str, Any] | None = None):
    human = f"{REASSURANCE_INSTRUCTION}\n{wrap_data(text)}"
    return _msgs(strategy, summary, human, simplified=False), _msgs(
        strategy, summary, human, simplified=True
    )


def reply_messages(
    text: str,
    *,
    strategy: str,
    summary: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    knowledge_status: str | None,
):
    snippets = "\n\n".join(
        f"[{e.get('evidence_id', '')[:8]}] {e.get('snippet', '')}" for e in evidence[:6]
    )
    status_note = {
        "no_match": "（知识库未找到匹配片段，按标准排障流程说明）",
        "unavailable": "（知识库暂不可用，按标准排障流程说明，不要臆造步骤）",
    }.get(knowledge_status or "", "")
    step_rule = "每个步骤不超过两句。" if strategy == "reassure_and_shorten" else ""
    human = (
        f"{REPLY_INSTRUCTION}{step_rule}{status_note}\n"
        f"{wrap_data(text)}\n"
        f"{wrap_data(snippets or '（无）', kind='retrieved_snippets')}"
    )
    return _msgs(strategy, summary, human, simplified=False), _msgs(
        strategy, summary, human, simplified=True
    )
