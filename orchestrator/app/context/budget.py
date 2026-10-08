"""Final model-call budget, after schema hints/retries and before each fallback."""

import json

from app.context.builder import estimate_tokens, message_tokens
from app.context.config import conversation_config


def context_input_budget(task, schema=None, *, extra_instruction="") -> int:
    """Reserve provider schema wrappers, optional fallback instructions and message framing."""
    reserve = 256 + estimate_tokens(extra_instruction)
    if schema is not None:
        reserve += estimate_tokens(json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")))
    return conversation_config().input_budget(task) - reserve


def measure_input(messages, *, schema=None, schema_in_messages=False) -> dict[str, int]:
    text = []
    images = 0
    for message in messages:
        content = message.content
        if isinstance(content, str):
            text.append(content)
        else:
            for block in content:
                if isinstance(block, dict) and block.get("type") in {"image", "image_url"}:
                    images += 1
                elif isinstance(block, dict):
                    text.append(str(block.get("text", "")))
    if schema is not None and not schema_in_messages:
        text.append(json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")))
    return {"text_tokens": sum(message_tokens(value) for value in text), "images": images}


def budget_error(messages, spec, *, task=None, schema=None, schema_in_messages=False, output_tokens=2048):
    measured = measure_input(messages, schema=schema, schema_in_messages=schema_in_messages)
    tokens, images = measured["text_tokens"], measured["images"]
    if tokens > conversation_config().input_budget(task):
        return "text input/schema exceeds conversation budget"
    # Image encoding differs by provider; reserve 16k per image within the provider window.
    # Upload count/size limits are independently enforced by vision/OCR selection.
    if spec.context_window and tokens + images * 16384 + output_tokens > spec.context_window:
        return "input/schema/images/output exceeds model context window"
    return None


def fit_prompt_budget(parts: list[str], *, budget: int) -> tuple[list[str], bool]:
    """按顺序保留片段直到累计 token 达上限；返回 (保留的片段, 是否截断)。"""
    used = 0
    kept: list[str] = []
    for part in parts:
        n = estimate_tokens(part)
        if used + n > budget:
            return kept, True
        used += n
        kept.append(part)
    return kept, False
