"""导出三份 JSON Schema 到 contracts/schema/。输出按键排序，重复执行结果稳定。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

from haike_contracts.actions import ActionConflict, ActionRequest, ActionResult
from haike_contracts.common import FaultLocalization, ImageQuality, WarrantyDecision
from haike_contracts.events import ServerEvent
from haike_contracts.snapshot import SessionSnapshot

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


class _Gen(GenerateJsonSchema):
    schema_dialect = "https://json-schema.org/draft/2020-12/schema"


def _wrap(title: str, schema: dict) -> dict:
    schema = {"$schema": _Gen.schema_dialect, "title": title, **schema}
    return schema


def build_schemas() -> dict[str, dict]:
    events = TypeAdapter(ServerEvent).json_schema(schema_generator=_Gen, mode="validation")
    for shared in (WarrantyDecision, FaultLocalization, ImageQuality):
        sub = shared.model_json_schema(schema_generator=_Gen, mode="validation")
        events.setdefault("$defs", {}).update(sub.pop("$defs", {}))
        events["$defs"][shared.__name__] = sub
    actions = TypeAdapter(ActionRequest).json_schema(schema_generator=_Gen, mode="validation")
    # 动作响应体也放进 actions.schema.json 的 $defs，前端一并生成类型
    for extra in (ActionResult, ActionConflict):
        sub = extra.model_json_schema(schema_generator=_Gen, mode="validation")
        defs = sub.pop("$defs", {})
        actions.setdefault("$defs", {}).update(defs)
        actions["$defs"][extra.__name__] = sub
    snapshot = SessionSnapshot.model_json_schema(schema_generator=_Gen, mode="validation")
    return {
        "events.schema.json": _wrap("ServerEvent", events),
        "actions.schema.json": _wrap("ActionRequest", actions),
        "snapshot.schema.json": _wrap("SessionSnapshot", snapshot),
    }


def render(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []
    for name, schema in build_schemas().items():
        path = SCHEMA_DIR / name
        text = render(schema)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                drift.append(name)
            continue
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    if drift:
        print("schema drift, run `make contracts`: " + ", ".join(drift), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
