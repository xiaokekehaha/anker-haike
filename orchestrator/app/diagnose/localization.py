"""读图结果的归一化与确定性映射（票 62；2026-09-15 阶段 1 重写）。

这一层的职责是把「模型说了什么」变成「系统敢用什么」，所以只做确定性的事：
- 词表归一：表外的值收进「其他」并把原值留在 raw，未知收进「不可辨」；
- 铭牌可读性从 model_hint 的字面派生（含 ? 即 partial，空即 unreadable），不接受模型自报；
- signature → plan 只认符号条件（部件与现象都可辨、且给出了 evidence），
  不再用模型自报的 confidence —— 自报置信度在错误检测上 AUROC≈0.5，拿它当阈值等于用随机数驱动先验。
"""

import yaml

from app.settings import CONFIG_DIR


def vocabulary():
    return yaml.safe_load((CONFIG_DIR / "vision_vocab.yaml").read_text())


def model_hint_readable(hint: str | None) -> str:
    """full = 读全了；partial = 读到但有 ? 占位；unreadable = 没读到。驱动阶段 1 的裁剪复看。"""
    text = (hint or "").strip()
    if not text or not text.replace("?", "").replace("？", "").strip():
        return "unreadable"
    return "partial" if ("?" in text or "？" in text) else "full"


def _valid_index(index, image_count: int | None):
    """图序号超出实际张数就当没给：模型报了个不存在的图，不如承认不知道是哪张。"""
    if index is None:
        return None
    if image_count is not None and not (1 <= index <= image_count):
        return None
    return index


def _content_kinds(raw, image_count: int | None) -> list[str]:
    """模型给的逐图定性 → 按图序排好的列表。没说到的图按 fault_photo 处理。

    默认 fault_photo 而不是 other：读图任务本身只对 purpose=fault 的图调用，漏填时沿用调用语境
    是保守的一侧 —— 把真故障照错判成单据会丢掉证据，反之只是多收一次证据。
    """
    count = image_count or 0
    kinds = ["fault_photo"] * count
    for item in raw or []:
        index = item.get("image_index")
        if isinstance(index, int) and 1 <= index <= count:
            kinds[index - 1] = item["kind"]
    return kinds


def normalize(localization, image_count: int | None = None):
    config = vocabulary()
    unknown = config["unknown"]
    result = localization.model_dump(mode="json", exclude={"observations", "visible_parts"})
    # 模型输出的 schema 里已经没有这两个字段（阶段 2 / 阶段 1），但直接传 FaultLocalization 的调用方还有
    result.setdefault("conflicts_with_text", [])
    result.setdefault("model_hint_verified", False)
    result["model_hint_image"] = _valid_index(result.get("model_hint_image"), image_count)
    result["content_kinds"] = _content_kinds(result.get("content_kinds"), image_count)
    # 单据 / 其他内容的图不产生故障结论：模型被要求只为 fault_photo 写 findings，但那是自报的约束，
    # 而约束的执行权不该握在被约束者手里 —— 这里按定性结果确定性地丢掉。
    non_fault = {i for i, k in enumerate(result["content_kinds"], 1) if k != "fault_photo"}
    if non_fault:
        result["findings"] = [
            f for f in result["findings"] if f.get("image_index") not in non_fault
        ]
    for finding in result["findings"]:
        for key, vocab in [("part", "parts"), ("phenomenon", "phenomena")]:
            if finding[key] not in config[vocab]:
                finding.setdefault("raw", {})[key] = finding[key]
                finding[key] = "其他"
        if finding.get("cell") not in config["cells"]:
            finding["cell"] = None
        finding["image_index"] = _valid_index(finding.get("image_index"), image_count)
    quality = result["image_quality"]
    quality["guidance"] = [config["retake_guidance"][r] for r in quality["reasons"]]
    result["model_hint_readable"] = model_hint_readable(result.get("model_hint"))
    # 丢掉整条都说不上来的；同一 (部件, 现象) 只留第一条（实测见过同一模型把「滚刷缠绕」报三遍，
    # 重复项会把回显和 issue facts 撑胖，对判断没有任何增量）
    seen: set[tuple[str, str]] = set()
    kept = []
    for f in result["findings"]:
        key = (f["part"], f["phenomenon"])
        if key == (unknown, unknown) or key in seen:
            continue
        seen.add(key)
        kept.append(f)
    result["findings"] = kept
    return result


def usable_findings(localization) -> list[dict]:
    """能驱动下游决策的 finding：部件与现象都可辨，且模型给出了对应的可见证据。"""
    unknown = vocabulary()["unknown"]
    return [
        f
        for f in (localization or {}).get("findings", [])
        if f["part"] != unknown and f["phenomenon"] != unknown and (f.get("evidence") or "").strip()
    ]


def signature_matches(localization, faults=None) -> list[tuple[dict, list[str]]]:
    """每条可用 finding 命中的 plan_id 列表，按 finding 归因（写症状事实时要带上「是哪条观察推出来的」）。

    没命中任何签名的 finding 也保留（plan_ids 为空）：调用方据此知道这条观察对候选集没有贡献。
    """
    if not localization or not localization["image_quality"]["usable"]:
        return []
    signatures = (
        [
            {"part": s.part, "phenomenon": s.phenomenon, "plan_id": f.plan_id}
            for f in faults
            for s in f.signatures
        ]
        if faults is not None
        else vocabulary()["signatures"]
    )
    return [
        (
            f,
            list(
                dict.fromkeys(
                    s["plan_id"]
                    for s in signatures
                    if (f["part"], f["phenomenon"]) == (s["part"], s["phenomenon"])
                )
            ),
        )
        for f in usable_findings(localization)
    ]


def signature_plans(localization, faults=None):
    return list(dict.fromkeys(pid for _, ids in signature_matches(localization, faults) for pid in ids))


def part_categories(localization) -> list[str]:
    """照片里认出的品类特有部件 → 品类（`category_parts`）。只是线索：调用方仍要让用户确认。

    用 findings（normalize 后已按词表归一）而不用 visible_parts（模型原话）。「正常」的 finding 也算：
    看见一根完好的滚刷，同样说明这是扫地机器人。
    """
    parts = {f["part"] for f in (localization or {}).get("findings", [])}
    return [
        category
        for category, hints in vocabulary().get("category_parts", {}).items()
        if parts.intersection(hints)
    ]


def echo_findings(localization) -> str | None:
    """把读图结果回显成一句人话，供步骤卡做隐式确认（阶段 4）。

    会话设计的通行做法：高置信 + 低后果用隐式确认（陈述我看到了什么，用户看错了会纠正），
    不可逆动作才用显式确认（必须点「确认」才执行）。读图属于前者 —— 说错了代价是用户回一句，
    而每次都弹确认框会把排障拖慢一倍。

    句子由结构化结果确定性拼出，不经模型：回显的意义就在于「我们真正拿到的是什么」，
    让模型再措辞一遍就等于把它可能编的东西又念了一遍。

    客户可见，所以用英文（D2）：部件 / 现象经 vision_vocab 的 english 映射，与图文冲突提示同一套词。
    """
    from app.diagnose.conflict import en

    facts = [
        f"{en(f['part'])} {en(f['phenomenon'])}"
        for f in usable_findings(localization)
        if f["phenomenon"] not in ("正常", "不可辨")
    ]
    if not facts:
        return None
    return f"From the photo I can see: {', '.join(dict.fromkeys(facts))}. If that's not right, just tell me."
