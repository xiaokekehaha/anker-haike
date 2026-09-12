"""haike-metrics：按 run 去重，按会话汇总首可见/首卡延迟并输出 P50/P95。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], p: float) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def summarize(paths: list[Path]) -> dict:
    runs: dict[tuple[str, str], dict] = {}
    invalid = 0
    for path in paths:
        with path.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise TypeError("row is not an object")
                except (ValueError, TypeError):
                    invalid += 1
                    continue
                if row.get("event") != "run_metric":
                    continue
                metric = row.get("metric")
                if metric not in {"first_visible_ms", "card_ready_ms"}:
                    continue
                value = row.get("value_ms")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    invalid += 1
                    continue
                key = (row.get("session_id"), row.get("run_id"))
                if not all(isinstance(v, str) and v for v in key):
                    invalid += 1
                    continue
                bucket = runs.setdefault(key, {"session_id": key[0], "run_id": key[1]})
                bucket[metric] = min(bucket.get(metric, value), value)
                if metric == "card_ready_ms":
                    bucket["card_kind"] = row.get("card_kind")
    metrics = {}
    for name in ("first_visible_ms", "card_ready_ms"):
        values = [row[name] for row in runs.values() if name in row]
        metrics[name] = {
            "count": len(values),
            "p50": percentile(values, 0.5),
            "p95": percentile(values, 0.95),
        }
    sessions: dict[str, list] = {}
    for row in runs.values():
        sessions.setdefault(row["session_id"], []).append(row)
    return {"metrics": metrics, "sessions": sessions, "invalid_lines": invalid}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="汇总 JSONL 的 run 延迟（最近秩 P50/P95，重复行按 run 去重）"
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(args.paths)
    except OSError as exc:
        parser.exit(2, f"无法读取日志：{exc}\n")
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
