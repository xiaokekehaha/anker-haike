"""票 38 第三项：取消时正在进行的模型流被中止（CancelledError 直达模型），不进入重试链、不切降级。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import ClassVar

from haike_contracts.snapshot import SessionSnapshot
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from app.main import app
from app.models.runtime import set_model_router
from app.rules import RulesService, set_rules_service
from tests.test_reply_stream import DIALOGUE_TEXT, DIALOGUE_TURN, RULES, make_router


class SlowStreamModel(BaseChatModel):
    """每 0.25 s 吐一个 delta 的假模型；记录调用次数与是否被取消。"""

    deltas: ClassVar[list[str]] = ["根据", "说明书", "，请", "先清理", "滚刷", "。"]
    calls: int = 0
    cancelled: bool = False
    finished: bool = False

    @property
    def _llm_type(self) -> str:
        return "slow-stream"

    def _generate(self, *a, **k):  # pragma: no cover - 只走流式
        raise NotImplementedError

    async def _astream(
        self, messages, stop=None, run_manager=None, **kwargs
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.calls += 1
        try:
            for d in self.deltas:
                yield ChatGenerationChunk(message=AIMessageChunk(content=d))
                await asyncio.sleep(0.25)
            self.finished = True
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def test_cancel_aborts_live_model_stream_without_retry(mem_runtime, tmp_path):
    router, fakes = make_router(
        tmp_path, fast=[DIALOGUE_TURN], main=[["x"]], backup=[["备用回答"]]
    )
    slow = SlowStreamModel()
    fakes["main"] = slow  # model_factory 闭包按 alias 取，替换成慢流模型
    set_model_router(router)
    set_rules_service(RulesService(RULES, hot_reload=False))
    manager = app.state.run_manager
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            handle = await manager.start(sid, DIALOGUE_TEXT)
            # 等第一个 message delta 落库（模型流已开始）
            for _ in range(200):
                await asyncio.sleep(0.02)
                if slow.calls and not slow.finished:
                    break
            else:
                raise AssertionError("model stream never started")
            resp = await client.post(f"/sessions/{sid}/cancel", json={"run_id": handle.run_id})
            assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
            await asyncio.sleep(0.6)  # 若未真正中止，慢流会在此期间继续吐 delta / 走完
            snap = SessionSnapshot.model_validate((await client.get(f"/sessions/{sid}")).json())
    finally:
        set_model_router(None)
        set_rules_service(None)

    events = await mem_runtime.list_events(sid, run_id=handle.run_id)
    types = [e["type"] for e in events]
    # 模型流被中止：CancelledError 到达模型，且没有跑完
    assert slow.cancelled is True and slow.finished is False
    # 不重试、不降级：主模型只被调用一次，备用模型零调用
    assert slow.calls == 1 and fakes["backup"].calls == []
    # 事件侧：有 message 但没有 completed 的 message_end，没有 error，最后是 done(cancelled)
    assert "message" not in types and types[-1] == "done" and events[-1]["reason"] == "cancelled"
    assert not any(e["type"] == "message_end" and e["status"] == "completed" for e in events)
    assert "error" not in types
    # 取消后没有新 delta 落库
    deltas_at_done = [e for e in events if e["type"] == "message"]
    assert len(deltas_at_done) < len(slow.deltas)
    assert snap.cancelled_run is not None and snap.cancelled_run.run_id == handle.run_id
    assert snap.last_error is None and snap.active_run is None
