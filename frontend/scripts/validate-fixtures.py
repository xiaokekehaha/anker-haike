"""用上游 Pydantic 契约验证与前端共用的协议样本；从仓库根目录 uv run --project contracts 执行。"""

import json
from pathlib import Path

from haike_contracts.events import EVENT_TYPES, ServerEventAdapter


def main() -> None:
    fixture_dir = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
    samples = json.loads((fixture_dir / "events.valid.json").read_text(encoding="utf-8"))
    if not isinstance(samples, list):
        raise TypeError("events.valid.json must contain an array")
    events = [ServerEventAdapter.validate_python(sample) for sample in samples]
    if {event.type for event in events} != set(EVENT_TYPES):
        raise ValueError("Shared fixtures must cover every event type")
    print(f"Shared fixtures: {len(events)} samples accepted by Pydantic; all event types covered.")


if __name__ == "__main__":
    main()
