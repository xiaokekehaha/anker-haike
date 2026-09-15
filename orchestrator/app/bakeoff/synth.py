"""合成评测图（票 42）：没有真实照片时用 Pillow 画出可被视觉模型辨认的示意图。

kind:
  receipt   — 订单截图：标题、订单号、店铺、日期、金额四行文字（fields 缺谁就不画谁；blur 打模糊）
  parts     — 故障部件示意：底部滚刷 + 缠绕毛发 / 滤网 + 灰尘 / 尘盒 / 边刷，带中文标签与可选警示词
  nameplate — 高分辨率整机图 + 右下角小铭牌（font_size / contrast 控制难度）。
              验「小字是否被静默编造」：字号越小，模型越容易编出格式合理的假型号（2026-09-14 实测）。
  scene     — 同一画面里放「有故障的部件」与「完好的部件」，配合样本的误导文字，
              验「用户先入之见会不会把真实故障挤掉」（2026-09-14 实测 glm-4.6v 2/2 丢失真故障）。
文字用系统 CJK 字体（STHeiti / Arial Unicode），找不到时退回默认字体（此时中文会变方框，只作链路验证）。
"""

from __future__ import annotations

import io
import random
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

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
    im = {"receipt": _receipt, "nameplate": _nameplate, "scene": _scene}.get(kind, _parts)(spec)
    if spec.get("blur"):
        im = im.filter(ImageFilter.GaussianBlur(float(spec["blur"])))
    if spec.get("brightness") is not None:  # 退化用：模拟欠曝，验像素层门控
        im = ImageEnhance.Brightness(im).enhance(float(spec["brightness"]))
    if kind != "nameplate" and (spec.get("width") or spec.get("height")):
        # 退化用：缩到指定尺寸，验「太小 / 拍太远」。nameplate 自己按 width/height 作画，不走这里。
        im = im.resize((int(spec.get("width", im.width)), int(spec.get("height", im.height))), Image.LANCZOS)
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
        # 旧版画成一条平铺的灰色矩形，三家模型一致读成「正常」—— 换成人看也未必说得出「满」。
        # 真实的满尘盒是「堆起来的、表面不平、带颗粒与毛发」，按此重画（2026-09-15 阶段 2）。
        level = int(spec.get("fill_level", 0.9) * 200)
        top = 360 - level
        heap = [(150, 355)]
        for x in range(150, 500, 34):
            heap.append((x, top + rng.randint(-14, 10)))
        heap += [(490, 355)]
        d.polygon(heap, fill=(96, 84, 70))
        for _ in range(int(level * 2.2) if top + 6 < 352 else 0):  # 颗粒与碎屑（尘盒几乎空时没有堆积面）
            x, y = rng.randint(155, 485), rng.randint(top + 6, 352)
            s = rng.randint(2, 6)
            d.ellipse([x, y, x + s, y + s], fill=rng.choice([(58, 48, 38), (132, 118, 98), (36, 30, 24)]))
        for _ in range(int(level / 6)):  # 表层毛发
            x0 = rng.randint(160, 470)
            y0 = rng.randint(top, top + 40)
            d.line(
                [(x0 + rng.randint(-26, 26), y0 + rng.randint(-8, 14)) for _ in range(4)],
                fill=(26, 20, 16),
                width=2,
            )
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
        _burn(d, rng, cx=320, cy=240)
    label = spec.get("label")
    if label:
        d.text((30, 410), str(label), fill="black", font=_font(30))
    return im


NAMEPLATE_LINES = ("Model: X10 Pro", "S/N: A2637K8J2", "14.4V  5200mAh")


def _nameplate(spec: dict[str, Any]) -> Image.Image:
    """整机图 + 右下角小铭牌。font_size 决定铭牌占画面的比例（14px ≈ 0.15%，34px ≈ 0.84%）。

    contrast=low 模拟激光蚀刻 / 深色机身丝印（深灰字 + 灰底），比黑字白底难一档。
    """
    w, h = int(spec.get("width", 3000)), int(spec.get("height", 2250))
    fs = int(spec.get("font_size", 22))
    im = Image.new("RGB", (w, h), (205, 205, 208))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([w * 0.1, h * 0.11, w * 0.9, h * 0.84], radius=int(w * 0.04), fill=(70, 70, 74))
    d.ellipse([w * 0.37, h * 0.31, w * 0.63, h * 0.67], fill=(45, 45, 48))
    d.text((w * 0.41, h * 0.46), "吸尘口", font=_font(int(w * 0.03)), fill=(150, 150, 155))
    plate, ink = (
        ((96, 96, 100), (52, 52, 56)) if spec.get("contrast") == "low" else ((238, 238, 236), (10, 10, 10))
    )
    pw, ph = int(fs * 11.5), int(fs * 4.6)
    nx, ny = int(w * 0.883) - pw, int(h * 0.822) - ph
    d.rectangle([nx, ny, nx + pw, ny + ph], fill=plate, outline=(20, 20, 20), width=2)
    for i, line in enumerate(spec.get("lines") or NAMEPLATE_LINES):
        d.text((nx + int(fs * 0.45), ny + int(fs * 0.35) + i * int(fs * 1.35)), line, font=_font(fs), fill=ink)
    return im


def _scene(spec: dict[str, Any]) -> Image.Image:
    """机器底部：滚刷缠满毛发（真故障）+ 滤网洁净（无故障）。两个部件都带中文标签。"""
    rng = random.Random(spec.get("seed", 7))
    w, h = 1600, 1200
    im = Image.new("RGB", (w, h), (200, 200, 204))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([80, 80, 1520, 1120], radius=60, fill=(64, 64, 68))
    d.text((120, 110), "机器底部", font=_font(40), fill=(200, 200, 205))
    d.rounded_rectangle([200, 420, 1000, 600], radius=90, fill=(158, 150, 120))
    d.text((205, 340), "滚刷", font=_font(44), fill=(235, 235, 240))
    for _ in range(int(spec.get("hair_count", 260))):
        x, y = rng.randint(220, 980), rng.randint(430, 590)
        d.arc(
            [x - 40, y - 26, x + 40, y + 26],
            rng.randint(0, 180),
            rng.randint(180, 360),
            fill=(18, 18, 20),
            width=5,
        )
    d.rectangle([1120, 420, 1440, 740], fill=(245, 245, 242), outline=(30, 30, 30), width=4)
    for i in range(1, 10):
        d.line([1120 + i * 32, 420, 1120 + i * 32, 740], fill=(205, 205, 200), width=2)
        d.line([1120, 420 + i * 32, 1440, 420 + i * 32], fill=(205, 205, 200), width=2)
    d.text((1125, 340), "滤网", font=_font(44), fill=(235, 235, 240))
    return im


def _burn(d: ImageDraw.ImageDraw, rng: random.Random, *, cx: int, cy: int, scale: float = 1.0) -> None:
    """烧灼痕迹：由外到内的变色圈（焦黄 → 褐 → 炭黑）+ 边缘不规则 + 周围烟炱。

    旧版只画一个深色椭圆，三家模型一致读成「污渍」而不是「烧焦」（2026-09-15 基线实测 安全召回 0%）。
    真实烧痕的判别特征是「同心变色梯度 + 炭化核心 + 烟炱」，这里按此重画，不是为了让模型说出某个词。
    """
    layers = [
        (1.00, (176, 132, 58)),  # 最外：焦黄晕圈
        (0.78, (122, 72, 24)),   # 褐色碳化过渡
        (0.55, (58, 33, 12)),    # 深褐
        (0.34, (22, 16, 13)),    # 炭黑核心
    ]
    for frac, color in layers:
        rx, ry = 78 * frac * scale, 52 * frac * scale
        pts = []
        for k in range(24):
            a = k * 3.14159 * 2 / 24
            jitter = 1 + rng.uniform(-0.14, 0.14)
            pts.append((cx + rx * jitter * __import__("math").cos(a), cy + ry * jitter * __import__("math").sin(a)))
        d.polygon(pts, fill=color)
    for _ in range(90):  # 烟炱：核心外围的细小黑点
        a, r = rng.uniform(0, 6.2832), rng.uniform(0.6, 1.9)
        x = cx + 78 * scale * r * __import__("math").cos(a)
        y = cy + 52 * scale * r * __import__("math").sin(a)
        s = rng.randint(1, 3)
        d.ellipse([x, y, x + s, y + s], fill=(35, 28, 24))
