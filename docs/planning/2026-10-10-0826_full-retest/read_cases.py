"""Read complete customer-facing evidence and compact task states."""
import argparse
import json
from pathlib import Path


def show(folder, first, last):
    for i in range(first, last + 1):
        path = folder / f"T{i}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text())
        if not record.get("complete"):
            continue
        print(json.dumps({
            "id": record["id"], "input": record["input"], "intent": record.get("intent"),
            "stop": record.get("stop_reason"), "reply": record.get("visible_text"),
            "cards": [{key: step.get(key) for key in ("plan_id", "step_id", "kind", "instruction", "context", "options", "media", "caution", "expected_result")}
                      for step in record.get("step_cards", [])],
            "case_states": [case["status"] for case in record.get("cases", [])],
            "tasks": [{key: task.get(key) for key in ("intent", "status", "request_quote", "answer_request")}
                      for issue in record.get("snapshot", {}).get("issues", []) for task in issue.get("task_queue", [])],
        }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--last", type=int, default=63)
    args = parser.parse_args()
    show(args.folder, args.first, args.last)
