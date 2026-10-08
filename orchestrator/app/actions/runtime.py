"""售后业务能力的进程内单例：业务后端（主办方订单 + 服务单）、动作执行器、案件服务。"""

from dataclasses import dataclass

from app.backends.service import MemoryBackend, PostgresBackend
from app.cases.service import CaseService
from app.cases.store import PostgresCaseStore

from .executor import ActionExecutor
from .store import PostgresExecutionStore


@dataclass
class L3Services:
    backend: MemoryBackend | PostgresBackend
    executor: ActionExecutor
    cases: CaseService


_services: L3Services | None = None


def configure(pool=None, *, memory=False):
    global _services
    if pool is None and not memory:
        _services = None
        return None
    backend = MemoryBackend() if memory else PostgresBackend(pool)
    executor = ActionExecutor(backend, None if memory else PostgresExecutionStore(pool))
    _services = L3Services(backend, executor, CaseService(None if memory else PostgresCaseStore(pool)))
    return _services


def get_services():
    return _services


def require_services():
    if _services is None:
        raise RuntimeError("L3 业务存储未就绪")
    return _services
