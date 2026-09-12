"""bake-off 评测（票 42，model-selection §3.8）：对每个 task 链上的候选模型跑金标样本，
输出 Schema 通过率 / 字段准确率 / 延迟 P50 / 成本并与门槛比对，给出主备裁决。

评测调用复用生产函数（intake / clarify / synthesize / guide 改写 / reply.stream / summary polish /
query.rewrite / vision / receipt OCR），保证评的就是线上会跑的 Prompt 与后过滤。
"""

from app.bakeoff.config import BakeoffConfig, load_bakeoff_config
from app.bakeoff.runner import run_bakeoff
from app.bakeoff.samples import load_samples

__all__ = ["BakeoffConfig", "load_bakeoff_config", "load_samples", "run_bakeoff"]
