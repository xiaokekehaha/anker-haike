from fastapi import APIRouter, HTTPException, Request, Response

from app.models.probe import ModelProbes, ModelStatus, ModelStatuses, ProbeBusy

router = APIRouter(prefix="/models", tags=["models"])


def probes(request: Request) -> ModelProbes:
    service = getattr(request.app.state, "model_probes", None)
    if service is None:
        raise HTTPException(503, "模型状态服务尚未就绪")
    return service


@router.get("/status", response_model=ModelStatuses)
async def model_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return probes(request).snapshot()


@router.post("/{alias}/probe", response_model=ModelStatus)
async def model_probe(alias: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await probes(request).probe(alias)
    except KeyError:
        raise HTTPException(404, "未找到该聊天模型") from None
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    except ProbeBusy:
        raise HTTPException(429, "检测请求较多，请稍后重试") from None
