"""证据标识不经模型之手（2026-10-10 第 2 项）：

T35 第十轮产品咨询回复里出现了拼接出来的 UUID「05af0178-096c-47d0-b317-fc99b221f68e」，
它不在本轮任何证据里。根因是 evidence_header 把 36 位证据 id 直接喂给模型，模型抄写时把两个 id 拼接。
修法：提示词只给 [n] 编号，流式层把 UUID 形状和 [n] 编号形状的标记丢掉，引用只取服务端归因。
"""

from __future__ import annotations

import pytest

from app.sessions.streaming import strip_markers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 真实 T35 输出：拼接 UUID 夹在句尾
        (
            "the robot will automatically resume the last incomplete cleaning task [05af0178-096c-47d0-b317-fc99b221f68e].",
            "the robot will automatically resume the last incomplete cleaning task.",
        ),
        ("See [1] and [2] for details.", "See and for details."),
        ("Charging resumes [1][2].", "Charging resumes."),
        ("裸 UUID 05af0178-096c-43b6-9007-79ca404b44e1 也不留。", "裸 UUID 也不留。"),
        # 不是标识符的方括号保留：用户可见的选项、Markdown 链接文本
        ("Press [Power] for 12 seconds.", "Press [Power] for 12 seconds."),
        ("[Click here](https://support.eufy.com/x)", "[Click here](https://support.eufy.com/x)"),
        ("Error 7021 means positioning failed.", "Error 7021 means positioning failed."),
    ],
)
def test_strip_markers_removes_ids_and_numbered_refs(text, expected):
    assert strip_markers(text) == expected


async def test_stream_filter_handles_marker_split_across_deltas():
    """标记可能被分成多个 delta（「[05af0178-」「096c-…」「]」）：过滤器跨块缓冲，不把半截 id 发给用户。"""
    from app.sessions.streaming import MarkerFilter

    f = MarkerFilter()
    chunks = ["Charging resumes ", "[05af0178-096c", "-47d0-b317-fc99b221f68e", "] when ready.", " Done [", "1", "]."]
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == "Charging resumes when ready. Done."


async def test_stream_filter_flushes_unfinished_bracket():
    from app.sessions.streaming import MarkerFilter

    f = MarkerFilter()
    out = f.feed("Press [Power") + f.flush()
    assert out == "Press [Power"
