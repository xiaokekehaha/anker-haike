"""客户首封描述的可见物理损坏（部件断裂 / 脱落 / 开裂 / 缺失）：不发排障步骤，直接进质保判断（R6）。

2026-10-08 Fable 5.1 裁定（63 单回放 T42：塑料件脱落漏水，先跑了 4 张「清空污水箱」排障卡）：
- 破损词与部件名词须在同一句共现；
- 排除可自装的耗材 / 配件（滚刷、拖布、滤网、尘袋），以及破损词修饰声音（T28「crack sound」）；
- 不要求附图：照片是质保证据，进分支后再向客户索取。
63 单里命中 T42、T44，均为真实物理损坏。
"""

from __future__ import annotations

import re

DAMAGE = re.compile(
    r"\b(broke|broken|snapped|came off|come off|fell off|falls off|cracked|crack|missing|detached|"
    r"roto|rota|se cayó|falta|cassée?|détachée?|manque|abgebrochen|kaputt|fehlt|gebroken|afgebroken|los gekomen)\b"
    r"|断了|断裂|掉了|脱落|裂了|开裂|缺了|缺失",
    re.IGNORECASE,
)
PART = re.compile(
    r"\b(piece|part|plastic|pin|pins|lid|cover|tank|wheel|hinge|clip|clips|latch|connector|housing|shell|case|"
    r"handle|button|stuk|onderdeel|deksel|teil|deckel|pièce|couvercle|pieza|tapa)\b"
    r"|零件|部件|塑料|盖子|水箱|轮子|卡扣|外壳|按键|针脚",
    re.IGNORECASE,
)
EXCLUDED = re.compile(
    r"\b(brush|brushes|mop|mops|filter|filters|dust ?bag|roller|pad|pads|sound|noise|noises|geluid|geräusch|bruit|ruido)\b"
    r"|滚刷|边刷|拖布|滤网|尘袋|声音|异响",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"[^.!?。！？\n]+")


def physical_damage(text: str) -> str | None:
    """返回描述物理损坏的那一句原话；没有返回 None。"""
    for sentence in SENTENCE.findall(text or ""):
        if DAMAGE.search(sentence) and PART.search(sentence) and not EXCLUDED.search(sentence):
            return sentence.strip()
    return None
