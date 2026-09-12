"""最简告警（票 50，04 §3）：四条规则、一个冷却期、两种投递（IM webhook / 邮件），无外部告警系统。

规则（阈值均可由环境变量覆盖，见 settings.alert_*）：
- model_chain_failed：ModelRouter 整条链连续失败 ≥ 3 次（record("model_call", status!=ok)）。
- retrieval_empty_rate：最近 20 次知识检索里 no_match / unavailable 占比 > 50%（至少 10 次样本）。
- queue_rejections：全局有界队列最近 60 s 拒绝率 > 20%（至少 5 次拒绝）。
- health_check_failed：/health 聚合状态连续 ≥ 3 次非 ok（后台每 60 s 探测一次）。

投递：每条规则 5 分钟冷却；恢复时发一条 resolved。无论有没有配置投递渠道，都写结构化日志 event=alert，
/health 的 alerts 块给出活动告警与计数器。投递失败只记日志，不影响业务。
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import time
from collections import deque
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

log = logging.getLogger("alerts")

EMPTY_STATUSES = {"no_match", "unavailable"}


class AlertSink(Protocol):
    name: str

    async def send(self, alert: dict[str, Any]) -> bool: ...


def format_text(alert: dict[str, Any]) -> str:
    state = "已恢复" if alert.get("resolved") else "触发"
    return (
        f"[haike] {alert['rule']} {state}\n"
        f"{alert['summary']}\n"
        f"时间 {alert['at']}  环境 {alert.get('env', '-')}"
    )


class WebhookSink:
    """通用 JSON webhook：同时带飞书 / 钉钉 / 企业微信 / Slack 都能显示的 text 字段与完整 alert。"""

    name = "webhook"

    def __init__(self, url: str, timeout_s: float = 5.0, client: httpx.AsyncClient | None = None):
        self.url = url
        self.timeout_s = timeout_s
        self._client = client

    async def send(self, alert: dict[str, Any]) -> bool:
        text = format_text(alert)
        payload = {
            "msg_type": "text",
            "msgtype": "text",
            "text": {"content": text, "text": text},
            "content": text,
            "alert": alert,
        }
        client = self._client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            r = await client.post(self.url, json=payload)
            return r.status_code < 300
        finally:
            if self._client is None:
                await client.aclose()


class EmailSink:
    name = "email"

    def __init__(
        self, host: str, port: int, sender: str, recipients: list[str],
        user: str = "", password: str = "", use_tls: bool = True,
    ):
        self.host, self.port, self.sender = host, port, sender
        self.recipients, self.user, self.password, self.use_tls = recipients, user, password, use_tls

    def _send_sync(self, alert: dict[str, Any]) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"[haike alert] {alert['rule']} {'resolved' if alert.get('resolved') else 'firing'}"
        msg["From"], msg["To"] = self.sender, ", ".join(self.recipients)
        msg.set_content(format_text(alert) + "\n\n" + repr(alert.get("detail", {})))
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)

    async def send(self, alert: dict[str, Any]) -> bool:
        await asyncio.to_thread(self._send_sync, alert)
        return True


@dataclass
class Thresholds:
    model_fail_streak: int = 3
    retrieval_window: int = 20
    retrieval_min_samples: int = 10
    retrieval_empty_rate: float = 0.5
    queue_window_s: float = 60.0
    queue_min_rejects: int = 5
    queue_reject_rate: float = 0.2
    health_fail_streak: int = 3
    cooldown_s: float = 300.0


@dataclass
class RuleState:
    active: bool = False
    last_fired: float | None = None
    fired_total: int = 0
    suppressed_total: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


class AlertManager:
    def __init__(
        self,
        sinks: list[AlertSink] | None = None,
        thresholds: Thresholds | None = None,
        *,
        env: str = "dev",
        clock=time.monotonic,
    ):
        self.sinks = list(sinks or [])
        self.t = thresholds or Thresholds()
        self.env = env
        self._clock = clock
        self.rules: dict[str, RuleState] = {
            k: RuleState()
            for k in ("model_chain_failed", "retrieval_empty_rate", "queue_rejections", "health_check_failed")
        }
        self._model_streak = 0
        self._retrieval: deque[str] = deque(maxlen=self.t.retrieval_window)
        self._queue_events: deque[tuple[float, bool]] = deque()  # (ts, rejected?)
        self._queue_seen_admitted: int | None = None
        self._health_streak = 0
        self.sent: list[dict[str, Any]] = []  # 最近投递记录（测试 / 排查用，最多 50 条）
        self._tasks: set[asyncio.Task] = set()

    # ---------------- 观察入口 ----------------

    def observe(self, event: str, data: dict[str, Any]) -> None:
        """record() 的钩子：按事件名分发；任何异常不外抛。"""
        try:
            if event == "model_call":
                self.observe_model_call(str(data.get("status") or "ok"), str(data.get("task") or ""))
            elif event == "knowledge_search":
                self.observe_knowledge_search(str(data.get("status") or ""))
            elif event == "model_queue_full":
                self.observe_queue(rejected=True, admitted_total=data.get("admitted_total"))
        except Exception:
            log.exception("alert observe failed")

    def observe_model_call(self, status: str, task: str = "") -> None:
        if status == "cancelled":
            return  # 用户取消不是故障
        if status == "ok":
            self._model_streak = 0
            self._resolve("model_chain_failed", {"task": task})
            return
        self._model_streak += 1
        if self._model_streak >= self.t.model_fail_streak:
            self._fire(
                "model_chain_failed",
                f"模型链连续失败 {self._model_streak} 次（最近 task={task}），所有厂商均不可用或预算耗尽",
                {"streak": self._model_streak, "task": task},
            )

    def observe_knowledge_search(self, status: str) -> None:
        self._retrieval.append(status)
        n = len(self._retrieval)
        if n < self.t.retrieval_min_samples:
            return
        empty = sum(1 for s in self._retrieval if s in EMPTY_STATUSES)
        rate = empty / n
        if rate > self.t.retrieval_empty_rate:
            self._fire(
                "retrieval_empty_rate",
                f"最近 {n} 次知识检索中 {empty} 次为空 / 不可用（{rate:.0%}），检查 WeKnora 与知识库范围",
                {"window": n, "empty": empty, "rate": round(rate, 3)},
            )
        else:
            self._resolve("retrieval_empty_rate", {"window": n, "empty": empty, "rate": round(rate, 3)})

    def observe_queue(self, *, rejected: bool, admitted_total: int | None = None) -> None:
        now = self._clock()
        if admitted_total is not None:
            if self._queue_seen_admitted is not None:
                for _ in range(max(0, admitted_total - self._queue_seen_admitted)):
                    self._queue_events.append((now, False))
            self._queue_seen_admitted = admitted_total
        self._queue_events.append((now, rejected))
        while self._queue_events and now - self._queue_events[0][0] > self.t.queue_window_s:
            self._queue_events.popleft()
        rejects = sum(1 for _, r in self._queue_events if r)
        total = len(self._queue_events)
        rate = rejects / total if total else 0.0
        if rejects >= self.t.queue_min_rejects and rate > self.t.queue_reject_rate:
            self._fire(
                "queue_rejections",
                f"最近 {int(self.t.queue_window_s)} s 内模型队列拒绝 {rejects}/{total}（{rate:.0%}），容量不足或上游变慢",
                {"rejects": rejects, "total": total, "rate": round(rate, 3)},
            )
        elif not rejected:
            self._resolve("queue_rejections", {"rejects": rejects, "total": total})

    def observe_health(self, ok: bool, detail: dict[str, Any] | None = None) -> None:
        if ok:
            self._health_streak = 0
            self._resolve("health_check_failed", detail or {})
            return
        self._health_streak += 1
        if self._health_streak >= self.t.health_fail_streak:
            self._fire(
                "health_check_failed",
                f"/health 连续 {self._health_streak} 次非 ok：{detail or {}}",
                {"streak": self._health_streak, **(detail or {})},
            )

    # ---------------- 触发 / 恢复 / 投递 ----------------

    def _fire(self, rule: str, summary: str, detail: dict[str, Any]) -> None:
        st = self.rules[rule]
        now = self._clock()
        st.detail = detail
        was_active = st.active
        st.active = True
        if was_active and st.last_fired is not None and now - st.last_fired < self.t.cooldown_s:
            st.suppressed_total += 1
            return
        st.last_fired = now
        st.fired_total += 1
        self._emit({"rule": rule, "summary": summary, "detail": detail, "resolved": False})

    def _resolve(self, rule: str, detail: dict[str, Any]) -> None:
        st = self.rules[rule]
        if not st.active:
            return
        st.active = False
        self._emit({"rule": rule, "summary": f"{rule} 已恢复", "detail": detail, "resolved": True})

    def _emit(self, alert: dict[str, Any]) -> None:
        alert = {**alert, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "env": self.env}
        log.warning(
            "ALERT %s %s: %s", alert["rule"], "resolved" if alert["resolved"] else "firing", alert["summary"],
            extra={"event": "alert", **alert},
        )
        self.sent.append(alert)
        del self.sent[:-50]
        for sink in self.sinks:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                continue  # 同步上下文（测试）：只记日志
            task = loop.create_task(self._deliver(sink, alert))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _deliver(self, sink: AlertSink, alert: dict[str, Any]) -> None:
        try:
            ok = await sink.send(alert)
            log.info("alert delivered sink=%s rule=%s ok=%s", sink.name, alert["rule"], ok,
                     extra={"event": "alert_delivered", "sink": sink.name, "rule": alert["rule"], "ok": ok})
        except Exception as exc:  # noqa: BLE001
            log.warning("alert delivery failed sink=%s rule=%s err=%s", sink.name, alert["rule"], str(exc)[:200],
                        extra={"event": "alert_delivery_failed", "sink": sink.name, "rule": alert["rule"]})

    async def drain(self, timeout_s: float = 5.0) -> None:
        if self._tasks:
            await asyncio.wait(list(self._tasks), timeout=timeout_s)

    def snapshot(self) -> dict[str, Any]:
        return {
            "sinks": [s.name for s in self.sinks],
            "active": [k for k, v in self.rules.items() if v.active],
            "rules": {
                k: {"active": v.active, "fired_total": v.fired_total, "suppressed_total": v.suppressed_total,
                    **({"detail": v.detail} if v.active else {})}
                for k, v in self.rules.items()
            },
            "model_fail_streak": self._model_streak,
            "health_fail_streak": self._health_streak,
        }


# ---------------- 进程级实例 ----------------

_manager: AlertManager | None = None


def set_alert_manager(manager: AlertManager | None) -> None:
    global _manager
    _manager = manager


def get_alert_manager() -> AlertManager | None:
    return _manager


def observe(event: str, data: dict[str, Any]) -> None:
    if _manager is not None:
        _manager.observe(event, data)


def build_from_settings(s) -> AlertManager:
    sinks: list[AlertSink] = []
    if s.alert_webhook_url:
        sinks.append(WebhookSink(s.alert_webhook_url))
    if s.alert_email_to and s.alert_smtp_host:
        sinks.append(
            EmailSink(
                s.alert_smtp_host, s.alert_smtp_port, s.alert_smtp_from or s.alert_smtp_user,
                [x.strip() for x in s.alert_email_to.split(",") if x.strip()],
                user=s.alert_smtp_user, password=s.alert_smtp_password, use_tls=s.alert_smtp_tls,
            )
        )
    t = Thresholds(
        model_fail_streak=s.alert_model_fail_streak,
        retrieval_empty_rate=s.alert_retrieval_empty_rate,
        queue_reject_rate=s.alert_queue_reject_rate,
        health_fail_streak=s.alert_health_fail_streak,
        cooldown_s=s.alert_cooldown_s,
    )
    return AlertManager(sinks, t, env=s.app_env)


async def health_watch_loop(aggregator, manager: AlertManager, interval_s: float) -> None:
    """后台探测 /health 聚合状态，连续非 ok 触发 health_check_failed。"""
    while True:
        await asyncio.sleep(interval_s)
        try:
            body = await aggregator.snapshot(force=True)
            comps = body.get("components", {})
            bad = {k: v.get("status") for k, v in comps.items() if isinstance(v, dict) and v.get("status") not in ("ok", None)}
            manager.observe_health(body.get("status") == "ok", {"components": bad} if bad else None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            manager.observe_health(False, {"error": str(exc)[:200]})
