"""规则服务骨架与 CP-in（09 §1、03 §1.7）。

- 字典 `config/rules/safety_terms.yaml` 配置化，按文件 mtime 热加载（每次判定前廉价 stat）。
- `check_in()`：对用户文本 / 图片观察 / 动作及备注做 R3 / R4 / R6 判定，返回带 rule_id、source、ts 的命中。
- 每次命中写结构化日志（logger `rules`，extra 含 checkpoint / rule_id / source / term）。
- CP-pre-step、CP-verify（R1 / R2 / R5 / R7 / R8）在票 25 / 33 / 36 补充，接口预留在此。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("rules")

Source = Literal["text", "observation", "action", "action_note"]
Action = Literal["escalate", "flag"]


class RulesError(RuntimeError):
    pass


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    action: Action
    priority: int = Field(default=100, ge=0)
    text_terms: list[str] = Field(default_factory=list)
    observation_terms: list[str] = Field(default_factory=list)
    action_kinds: list[str] = Field(default_factory=list)


class PreStepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    high_risk_actions: list[str] = Field(default_factory=list)


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    rules: dict[str, RuleSpec]
    pre_step: PreStepSpec = Field(default_factory=PreStepSpec)


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    source: Source
    term: str
    ts: str
    action: Action

    def as_flag(self) -> dict[str, Any]:
        """写入会话状态 safety_flags 的形状。"""
        return {"rule_id": self.rule_id, "source": self.source, "term": self.term, "ts": self.ts}


@dataclass(frozen=True)
class PreStepResult:
    action: Literal["ok", "drop", "escalate"]
    rule_id: str | None
    term: str | None


@dataclass
class CheckpointResult:
    checkpoint: str
    hits: list[RuleHit] = field(default_factory=list)

    @property
    def escalate(self) -> bool:
        return any(h.action == "escalate" for h in self.hits)

    @property
    def rule_ids(self) -> list[str]:
        return sorted({h.rule_id for h in self.hits})

    @property
    def flags(self) -> list[dict[str, Any]]:
        return [h.as_flag() for h in self.hits]


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub("", text).casefold()


def load_rules_config(path: str | Path) -> RulesConfig:
    path = Path(path)
    if not path.is_file():
        raise RulesError(f"rules config not found: {path}")
    try:
        cfg = RulesConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as exc:
        raise RulesError(f"rules config invalid ({path}): {exc}") from exc
    bad = [rid for rid in cfg.rules if not re.fullmatch(r"R\d+[a-z]?", rid)]
    if bad:
        raise RulesError(f"rules config invalid ({path}): bad rule ids {bad}")
    return cfg


class RulesService:
    def __init__(self, path: str | Path, *, hot_reload: bool = True):
        self._path = Path(path)
        self._hot = hot_reload
        self._mtime = 0.0
        self._load()

    # ---- 加载 ----
    def _load(self) -> None:
        cfg = load_rules_config(self._path)
        self._mtime = os.stat(self._path).st_mtime
        self.version = cfg.version
        self.pre_step = cfg.pre_step
        self.rules = dict(sorted(cfg.rules.items(), key=lambda kv: kv[1].priority))
        self._text_index = [
            (rid, term, _norm(term)) for rid, r in self.rules.items() for term in r.text_terms
        ]
        self._obs_index = [
            (rid, term, term.casefold())
            for rid, r in self.rules.items()
            for term in r.observation_terms
        ]
        log.info("rules loaded version=%s rules=%s", self.version, list(self.rules))

    def reload_if_changed(self) -> bool:
        try:
            mtime = os.stat(self._path).st_mtime
        except FileNotFoundError:
            return False
        if mtime == self._mtime:
            return False
        try:
            self._load()
        except RulesError as exc:
            # 热加载失败保留旧字典，避免运行中因编辑错误丢失安全判定
            log.error("rules reload failed, keeping version=%s: %s", self.version, exc)
            self._mtime = mtime
            return False
        return True

    # ---- CP-in ----
    def check_in(
        self,
        *,
        text: str | None = None,
        observations: list[str] | None = None,
        action_kind: str | None = None,
        action_note: str | None = None,
        session_id: str | None = None,
        now: datetime | None = None,
    ) -> CheckpointResult:
        if self._hot:
            self.reload_if_changed()
        ts = (now or datetime.now(UTC)).isoformat()
        result = CheckpointResult("cp_in")
        if text:
            result.hits += self._match_text(text, "text", ts)
        if action_note:
            result.hits += self._match_text(action_note, "action_note", ts)
        for obs in observations or []:
            low = obs.casefold()
            for rid, term, nterm in self._obs_index:
                if nterm in low:
                    result.hits.append(
                        RuleHit(rid, "observation", term, ts, self.rules[rid].action)
                    )
        if action_kind:
            for rid, r in self.rules.items():
                if action_kind in r.action_kinds:
                    result.hits.append(RuleHit(rid, "action", action_kind, ts, r.action))
        # 同一规则同一来源只留一条，按规则优先级排序
        dedup: dict[tuple[str, str], RuleHit] = {}
        for h in result.hits:
            dedup.setdefault((h.rule_id, h.source), h)
        order = {rid: i for i, rid in enumerate(self.rules)}
        result.hits = sorted(dedup.values(), key=lambda h: (order[h.rule_id], h.source))
        for h in result.hits:
            log.info(
                "rule_hit checkpoint=cp_in rule_id=%s source=%s term=%s action=%s session=%s",
                h.rule_id,
                h.source,
                h.term,
                h.action,
                session_id,
                extra={
                    "event": "rule_hit",
                    "checkpoint": "cp_in",
                    "rule_id": h.rule_id,
                    "source": h.source,
                    "term": h.term,
                    "action": h.action,
                    "session_id": session_id,
                    "rules_version": self.version,
                },
            )
        return result

    # ---- CP-pre-step（09 §1；票 34）----
    def check_pre_step(
        self, *, instruction: str, title: str = "", caution: str | None, session_id: str | None = None
    ) -> PreStepResult:
        """步骤命中安全词或无 caution 的高危动作时丢弃；步骤文字不是用户风险事实。"""
        if self._hot:
            self.reload_if_changed()
        norm = _norm(f"{title} {instruction}")
        for rid, term, nterm in self._text_index:
            if rid == "R4" and nterm and nterm in norm:
                log.info(
                    "rule_hit checkpoint=cp_pre_step rule_id=R4 source=step term=%s action=drop session=%s",
                    term,
                    session_id,
                    extra={"event": "rule_hit", "checkpoint": "cp_pre_step", "rule_id": "R4", "source": "step", "term": term, "action": "drop", "session_id": session_id},
                )
                return PreStepResult("drop", "R4", term)
        risky = [w for w in self.pre_step.high_risk_actions if _norm(w) in norm]
        if risky and not (caution or "").strip():
            log.info(
                "rule_hit checkpoint=cp_pre_step rule_id=HR source=step term=%s action=drop session=%s",
                risky[0],
                session_id,
                extra={"event": "rule_hit", "checkpoint": "cp_pre_step", "rule_id": "HR", "source": "step", "term": risky[0], "action": "drop", "session_id": session_id},
            )
            return PreStepResult("drop", "HR", risky[0])
        return PreStepResult("ok", None, None)

    def _match_text(self, text: str, source: Source, ts: str) -> list[RuleHit]:
        norm = _norm(text)
        return [
            RuleHit(rid, source, term, ts, self.rules[rid].action)
            for rid, term, nterm in self._text_index
            if nterm and nterm in norm
        ]


# ---- 进程级单例（图节点里取用；测试可注入）----
_service: RulesService | None = None


def set_rules_service(service: RulesService | None) -> None:
    global _service
    _service = service


def get_rules_service() -> RulesService:
    global _service
    if _service is None:
        from app.settings import settings

        _service = RulesService(settings.rules_config_path)
    return _service
