"""送进视觉模型之前的确定性图片处理（2026-09-15 阶段 1）。

两件事，都不调模型：

1. `prepare` —— EXIF 方向烤进像素 + 超预算时降采样。
   手机竖拍的方向只记在 EXIF 里，而各厂商都把 rotated 图列为已知失效条件，
   Anthropic 文档甚至两处对「服务端是否读 EXIF」表述不一致 —— 不赌，自己转正。
   降采样只在超过像素预算时才做：把 3000×2250 压到 1568 会让铭牌小字直接消失，
   而 qwen3-vl 单图允许 1600 万像素，默认预算按此设，不做无谓的信息丢弃。

2. `crop_cell` —— 按九宫格从**原图**裁剪并放大，供「看不清就凑近再看一次」的第二次调用。
   实测（2026-09-14）：同一张图铭牌全图 0/3，裁剪放大后 3/3，信息一直在，只是没送到模型眼前。
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger("images.prepare")

# Pillow 打不开 / 认不出 / 判为解压炸弹时的异常集合；这几类一律「原样交给下游」而不是抛错，
# 因为读图失败不该中断排障流程（07 §6）。
DECODE_ERRORS = (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError)

DEFAULT_MAX_PIXELS = 12_000_000  # 约 12MP，覆盖主流手机原图；qwen3-vl 上限 1600 万像素
CELL_GRID = {
    "左上": (0, 0), "上中": (1, 0), "右上": (2, 0),
    "左中": (0, 1), "中心": (1, 1), "右中": (2, 1),
    "左下": (0, 2), "下中": (1, 2), "右下": (2, 2),
}
JPEG_QUALITY = 90


def _encode(im: Image.Image, prefer_png: bool) -> tuple[bytes, str]:
    buf = io.BytesIO()
    if prefer_png:
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue(), "image/png"
    im.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue(), "image/jpeg"


def prepare(data: bytes, mime: str = "image/jpeg", *, max_pixels: int = DEFAULT_MAX_PIXELS) -> tuple[bytes, str]:
    """返回 (处理后的 bytes, mime)。无需改动时原样返回，不做无谓的重编码。"""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except DECODE_ERRORS as exc:  # 解不开就原样交给模型，让上游的校验与降级去处理
        log.warning("image prepare skipped: %s", exc)
        return data, mime
    changed = False
    fixed = ImageOps.exif_transpose(im)
    if fixed is not im and fixed.size != im.size or _has_orientation(im):
        changed = True
    im = fixed or im
    if im.width * im.height > max_pixels:
        ratio = (max_pixels / (im.width * im.height)) ** 0.5
        im = im.resize((max(1, int(im.width * ratio)), max(1, int(im.height * ratio))), Image.LANCZOS)
        changed = True
    if not changed:
        return data, mime
    out, out_mime = _encode(im, prefer_png=mime == "image/png")
    log.info("image prepared %s → %s bytes=%d→%d", mime, out_mime, len(data), len(out))
    return out, out_mime


def _has_orientation(im: Image.Image) -> bool:
    try:
        return (im.getexif() or {}).get(274, 1) not in (1, None)
    except DECODE_ERRORS:
        return False


def crop_cell(
    data: bytes,
    cell: str,
    *,
    expand: float = 0.5,
    zoom: int = 2,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> tuple[bytes, str] | None:
    """裁出九宫格的某一格（四周外扩 expand 倍格宽）并放大 zoom 倍。cell 不认识时返回 None。"""
    if cell not in CELL_GRID:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))) or Image.open(io.BytesIO(data))
        im.load()
    except DECODE_ERRORS as exc:
        log.warning("crop_cell skipped: %s", exc)
        return None
    col, row = CELL_GRID[cell]
    cw, ch = im.width / 3, im.height / 3
    ew, eh = cw * expand, ch * expand
    box = (
        max(0, int(col * cw - ew)),
        max(0, int(row * ch - eh)),
        min(im.width, int((col + 1) * cw + ew)),
        min(im.height, int((row + 1) * ch + eh)),
    )
    crop = im.crop(box)
    if crop.width * crop.height * zoom * zoom <= max_pixels:
        crop = crop.resize((crop.width * zoom, crop.height * zoom), Image.LANCZOS)
    return _encode(crop, prefer_png=False)
