"""主办方工单只读接口（前端「载入真实工单」）。"""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_lists_63_tickets_and_serves_attachments():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        tickets = (await client.get("/official/tickets")).json()
        assert len(tickets) == 63 and tickets[0]["id"] == "T1"
        with_image = next(t for t in tickets if t["attachments"])
        image = await client.get(f"/official/tickets/{with_image['id']}/attachments/{with_image['attachments'][0]}")
        assert image.status_code == 200 and image.headers["content-type"].startswith("image/")
        missing = await client.get(f"/official/tickets/{with_image['id']}/attachments/other.jpg")
        assert missing.status_code == 404
