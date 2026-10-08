from pathlib import Path

import yaml

from app.settings import CONFIG_DIR


class ConfigError(ValueError):
    pass


HANDLERS = {
    "logistics.query": "get_order",
    "warranty.check": "get_order",
    "service_order.create": "create_service_order",
}
GATE_CHECKS = ["eligibility", "evidence", "safety", "idempotency"]
# 主办方工具只收单：不承诺发货或退款时效。
SUBMITTED_NEXT_STEP = "服务单已提交，人工处理中；处理结果会回到本会话，请保留服务单号"


class ActionRegistry:
    def __init__(self, config=None):
        config = (
            config
            if config is not None
            else yaml.safe_load((CONFIG_DIR / "actions.yaml").read_text())
        )
        self.version = str(config["version"])
        self.actions = config["actions"]
        for name, spec in self.actions.items():
            if HANDLERS.get(name) != spec.get("backend") or spec.get("kind") not in {"read", "write"}:
                raise ConfigError("未注册的动作或后端")
            if not isinstance(spec.get("timeout_ms"), int) or not 0 < spec["timeout_ms"] <= 30000:
                raise ConfigError("timeout_ms 必须在 1–30000 之间")
            if name == "service_order.create" and spec["kind"] != "write":
                raise ConfigError("写操作不能降级为只读")
            if spec["kind"] == "write" and (not spec.get("requires") or not spec.get("idempotency")):
                raise ConfigError("write 必须有 requires 和 idempotency")
            if spec["kind"] == "write" and spec["requires"] != {"checks": GATE_CHECKS, "user_confirmed": True}:
                raise ConfigError("写操作授权约束不得缺失或放宽")

    @classmethod
    def from_yaml(cls, path: Path):
        return cls(yaml.safe_load(path.read_text()))

    def spec(self, kind):
        if kind not in self.actions:
            raise ConfigError("未注册动作")
        return self.actions[kind]

