"""金标样本：tests/fixtures/bakeoff/<task>.yaml；视觉样本的图片运行时合成（Pillow），不落仓库。

每条样本：
  id, input（task 专属输入字段）, expect（评分规则，见 scoring.py）
视觉样本可选 image: {kind: synthetic, draw: ...} 或 image: {file: <相对 BAKEOFF_IMAGES_DIR 的路径>}。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.settings import REPO_ROOT

FIXTURES_DIR = REPO_ROOT / "orchestrator" / "tests" / "fixtures" / "bakeoff"


@dataclass
class Sample:
    task: str
    id: str
    input: dict[str, Any]
    expect: dict[str, Any] = field(default_factory=dict)
    image: dict[str, Any] | None = None
    images: list[tuple[str, bytes]] = field(
        default_factory=list
    )  # (mime, bytes)，视觉样本运行时填充


def load_samples(task: str, *, fixtures_dir: Path | None = None) -> list[Sample]:
    path = (fixtures_dir or FIXTURES_DIR) / f"{task.replace('.', '_')}.yaml"
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[Sample] = []
    for c in raw.get("cases") or []:
        s = Sample(
            task=task,
            id=str(c["id"]),
            input=dict(c.get("input") or {}),
            expect=dict(c.get("expect") or {}),
            image=c.get("image"),
        )
        if s.image:
            s.images = materialize_images(s.image)
        out.append(s)
    return out


def materialize_images(spec: dict[str, Any]) -> list[tuple[str, bytes]]:
    """file → 从 BAKEOFF_IMAGES_DIR 读真实照片；synthetic → Pillow 画一张示意图。"""
    if "file" in spec:
        base = Path(os.environ.get("BAKEOFF_IMAGES_DIR", REPO_ROOT / "data" / "bakeoff-images"))
        p = base / spec["file"]
        if not p.is_file():
            return []
        mime = "image/jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        return [(mime, p.read_bytes())]
    from app.bakeoff.synth import render

    return [("image/png", render(spec))]
