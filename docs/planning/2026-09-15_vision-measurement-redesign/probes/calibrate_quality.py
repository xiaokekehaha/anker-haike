"""像素层画质门控的阈值标定（阶段 3）。

跑法：orchestrator/.venv/bin/python docs/planning/2026-09-15_vision-measurement-redesign/probes/calibrate_quality.py

对若干合成图做亮度 / 模糊 / 尺寸的退化扫描，打印四项指标随退化的变化，用于确定
config/vision_vocab.yaml 的 quality 阈值。**结论只对合成图成立**：合成图的梯度统计是病态的
（大片纯色 + 完美阶跃边缘），拿到真实照片后必须重跑一遍并复标定，尤其是 blurry。
"""

import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "orchestrator"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "contracts"))

from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from app.bakeoff.synth import render  # noqa: E402
from app.images.quality import assess, measure  # noqa: E402

SPECS = {
    "brush_hair": {"kind": "parts", "part": "roller_brush", "hair": True, "seed": 1},
    "filter_dust": {"kind": "parts", "part": "filter", "dust": True, "seed": 3},
    "dustbin": {"kind": "parts", "part": "dustbin", "fill_level": 0.95, "seed": 6},
    "side_brush": {"kind": "parts", "part": "side_brush", "hair": True, "seed": 9},
    "scene": {"kind": "scene", "seed": 7},           # 深色机身：验「黑设备 ≠ 拍得暗」
    "nameplate": {"kind": "nameplate", "font_size": 22},  # 大片纯色：验「平面 ≠ 模糊」
}


def degrade(data: bytes, *, blur: float = 0, bright: float = 1.0) -> bytes:
    im = Image.open(io.BytesIO(data))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    if bright != 1.0:
        im = ImageEnhance.Brightness(im).enhance(bright)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def main() -> None:
    rendered = {name: render(spec) for name, spec in SPECS.items()}

    print("=== 原图（全部应为 ok，任何一条 marginal/reject 都是误报）===")
    for name, data in rendered.items():
        r = assess(data)
        m = r.metrics
        print(
            f"  {name:<12} {r.verdict:<9} focus={m['focus']:>6.0f} "
            f"p50={m['luma_p50']:>4.0f} p95={m['luma_p95']:>4.0f} short={m['short_edge']:>5.0f} {r.reasons}"
        )

    print("\n=== focus × 模糊半径（对比度归一后，应与曝光无关）===")
    radii = [0, 1, 2, 3, 4, 6, 9, 12]
    print(f"  {'图':<12}" + "".join(f"{r:>7}" for r in radii))
    for name, data in rendered.items():
        print(f"  {name:<12}" + "".join(f"{measure(degrade(data, blur=r))['focus']:>7.0f}" for r in radii))

    print("\n=== 亮度退化：p50 会把「深色机身」误判成「拍得暗」，p95 不会 ===")
    factors = [1.0, 0.6, 0.4, 0.3, 0.2, 0.15, 0.1]
    for name in ("brush_hair", "scene"):
        print(f"  {name}")
        print("    ×     " + "".join(f"{f:>8}" for f in factors))
        print("    p50   " + "".join(f"{measure(degrade(rendered[name], bright=f))['luma_p50']:>8.0f}" for f in factors))
        print("    p95   " + "".join(f"{measure(degrade(rendered[name], bright=f))['luma_p95']:>8.0f}" for f in factors))
        print("    判定  " + "".join(f"{assess(degrade(rendered[name], bright=f)).verdict:>8}" for f in factors))


if __name__ == "__main__":
    main()
