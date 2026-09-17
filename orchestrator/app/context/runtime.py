"""Apply the same source/time context at every conversational model boundary."""

import json
from contextvars import ContextVar

from langchain_core.messages import convert_to_messages

from app.context.budget import context_input_budget
from app.context.builder import build_context
from app.conversation.history import ConversationEntry
from app.prompts.system import wrap_data

turn_context: ContextVar = ContextVar("turn_context", default=None)


def prepare_messages(task, messages, schema=None):
    state = turn_context.get()
    if not state or not state.get("input_id"):
        return messages
    normalized = convert_to_messages(list(messages))
    # Intake and dialogue already use this builder and original source selection.
    if any(
        m.type == "system"
        and isinstance(m.content, str)
        and "只将 completed 助手消息视为完整答复" in m.content
        for m in normalized
    ):
        return messages
    if any(not isinstance(m.content, str) for m in normalized):
        # Vision/OCR receive only their current images/task + explicit subject, not unrelated QA.
        return [
            *messages,
            (
                "human",
                "图片任务主体数据："
                + json.dumps(
                    {
                        "issue_id": state.get("active_issue_id"),
                        "product": state.get("product_confirmed"),
                        "input_id": state["input_id"],
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
    instruction = "\n".join(m.content for m in normalized if m.type == "system")
    task_data = "\n".join(m.content for m in normalized if m.type != "system")
    if state.get("text"):
        task_data = task_data.replace(wrap_data(state["text"]), "（本轮原话见带来源的用户消息）")
    bundle = build_context(
        [ConversationEntry(**e) for e in state.get("history", [])],
        current_input_id=state["input_id"],
        now=state["at"],
        state={**state, "task_data": task_data, "task": task},
        task=task,
        max_tokens=context_input_budget(task, schema),
        instruction=instruction,
    )
    return bundle.messages
