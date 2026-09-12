from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.health.router import router as health_router
from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orchestrator")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    log.info("config %s", settings.redacted())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="智能服务编排", version="0.1.0", lifespan=_lifespan)
    app.include_router(health_router)

    static_dir = Path(settings.static_dir)
    if static_dir.is_dir():
        # 前端构建产物同源托管（票 02）；放在最后以免遮住 API 路由
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
