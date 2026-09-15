from dataclasses import dataclass

from app.backends.mock import MemoryBackend, MockBackend, load_config
from app.cases.service import CaseService
from app.cases.store import PostgresCaseStore
from app.policy.loader import PolicyLoader

from .executor import ActionExecutor
from .store import PostgresExecutionStore


@dataclass
class L3Services:
    backend: object
    executor: ActionExecutor
    cases: CaseService
    policy_loader: PolicyLoader


_services: L3Services | None = None


def configure(pool=None, *, memory=False):
    global _services
    if pool is None and not memory:
        _services = None
        return None
    backend = MemoryBackend() if memory else MockBackend(pool, load_config().get("faults", []))
    executor = ActionExecutor(backend, None if memory else PostgresExecutionStore(pool))
    _services = L3Services(
        backend, executor, CaseService(None if memory else PostgresCaseStore(pool)), PolicyLoader()
    )
    return _services


def get_services():
    return _services


def require_services():
    if _services is None:
        raise RuntimeError("L3 业务存储未就绪")
    return _services
