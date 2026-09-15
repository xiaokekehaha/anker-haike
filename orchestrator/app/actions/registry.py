from pathlib import Path

import yaml

from app.settings import CONFIG_DIR


class ConfigError(ValueError):
    pass


FROM_STATE = {"product_confirmed.sku", "policy_decision.fault_class", "current_evidence_ids"}
HANDLERS = {
    "logistics.query": "get_shipment",
    "warranty.check": "get_order",
    "replacement.create": "create_service_order",
}


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
            if HANDLERS.get(name) != spec.get("backend") or spec.get("kind") not in {
                "read",
                "write",
            }:
                raise ConfigError("未注册的动作或后端")
            if not isinstance(spec.get("timeout_ms"), int) or not 0 < spec["timeout_ms"] <= 30000:
                raise ConfigError("timeout_ms 必须在 1–30000 之间")
            if name == "replacement.create" and spec["kind"] != "write":
                raise ConfigError("写操作不能降级为只读")
            estimate = spec.get("estimated_dispatch_working_days")
            if estimate is not None and (name != "replacement.create" or type(estimate) is not int or estimate <= 0):
                raise ConfigError("发出时间估计仅适用于换货，必须为正整数工作日")
            if spec["kind"] == "write" and (
                not spec.get("requires") or not spec.get("idempotency")
            ):
                raise ConfigError("write 必须有 requires 和 idempotency")
            if spec["kind"] == "write" and spec["requires"] != {
                "policy_auto_allowed": "replace",
                "receipt_status": ["order_verified"],
                "product_state": ["confirmed_sku"],
                "user_confirmed": True,
            }:
                raise ConfigError("写操作授权约束不得缺失或放宽")
            for param in spec.get("params", {}).values():
                if "from_state" in param and param["from_state"] not in FROM_STATE:
                    raise ConfigError("from_state 不在白名单")

    @classmethod
    def from_yaml(cls, path: Path):
        return cls(yaml.safe_load(path.read_text()))

    def spec(self, kind):
        if kind not in self.actions:
            raise ConfigError("未注册动作")
        return self.actions[kind]

    def dispatch_estimate(self, kind):
        days = self.spec(kind).get("estimated_dispatch_working_days")
        return {"working_days": days, "action": kind, "actions_version": self.version} if days is not None else None
