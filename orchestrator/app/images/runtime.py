"""进程级 ImageStore 与清理任务（票 29）。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.images.store import RETENTION, ImageStore, PostgresImageStore

log = logging.getLogger("images.runtime")
CLEANUP_INTERVAL_S = 300


_store: ImageStore | None = None


def set_image_store(store: ImageStore | None) -> None:
    """图节点与测试取用的进程级存储。"""
    global _store
    _store = store


def current_image_store() -> ImageStore | None:
    return _store


def get_image_store(app: FastAPI) -> ImageStore | None:
    return getattr(app.state, "image_store", None) or _store


async def open_image_store(app: FastAPI) -> None:
    pool = getattr(app.state, "session_pool", None)
    app.state.image_store = None
    app.state.image_cleanup_task = None
    if pool is None:
        log.warning("image store disabled: no database pool")
        return
    store = PostgresImageStore(pool)
    await store.setup()
    app.state.image_store = store
    set_image_store(store)
    app.state.image_cleanup_task = asyncio.create_task(_cleanup_loop(store), name="image-cleanup")
    log.info("image store ready; cleanup every %ss, retention %s", CLEANUP_INTERVAL_S, RETENTION)


async def close_image_store(app: FastAPI) -> None:
    task = getattr(app.state, "image_cleanup_task", None)
    if task is not None:
        task.cancel()


async def _cleanup_loop(store: ImageStore, interval_s: float = CLEANUP_INTERVAL_S) -> None:
    while True:
        try:
            await store.cleanup(RETENTION)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("image cleanup failed")
        await asyncio.sleep(interval_s)
