"""Durable business subjects, independent of the language model's history window.

This module owns identifier provenance, focus and action binding. Callers never
combine old query arguments, receipts and conversation text themselves.
"""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.actions.params import IDENTIFIER, classify

KEYS = ("order_no", "tracking_no", "service_order_no")


class Value(BaseModel):
    value: str
    source: Literal["user", "backend", "legacy"]
    input_id: str
    observed_at: str | None = None


class Subject(BaseModel):
    identifiers: dict[str, Value] = Field(default_factory=dict)
    facts: dict[str, Value] = Field(default_factory=dict)


class Binding(BaseModel):
    status: Literal["ready", "missing", "ambiguous"]
    params: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


class BusinessContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    subjects: dict[str, Subject] = Field(default_factory=dict)
    active_subject_id: str | None = None
    status: Literal["resolved", "missing", "ambiguous"] = "missing"
    candidate_ids: list[str] = Field(default_factory=list)
    last_input_id: str | None = None

    @classmethod
    def restore(cls, state):
        if state.get("business_context") is not None:
            return cls.model_validate(state["business_context"])
        # A single compatibility seam; subsequent turns only read the new state.
        from app.conversation.business_migration import restore_legacy_params

        params = restore_legacy_params({**state, "text": ""})
        result = cls()
        if params:
            result._select(params, "legacy", state.get("input_id", "migration"))
        return result

    def _select(self, params, source, input_id):
        matches = [
            sid
            for sid, subject in self.subjects.items()
            if any(
                k in subject.identifiers and subject.identifiers[k].value == v
                for k, v in params.items()
            )
            and not any(
                k in subject.identifiers and subject.identifiers[k].value != v
                for k, v in params.items()
            )
        ]
        sid = (
            matches[0]
            if len(matches) == 1
            else uuid5(NAMESPACE_URL, repr(sorted(params.items()))).hex
        )
        subject = self.subjects.setdefault(sid, Subject())
        for key, value in params.items():
            if key not in subject.identifiers:
                subject.identifiers[key] = Value(value=value, source=source, input_id=input_id)
        self.active_subject_id, self.status, self.candidate_ids = sid, "resolved", []
        return sid

    def accept(self, text, input_id, reference=None):
        if self.last_input_id == input_id:
            return self
        result = self.model_copy(deep=True)
        result.last_input_id = input_id
        explicit: dict[str, list[str]] = {}
        for match in IDENTIFIER.finditer(text):
            key, value = classify(match.group())
            if value not in explicit.setdefault(key, []):
                explicit[key].append(value)
        if len(explicit.get("order_no", [])) == 1 and len(explicit.get("tracking_no", [])) > 1:
            # 一个订单号 + 多个运单号（T2：配件包与主机分开发）：运单是这个订单的多个包裹，不是多个对象
            explicit = {k: v for k, v in explicit.items() if k != "tracking_no"}
        if any(len(values) > 1 for values in explicit.values()):
            candidates = [
                result._select({key: value}, "user", input_id)
                for key, values in explicit.items()
                for value in values
            ]
            result.status, result.active_subject_id = "ambiguous", None
            result.candidate_ids = list(dict.fromkeys(candidates))
        elif explicit:
            result._select({key: values[0] for key, values in explicit.items()}, "user", input_id)
        elif reference and reference.get("quote") and reference["quote"] in text:
            target = reference.get("subject_id")
            if target and target in result.subjects:
                result.active_subject_id, result.status = target, "resolved"
                result.candidate_ids = []
            elif target:
                result.active_subject_id, result.status = None, "ambiguous"
                result.candidate_ids = list(result.subjects)
            elif reference.get("relation") == "other":
                result.active_subject_id, result.status, result.candidate_ids = None, "missing", []
            elif reference.get("relation") == "ambiguous":
                result.active_subject_id = None
                result.status = "ambiguous" if len(result.subjects) >= 2 else "missing"
                result.candidate_ids = list(result.subjects)
        return result

    def bind(self, action):
        if self.status == "ambiguous":
            candidates = set(self.candidate_ids).intersection(self.subjects)
            return Binding(status="ambiguous") if len(candidates) >= 2 else Binding(status="missing", missing_fields=["order_no"])
        subject = self.subjects.get(self.active_subject_id)
        values = {k: v.value for k, v in subject.identifiers.items()} if subject else {}
        keys = (
            ("tracking_no", "service_order_no", "order_no")
            if action == "logistics.query"
            else ("order_no",)
        )
        for key in keys:
            if values.get(key):
                params = {key: values[key]}
                if key == "tracking_no" and values.get("order_no"):
                    params["order_no"] = values["order_no"]
                return Binding(status="ready", params=params)
        return Binding(status="missing", missing_fields=["order_no"])

    def for_order(self, order_no):
        """Select a workflow's bound object on a copy; never move chat focus."""
        result = self.model_copy(deep=True)
        result._select({"order_no": order_no}, "legacy", self.last_input_id or "binding")
        return result

    def reference(self):
        """Persist object selection, without copying facts into a task."""
        return {
            "status": self.status,
            "subject_id": self.active_subject_id,
            "candidate_ids": list(self.candidate_ids),
        }

    def for_reference(self, reference):
        result = self.model_copy(deep=True)
        reference = reference or {}
        target = reference.get("subject_id")
        result.active_subject_id = None
        result.candidate_ids = []
        result.status = "missing"
        if reference.get("status") == "resolved" and target in result.subjects:
            result.active_subject_id, result.status = target, "resolved"
        elif reference.get("status") in {"resolved", "ambiguous"}:
            result.status = "ambiguous"
            result.candidate_ids = [sid for sid in reference.get("candidate_ids", []) if sid in result.subjects]
        return result

    def remember(self, values, input_id, *, source="user", order_no=None):
        result = self.model_copy(deep=True)
        target = result.for_order(order_no) if order_no else result
        subject = target.subjects.get(target.active_subject_id)
        if target.status != "resolved" or subject is None:
            return result
        for key, value in values.items():
            if key not in {"address", "serial_number", "seller", "country"} or not value:
                continue
            old = subject.facts.get(key)
            if not old or old.source != "backend":
                subject.facts[key] = Value(value=str(value), source=source, input_id=input_id)
        result.subjects.update(target.subjects)
        return result

    def focused(self):
        """Seed a new issue with the selected object, without unrelated subjects."""
        if self.status == "missing":
            return BusinessContext(last_input_id=self.last_input_id)
        if self.status != "resolved" or self.active_subject_id not in self.subjects:
            raise ValueError("a new service issue requires one resolved subject")
        return self.model_copy(
            deep=True,
            update={
                "subjects": {
                    self.active_subject_id: self.subjects[self.active_subject_id].model_copy(
                        deep=True
                    )
                },
                "candidate_ids": [],
            },
        )

    def observe(self, action, params, receipt, input_id):
        result = self.model_copy(deep=True)
        if action == "receipt.confirm":
            identifiers = {key: params[key] for key in KEYS if params.get(key)}
            if identifiers:
                result._select(identifiers, "user", input_id)
            return result
        observed = {k: receipt[k] for k in KEYS if receipt.get(k)}
        if any(observed.get(k) and observed[k] != v for k, v in params.items() if k in KEYS):
            raise ValueError("business receipt does not match requested identifiers")
        # A pending action retains its request subject when an inline query moves
        # conversation focus. Attach its result to that subject without moving focus.
        matches = [
            subject
            for subject in result.subjects.values()
            if any(
                k in subject.identifiers and subject.identifiers[k].value == v
                for k, v in params.items()
                if k in KEYS
            )
            and not any(
                k in subject.identifiers and subject.identifiers[k].value != v
                for k, v in params.items()
                if k in KEYS
            )
        ]
        if len(matches) != 1:
            raise ValueError("business observation requires one matching request subject")
        current = matches[0]
        if (
            observed.get("order_no")
            and current.identifiers.get("order_no")
            and current.identifiers["order_no"].value != observed["order_no"]
        ):
            raise ValueError("business receipt would relink a different order")
        for key, value in observed.items():
            current.identifiers[key] = Value(value=value, source="backend", input_id=input_id)
        data = receipt.get("data") or receipt
        fields = ("sku", "purchase_date", "warranty_end", "amount") if action == "warranty.check" else ("sku", "purchase_date", "warranty_end", "amount", "logistics_status") if action == "logistics.query" else ()
        for key in fields:
            value = data.get(key) or receipt.get(key)
            if value is not None:
                current.facts[key] = Value(
                    value=str(value), source="backend", input_id=input_id,
                    observed_at=receipt.get("updated_at") or data.get("updated_at"),
                )
        return result

    def projection(self):
        return {
            "status": self.status,
            "active_subject_id": self.active_subject_id,
            "active_subject": {
                key: value.value
                for key, value in self.subjects[self.active_subject_id].identifiers.items()
            }
            if self.active_subject_id in self.subjects
            else None,
            "subjects": {
                sid: {key: value.value for key, value in {**subject.facts, **subject.identifiers}.items()}
                for sid, subject in self.subjects.items()
            },
            "candidate_ids": self.candidate_ids,
        }
