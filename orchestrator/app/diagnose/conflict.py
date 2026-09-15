"""图文冲突检测：在两个**独立**结论之间比对（2026-09-15 阶段 2）。

为什么不交给模型：让同一次调用既读用户文字、又报告「图文是否矛盾」，逻辑上是自指的 ——
被污染的一方在报告自己有没有被污染。2026-09-14 的实测也说明提示词层面的纠偏几乎无效
（「Focus on image」只把偏好从 16.8% 压到 14.2%）。所以视觉调用完全看不到用户文字，
冲突改由这一层用受控词表做符号比对：零模型成本、可单测、可解释、结论稳定。

三种形态（按信息量排序，同一个部件只报最靠前的一种）：
  phenomenon_mismatch  用户说某部件是 A 现象，图中该部件是别的现象
  part_mismatch        用户点名的部件图中没问题，故障其实在另一个部件上
  absent_in_image      用户点名的部件在图中根本没出现（且图是可用的）
"""

from __future__ import annotations

from typing import Any

from app.diagnose.localization import usable_findings, vocabulary

NORMAL = ("正常", "不可辨")


def _claimed(text: str, aliases: dict[str, list[str]]) -> list[str]:
    """用户文字里提到了词表中的哪些词；按别名在文中出现的位置排序，保持用户的叙述顺序。"""
    hits: list[tuple[int, str]] = []
    for canonical, words in aliases.items():
        positions = [text.find(w) for w in words if w and w in text]
        if positions:
            hits.append((min(positions), canonical))
    return [c for _, c in sorted(hits)]


def detect_conflicts(localization: dict[str, Any] | None, claims: list[str]) -> list[str]:
    """返回给用户看的冲突描述；没有冲突时返回空表。

    只在图片可用时判定：图都看不清的时候，「图里没有」说明不了任何事。
    也只用有证据支撑的 finding（usable_findings），避免拿一条模型随口给的结论去质疑用户。
    """
    if not localization or not localization.get("image_quality", {}).get("usable", False):
        return []
    text = " ".join(c for c in claims if c).strip()
    if not text:
        return []
    aliases = vocabulary()["text_aliases"]
    claimed_parts = _claimed(text, aliases["parts"])
    if not claimed_parts:
        return []
    claimed_phenomena = _claimed(text, aliases["phenomena"])
    findings = usable_findings(localization)
    if not findings:
        # 一条有证据支撑的结论都没有 → 对画面内容一无所知，"照片里没有 X" 这种话就没有依据
        return []
    seen: dict[str, str] = {}
    for f in findings:
        seen.setdefault(f["part"], f["phenomenon"])
    faulty = [(p, ph) for p, ph in seen.items() if ph not in NORMAL]

    out: list[str] = []
    for part in claimed_parts:
        if part in seen:
            got = seen[part]
            said = next((ph for ph in claimed_phenomena if ph != got), None)
            if said and said not in NORMAL and got in NORMAL:
                out.append(f"您提到{part}{said}，但照片里{part}看起来是{got}的")
            elif said and said not in NORMAL and got not in NORMAL:
                out.append(f"您提到{part}{said}，但照片里{part}是{got}")
            continue
        others = [(p, ph) for p, ph in faulty if p != part]
        if others:
            p, ph = others[0]
            out.append(f"您提到的是{part}，但照片里看到问题的是{p}（{ph}）")
        else:
            out.append(f"您提到{part}，但照片里没有拍到{part}")
    return out
