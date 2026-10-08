"""主办方 63 单工单只读接口：前端「载入真实工单」用（演示与回归共用），附件原图按名取。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.official.models import OfficialData

router = APIRouter(prefix="/official", tags=["official"])


@router.get("/tickets")
async def list_tickets() -> list[dict]:
    return [
        {
            "id": t.id,
            "product_line": t.product_line,
            "product_name": t.product_name,
            "scenario": t.scenario,
            "body": t.body,
            "attachments": t.attachments,
        }
        for t in OfficialData().tickets
    ]


@router.get("/tickets/{ticket_id}/attachments/{name}")
async def ticket_attachment(ticket_id: str, name: str) -> FileResponse:
    ticket = next((t for t in OfficialData().tickets if t.id == ticket_id), None)
    if ticket is None or name not in ticket.attachments:
        raise HTTPException(404, detail={"code": "not_found", "message": f"{ticket_id}/{name}"})
    return FileResponse(OfficialData().attachment(name))
