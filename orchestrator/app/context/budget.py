"""Final model-call budget, after schema hints/retries and before each fallback."""

import json

from app.context.builder import estimate_tokens
from app.context.config import conversation_config


def budget_error(messages, spec, *, schema=None, schema_in_messages=False, output_tokens=2048):
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
        text.append(json.dumps(schema.model_json_schema(), ensure_ascii=False))
    tokens = sum(estimate_tokens(value) + 8 for value in text)
    if tokens > conversation_config().max_input_tokens:
        return "text input/schema exceeds conversation budget"
    # Image encoding differs by provider; reserve 16k per image within the provider window.
    # Upload count/size limits are independently enforced by vision/OCR selection.
    if spec.context_window and tokens + images * 16384 + output_tokens > spec.context_window:
        return "input/schema/images/output exceeds model context window"
    return None
