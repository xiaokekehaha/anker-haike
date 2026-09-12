"""生成约 200 条模拟工单 CSV（kb_tickets）。确定性随机，重复执行结果一致。

字段：ticket_id, sku, category, symptom, root_cause, steps, result, doc_version
result ∈ solved / unsolved / escalated；非 solved 工单只作反证（09 §2.4）。
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "kb_tickets" / "tickets.csv"
DOC_VERSION = "2026-09-12.1"
SKUS = [
    "EUFY-X10-PRO-OMNI", "EUFY-X9-PRO", "EUFY-X8-PRO-SES", "EUFY-S1-PRO", "EUFY-L60-HYBRID",
    "EUFY-L50-SES", "EUFY-G50-HYBRID", "EUFY-G40-HYBRID", "EUFY-G30-VERGE", "EUFY-G20-HYBRID",
    "EUFY-30C-MAX", "EUFY-25C", "EUFY-15C-MAX", "EUFY-11S-MAX", "EUFY-E20",
]
CASES = [
    ("吸力变小，扫不干净", "滚刷毛发缠绕", "取出滚刷清理缠绕毛发；装回后试运行"),
    ("吸力下降，尘盒很快满", "滤网堵塞", "取出滤网清洗晾干 24 小时后装回"),
    ("提示请检查尘盒", "尘盒未装到位", "重新安装尘盒直到咔哒声"),
    ("边刷不转", "边刷缠绕毛发", "关机拆下边刷清理缠绕物"),
    ("噪音变大吸力弱", "吸口卡异物", "检查吸口取出异物"),
    ("运行中异响并有焦味", "风机电机故障", "告知立即关机停用，升级人工"),
    ("不充电", "基站触点脏污", "擦拭触点后手动放回基站"),
    ("找不到基站", "基站位置遮挡", "调整基站到靠墙开阔位置"),
    ("拖布异味", "拖布未及时清洗", "取下拖布清洗晾干"),
    ("清扫路线混乱", "雷达窗口脏污", "擦拭雷达窗口并重新建图"),
]


def main() -> None:
    rng = random.Random(20260912)
    rows = []
    for i in range(1, 201):
        symptom, root, steps = CASES[(i - 1) % len(CASES)]
        r = rng.random()
        result = "solved" if r < 0.7 else ("escalated" if r < 0.85 else "unsolved")
        if root == "风机电机故障":
            result = "escalated"
        rows.append(
            {
                "ticket_id": f"T{i:04d}",
                "sku": rng.choice(SKUS),
                "category": "robot_vacuum",
                "symptom": symptom,
                "root_cause": root,
                "steps": steps,
                "result": result,
                "doc_version": DOC_VERSION,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
