"""产品咨询回复：证据按 [n] 编号进提示词，正文不得出现证据 id；引用只取服务端归因的 evidence_id。"""

from __future__ import annotations

import re

from tests.conversation_runtime import conversation as conversation_fixture
from tests.test_product_questions import ANSWER, DIRECT
from tests.test_product_questions import knowledge as knowledge_fixture

conversation = conversation_fixture
knowledge = knowledge_fixture

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


async def test_product_answer_prompt_uses_numbered_evidence_and_output_has_no_ids(conversation, knowledge):
    # 模型照 T35 的样子把一个拼接 id 和一个编号抄进正文
    conversation.models["reply.stream"].script = [[ANSWER + " [05af0178-096c-47d0-b317-fc99b221f68e]", " [1]."]]
    events = await conversation.send(DIRECT, {
        "primary_intent": "product_question", "product_hints": ["T8D04"], "device_relation": "current",
    })
    prompt = "".join(str(m.content) for m in conversation.models["reply.stream"].calls[-1]["messages"])
    assert "[1]" in prompt and not UUID.search(prompt), "提示词只给编号，不给证据 UUID"
    text = "".join(e["delta"] for e in events if e["type"] == "message")
    assert ANSWER in text and not UUID.search(text) and "[1]" not in text
    end = next(e for e in events if e["type"] == "message_end" and e["status"] == "completed")
    evidence_ids = {item["evidence_id"] for e in events if e["type"] == "evidence" for item in e["items"]}
    assert end.get("citations") and set(end["citations"]) <= evidence_ids
