"""合成评测图（票 42）：没有真实照片时用 Pillow 画出可被视觉模型辨认的示意图。

kind:
  receipt  — 订单截图：标题、订单号、店铺、日期、金额四行文字（fields 缺谁就不画谁；blur 打模糊）
  parts    — 故障部件示意：底部滚刷 + 缠绕毛发 / 滤网 + 灰尘 / 尘盒 / 边刷，带中文标签与可选警示词
文字用系统 CJK 字体（STHeiti / Arial Unicode），找不到时退回默认字体（此时中文会变方框，只作链路验证）。
"""

from __future__ import annotations

import io
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(spec: dict[str, Any]) -> bytes:
    kind = spec.get("kind", "parts")
    im = _receipt(spec) if kind == "receipt" else _parts(spec)
    if spec.get("blur"):
        im = im.filter(ImageFilter.GaussianBlur(float(spec["blur"])))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _receipt(spec: dict[str, Any]) -> Image.Image:
    fields = spec.get("fields") or {}
    im = Image.new("RGB", (720, 520), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 720, 90], fill=(255, 80, 0))
    d.text((30, 25), spec.get("title", "订单详情"), fill="white", font=_font(36))
    y = 130
    rows = [
        ("订单编号", fields.get("order_no")),
        ("店铺", fields.get("channel")),
        ("下单时间", fields.get("purchase_date")),
        ("实付款", fields.get("amount")),
    ]
    for label, value in rows:
        if value is None:
            continue
        d.text((40, y), f"{label}：", fill=(90, 90, 90), font=_font(28))
        d.text((220, y), str(value), fill="black", font=_font(28))
        y += 70
    if spec.get("product"):
        d.rectangle([40, y + 10, 680, y + 110], outline=(200, 200, 200), width=2)
        d.text((60, y + 40), str(spec["product"]), fill="black", font=_font(26))
    return im


def _parts(spec: dict[str, Any]) -> Image.Image:
    rng = random.Random(spec.get("seed", 1))
    im = Image.new("RGB", (640, 480), (238, 238, 238))
    d = ImageDraw.Draw(im)
    part = spec.get("part", "roller_brush")
    if part == "roller_brush":
        d.rounded_rectangle([60, 180, 580, 300], radius=60, fill=(50, 50, 50))
        for x in range(80, 580, 24):
            d.line([(x, 190), (x + 10, 290)], fill=(120, 120, 120), width=2)
        if spec.get("hair", True):
            for _ in range(int(spec.get("hair_count", 60))):
                x0 = rng.randint(70, 570)
                pts = [(x0 + rng.randint(-40, 40), 185 + rng.randint(0, 110)) for _ in range(4)]
                d.line(pts, fill=(40, 25, 10), width=2)
    elif part == "filter":
        d.rectangle([140, 120, 500, 360], fill=(230, 230, 230), outline=(120, 120, 120), width=4)
        for y in range(130, 360, 12):
            d.line([(150, y), (490, y)], fill=(180, 180, 180), width=1)
        if spec.get("dust", True):
            for _ in range(int(spec.get("dust_count", 400))):
                x, y = rng.randint(150, 490), rng.randint(130, 350)
                d.ellipse([x, y, x + rng.randint(2, 6), y + rng.randint(2, 6)], fill=(110, 100, 90))
    elif part == "dustbin":
        d.polygon(
            [(160, 120), (480, 120), (520, 360), (120, 360)],
            fill=(200, 200, 210),
            outline=(90, 90, 90),
        )
        level = int(spec.get("fill_level", 0.9) * 200)
        d.rectangle([150, 360 - level, 490, 355], fill=(105, 95, 85))
    elif part == "side_brush":
        cx, cy = 320, 240
        d.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], fill=(60, 60, 60))
        for k in range(3):
            ang = k * 2.0944
            import math

            for j in range(10):
                x = cx + math.cos(ang + j * 0.03) * (40 + j * 14)
                y = cy + math.sin(ang + j * 0.03) * (40 + j * 14)
                d.line([(cx, cy), (x, y)], fill=(90, 90, 90), width=2)
        if spec.get("hair", True):
            for _ in range(40):
                x0 = rng.randint(200, 440)
                pts = [(x0 + rng.randint(-30, 30), 200 + rng.randint(0, 80)) for _ in range(3)]
                d.line(pts, fill=(40, 25, 10), width=2)
    if spec.get("burn"):
        d.ellipse([260, 200, 380, 280], fill=(20, 10, 5))
        d.ellipse([280, 215, 360, 265], fill=(60, 30, 10))
    label = spec.get("label")
    if label:
        d.text((30, 410), str(label), fill="black", font=_font(30))
    return im
