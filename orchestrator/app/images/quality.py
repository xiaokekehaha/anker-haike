"""像素层画质门控（2026-09-15 阶段 3）——不调用任何模型。

为什么这一层必须存在：模型无法自知其无知。公开实验里，亮度降到 0.15 倍时 VLM 的识别准确率
从 0.99 掉到 0.22，而它自报的置信度仍稳定在 0.87–0.90，错误检测 AUROC≈0.50。
换句话说，**最该拦下来的那些图，恰好是模型看不出自己看不见的那些**。
所以「这张图能不能用」的判断必须来自模型之外，而清晰度、亮度、尺寸恰好都是可计算的确定性指标。

三档判定：
  reject    硬阈值：明显不可用，直接发补拍卡，一次模型都不调
  marginal  软阈值：像素层存疑，交给模型再看一眼，两边都说不行才判不可用
  ok        像素层无异议

指标都只用 Pillow（本仓没有 numpy）：
  focus       梯度的 99.5 分位。长边先归一到 1024（否则换个分辨率数值就变），
              再做 autocontrast（否则暗图会被误判为模糊 —— 实测归一前亮度 1.0→0.1 会让指标掉 10 倍，
              归一后稳定在 96 上下）。取高分位而不是均值，是因为均值随画面平坦程度变化，
              大片纯色的图清晰时数值也低。
  luma_p95    灰度直方图的 95 分位，判过暗。**刻意不用中位数**：中位数分不开「拍得暗」和
              「机身本来就是黑的」，而 Anker 的设备大多是深色的 —— 实测一张曝光正常的深色机身图
              中位数只有 64，会被误判成欠曝，但它的 95 分位有 204；真正欠曝的图两个数一起塌
              （亮度 ×0.15 时 95 分位只剩 30）。用亮端分位等于问「画面里还有没有正常曝光的地方」。
  clipped     亮度 ≥ 250 的像素占比，判过曝
  short_edge  原图短边像素，判「太小 / 拍太远」

**关于 blurry 只做 marginal、不做 reject**：阈值是在合成示意图上标的，而合成图的梯度统计是病态的
（大片纯色 + 完美阶跃边缘），真实照片处处有纹理与噪点，这条阈值大概率不迁移。实测也确实看到
铭牌那类平面为主的图清晰时 focus 只有 20，比别的图模糊到半径 9 时还低。
所以清晰度不允许单独拦人：它只能在模型也说看不清时起加强作用。拿到真实照片后重新标定，再决定是否升为硬阈值。
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from app.settings import CONFIG_DIR

log = logging.getLogger("images.quality")

DECODE_ERRORS = (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError)
FOCUS_NORM_EDGE = 1024  # 算 focus 前把长边归一到这个尺寸，让阈值与拍摄分辨率无关
FOCUS_PERCENTILE = 0.995

Verdict = Literal["ok", "marginal", "reject"]


@dataclass
class QualityReport:
    verdict: Verdict = "ok"
    reasons: list[str] = field(default_factory=list)  # 与 ImageQuality.reasons 同词表
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.verdict != "reject"


def thresholds() -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / "vision_vocab.yaml").read_text())["quality"]


def _percentile(hist: list[int], q: float) -> float:
    total = sum(hist)
    if not total:
        return 0.0
    target, acc = total * q, 0
    for value, count in enumerate(hist):
        acc += count
        if acc >= target:
            return float(value)
    return 255.0


def measure(data: bytes) -> dict[str, float]:
    """四项像素指标；解不开的图返回空 dict（由调用方当作「无从判断」）。"""
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        im.load()
    except DECODE_ERRORS as exc:
        log.warning("quality measure skipped: %s", exc)
        return {}
    grey = im.convert("L")
    short_edge = float(min(grey.width, grey.height))
    hist = grey.histogram()
    total = sum(hist) or 1
    norm = grey.copy()
    norm.thumbnail((FOCUS_NORM_EDGE, FOCUS_NORM_EDGE), Image.LANCZOS)
    norm = ImageOps.autocontrast(norm)
    gradient = ImageChops.difference(norm, ImageChops.offset(norm, 1, 0))
    focus = _percentile(gradient.histogram(), FOCUS_PERCENTILE)
    return {
        "focus": round(focus, 2),
        "luma_p50": _percentile(hist, 0.5),
        "luma_p95": _percentile(hist, 0.95),
        "clipped": round(sum(hist[250:]) / total, 4),
        "short_edge": short_edge,
    }


def assess(data: bytes) -> QualityReport:
    m = measure(data)
    if not m:
        return QualityReport("ok", [], {})
    th = thresholds()
    reject: list[str] = []
    marginal: list[str] = []
    for reason, key, cmp in (
        ("blurry", "focus", "lt"),
        ("too_dark", "luma_p95", "lt"),
        ("too_far", "short_edge", "lt"),
        ("too_bright", "clipped", "gt"),
    ):
        hard, soft = th[reason]["reject"], th[reason]["marginal"]
        value = m[key]
        worse = (lambda v, t: v < t) if cmp == "lt" else (lambda v, t: v > t)
        if hard is not None and worse(value, hard):
            reject.append(reason)  # 硬阈值：直接拦下，一次模型都不调
        elif soft is not None and worse(value, soft):
            marginal.append(reason)  # 软阈值：只在模型也说不行时才判不可用
    if reject:
        return QualityReport("reject", reject, m)
    if marginal:
        return QualityReport("marginal", marginal, m)
    return QualityReport("ok", [], m)


def assess_all(images: list[bytes]) -> QualityReport:
    """多图取最好的一张：只要有一张能用，这一轮就不该被拦下来（与提示词里的口径一致）。"""
    reports = [assess(d) for d in images]
    if not reports:
        return QualityReport("ok", [], {})
    order = {"ok": 0, "marginal": 1, "reject": 2}
    return min(reports, key=lambda r: order[r.verdict])
