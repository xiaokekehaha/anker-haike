"""自由文本回复的事后引用归因（G1a）。

卡片路径的证据是强制的：假设零证据整条丢弃、步骤引用越界即丢步。自由文本路径（reply.stream
与 reply_to_turn）却只是把检索片段塞进提示词，输出不做任何校验——R7 样本里「模型自行给出
三步排查」就走的这条路，那三步没有任何来源。

这里先不改提示词、不让模型自己标 [n]（外部方案正是这么做的，且对模型标了什么完全不校验，
可信度建立在模型合规上）。改为事后按字面重叠把句子对回片段：零模型成本、可离线重放，
而且偏差方向是把有据判成无据，作为基线偏保守是可接受的。

见 docs/claude/spec_grounded_citation_20260916.md §3。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# 一句话与某个片段的最长公共子串占句长的比例达到这个值，才算这句有据。
# 调高会漏掉改写过的句子，调低会把「请把机器放到开阔处」这类通用话术错认成有据。
GROUNDED_RATIO = 0.45
MIN_SENTENCE_CHARS = 8

_SPLIT = re.compile(r"[。！？；\n]+")
_STRIP = re.compile(r"^[\s\-*•·0-9.、)）]+")
# 含具体动作的句子才要求有来源：安抚、澄清提问、历史回顾本来就不该有引用。
# 按关键词认，口语说法（「把那个弄一弄」）认不出来，ungrounded 的分母因此偏保守——
# 扩词表会把安抚语误判成动作句，那比漏计更糟。
_ACTION = re.compile(
    r"检查|清理|清洁|取出|打开|拆|更换|重启|重新|放回|擦|冲洗|晾干|倒空|按下|翻转|关机|插|拔|复位|长按"
)


def sentences(text: str) -> list[str]:
    """按句切分并去掉 Markdown 列表前缀；太短的句子不参与判定（「好的」「请稍等」）。"""
    out = []
    for raw in _SPLIT.split(text or ""):
        s = _STRIP.sub("", raw).strip()
        if len(s) >= MIN_SENTENCE_CHARS:
            out.append(s)
    return out


def _overlap(sentence: str, source: str) -> float:
    if not sentence or not source:
        return 0.0
    m = SequenceMatcher(None, sentence, source, autojunk=False).find_longest_match(
        0, len(sentence), 0, len(source)
    )
    return m.size / len(sentence)


def attribute(text: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """把回复对回本轮片段。

    返回 {citations, grounded, actionable, ungrounded}：citations 是被引用到的 evidence_id
    （按片段顺序、去重），ungrounded 是「有动作但对不上任何片段」的句子数——它就是
    ungrounded_reply 指标的分子。
    """
    sents = sentences(text)
    cited: list[str] = []
    grounded = 0
    actionable = 0
    ungrounded = 0
    for s in sents:
        act = bool(_ACTION.search(s))
        actionable += act
        best_id, best = None, 0.0
        for e in evidence:
            eid = e.get("evidence_id")
            if not eid:
                continue
            for field in ("snippet", "full_text"):
                r = _overlap(s, e.get(field) or "")
                if r > best:
                    best_id, best = eid, r
        if best >= GROUNDED_RATIO and best_id:
            grounded += 1
            if best_id not in cited:
                cited.append(best_id)
        elif act:
            ungrounded += 1
    return {
        "citations": cited,
        "sentences": len(sents),
        "grounded": grounded,
        "actionable": actionable,
        "ungrounded": ungrounded,
    }
