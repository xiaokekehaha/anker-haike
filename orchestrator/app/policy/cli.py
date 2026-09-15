import argparse
import json
from pathlib import Path

import yaml

from .engine import PolicyEngine
from .loader import PolicyLoader
from .models import PolicyInput


def main():
    parser = argparse.ArgumentParser(description="演示政策校验与解释（待真实 SOP 替换）")
    parser.add_argument("command", choices=["lint", "explain"])
    parser.add_argument("--case", type=Path)
    args = parser.parse_args()
    bundle = PolicyLoader().load()
    if args.command == "lint":
        print("policy valid:", bundle["policy"]["version"])
    else:
        if not args.case:
            parser.error("explain requires --case")
        data = yaml.safe_load(args.case.read_text())
        cases = data.get("cases", [data])
        for case in cases:
            result = PolicyEngine(bundle).decide(
                PolicyInput.model_validate(case.get("input", case))
            )
            print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
