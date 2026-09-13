"""guide.step 改写模板（票 34，09 §3.2）：只把 instruction_src 原文改写成用户能执行的一句话，不得增删动作。"""

from __future__ import annotations

from typing import Any

from app.prompts.system import compose_system_prompt, state_layer, wrap_data

GUIDE_PROMPT_VERSION = "2026-09-12.1"

INSTRUCTION = (
    "把 <data> 段里的排障原文改写成一句用户能直接照做的话（中文，不超过 60 字），要求：\n"
    "- 只保留原文里的动作，不得增加、删除或替换任何动作、部件或数值；\n"
    "- 不解释原理、不加安全提醒（安全提醒由系统另行显示）、不提问；\n"
    "- 只输出 JSON：{\"instruction\": \"...\"}。"
)


def guide_messages(
    *, source_text: str, title: str, product: str | None, strategy: str, summary: dict[str, Any] | None
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    short = "用户情绪激动：改写结果不超过两句、越短越好。" if strategy == "reassure_and_shorten" else ""
    human = wrap_data(state_layer(summary or {}), kind="session_state") + f"{INSTRUCTION}{short}\n步骤标题：{title}\n产品：{product or '扫地机器人'}\n{wrap_data(source_text, kind='instruction_src')}"
    return (
        [("system", compose_system_prompt(strategy, summary)), ("human", human)],
        [("system", compose_system_prompt(strategy, summary, simplified=True)), ("human", human)],
    )
