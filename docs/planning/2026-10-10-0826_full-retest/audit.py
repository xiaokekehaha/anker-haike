"""Summarize collected evidence without inferring semantic correctness."""
import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path


RESPONSIBILITIES = {
    "系统需修", "知识缺口已确认", "知识根因待查", "源文疑点待核",
    "明确执行边界", "等待用户或后续验证", "当前诉求已回应",
}
FACTORS = {
    "混合知识节点", "已知事实未消费", "引导性追问", "完成状态不一致", "原问题被覆盖",
    "QA覆盖缺口", "源文缺引用", "证据不足待查", "术语待核", "输入歧义", "记录待核",
    "审批权限", "实体维修", "安全交接", "工具未接入", "保修政策", "待事实", "待确认",
    "待材料", "等待继续", "模拟排障未解", "正常说明", "投诉承接", "历史缺陷开放",
}


def audit(folder, previous):
    records = [json.loads((folder / f"T{i}.json").read_text()) for i in range(1, 64)]
    baseline = json.loads((previous / "version-after.json").read_text())
    before = json.loads((folder / "version-before.json").read_text())
    after = json.loads((folder / "version-after.json").read_text())
    metadata = json.loads((folder / "run-metadata.json").read_text())
    validation = json.loads((folder / "validation.json").read_text())
    times = sorted(record["seconds"] for record in records)
    result = {
        "cases": len(records),
        "complete": sum(record.get("complete", False) for record in records),
        "evidence_valid": validation["evidence_valid"],
        "behavior_flags": validation["behavior_flags"],
        "production_files_equal_to_previous": baseline["local"] == before["local"],
        "same_container_as_previous": baseline["identity"] == before["identity"],
        "runtime_stable": before["runtime"] == after["runtime"] and before["identity"] == after["identity"],
        "worktree_stable": before["local"] == after["local"],
        "production_fingerprint": hashlib.sha256(json.dumps(after["local"], sort_keys=True).encode()).hexdigest(),
        "started_at": metadata["started_at"],
        "finished_at": metadata["finished_at"],
        "stop_distribution": dict(Counter(record["stop_reason"] for record in records)),
        "action_cards": sum(step.get("kind", "action") == "action" for record in records for step in record.get("step_cards", [])),
        "all_cards": sum(len(record.get("step_cards", [])) for record in records),
        "journey_seconds": {"median": statistics.median(times), "p95": times[math.ceil(len(times) * .95) - 1], "max": max(times)},
        "latency_note": "从首条消息到评测停止，含自动反馈和采证等待；不是首字延迟，不能与单轮回答速度混用。",
    }
    review = folder.parent / "review.md"
    if review.exists():
        rows = re.findall(r"^\| T(\d+) \| ([^|]+) \|", review.read_text(), re.M)
        result["review_covers_63_unique_cases"] = len(rows) == 63 and {int(i) for i, _ in rows} == set(range(1, 64))
        counts = Counter(label.strip() for _, label in rows)
        if not result["review_covers_63_unique_cases"] or set(counts) - {"可接受", "需改进", "资料待核"}:
            raise ValueError("review must cover 63 unique cases with recognized verdicts before calculating rates")
        result["review_distribution"] = dict(counts)
        total = len(records)
        rated = total - counts["资料待核"]
        ratios = {
            "review_acceptance_all_cases": (counts["可接受"], total),
            "needs_improvement_all_cases": (counts["需改进"], total),
            "unverified_source_all_cases": (counts["资料待核"], total),
            "review_acceptance_excluding_unverified": (counts["可接受"], rated),
            "technical_completion_without_errors": (sum(
                record.get("complete", False) and not record.get("errors")
                and record.get("stop_reason") not in {"collection_error", "event_error", "turn_limit"}
                for record in records
            ), total),
            "human_handoff_share": (sum(record.get("stop_reason") == "awaiting_human" for record in records), total),
        }
        result["rates"] = {name: {"numerator": numerator, "denominator": denominator,
                                  "percent": round(100 * numerator / denominator, 2) if denominator else None}
                           for name, (numerator, denominator) in ratios.items()}
        result["rate_scope"] = "现有逐案评审的已覆盖内容合格率，综合回答、流程、交互及状态；不是独立事实正确率、设备解决率或稳定生产正确率。"
        ledger = folder.parent / "responsibility-review.md"
        if ledger.exists():
            case_rows = [line.strip().strip("|").split("|") for line in ledger.read_text().splitlines()
                         if re.match(r"^\| T\d+ \|", line)]
            if len(case_rows) != total or any(len(row) != 5 for row in case_rows):
                raise ValueError("responsibility ledger must contain exactly 63 five-column case rows")
            quality = {f"T{i}": label.strip() for i, label in rows}
            primary = {}
            factors = {}
            case_factors = {}
            seen = set()
            for raw in case_rows:
                case_id, verdict, category, factor_text, evidence = (cell.strip() for cell in raw)
                tags = factor_text.split(";")
                if case_id in seen or case_id not in quality or quality[case_id] != verdict:
                    raise ValueError(f"duplicate, unknown, or inconsistent case: {case_id}")
                if category not in RESPONSIBILITIES or set(tags) - FACTORS or len(tags) != len(set(tags)) or not evidence:
                    raise ValueError(f"invalid responsibility, factors, or missing evidence: {case_id}")
                if (category == "系统需修") != (verdict == "需改进"):
                    raise ValueError(f"confirmed system defects must remain in the improvement group: {case_id}")
                seen.add(case_id)
                case_factors[case_id] = set(tags)
                primary.setdefault(category, []).append(case_id)
                for tag in tags:
                    factors.setdefault(tag, []).append(case_id)
            if seen != set(quality):
                raise ValueError("responsibility ledger and quality review must cover the same cases")
            result["responsibility_covers_63_unique_cases"] = True
            result["responsibility_distribution"] = {
                name: {"cases": ids, "numerator": len(ids), "denominator": total,
                       "percent": round(100 * len(ids) / total, 2)}
                for name, ids in primary.items()
            }
            result["coexisting_factors"] = {
                name: {"cases": ids, "count": len(ids)} for name, ids in factors.items()
            }
            result["responsibility_scope"] = "主组每案一次，按已证实系统缺陷优先分派；因素允许重叠，不可相加。待查不是已证实缺失，执行边界不是所有 agent 无法解决的全集。"
            result["historical_defects_not_reproduced"] = factors.get("历史缺陷开放", [])
            records_by_id = {record["id"]: record for record in records}
            waiting = {}
            for case_id in primary.get("等待用户或后续验证", []):
                tags = case_factors[case_id]
                if "待事实" in tags:
                    subgroup = "事实或记录补充"
                elif "待确认" in tags:
                    subgroup = "方案确认"
                elif "模拟排障未解" in tags and records_by_id[case_id]["stop_reason"] == "awaiting_upload_receipt":
                    subgroup = "模拟排障后凭证"
                elif "待材料" in tags:
                    subgroup = "其他材料"
                elif "等待继续" in tags:
                    subgroup = "继续意愿"
                else:
                    raise ValueError(f"missing waiting reason: {case_id}")
                waiting.setdefault(subgroup, []).append(case_id)
            result["waiting_breakdown"] = {name: {"cases": ids, "count": len(ids)} for name, ids in waiting.items()}
    (folder.parent / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("previous", type=Path)
    args = parser.parse_args()
    audit(args.folder, args.previous)
