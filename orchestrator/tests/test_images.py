"""票 29：图片校验 / 存储 / 引用进状态与快照 / 1 小时清理 / 本地无文件；Postgres 可达时跑真实表。"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import struct
import zlib
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.images import MAX_IMAGE_BYTES, ImageRejected, InMemoryImageStore
from app.images.runtime import set_image_store
from app.images.store import validate_image
from app.main import app
from app.rules import RulesService, set_rules_service
from app.sessions import sse
from app.settings import REPO_ROOT
from tests.message_form import message_form

RULES = REPO_ROOT / "config" / "rules" / "safety_terms.yaml"


def png_bytes(payload_size: int = 64) -> bytes:
    """最小合法 PNG 头 + 任意长度数据块，用来控制体积。"""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    chunk = (
        struct.pack(">I", len(ihdr))
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    )
    data = os.urandom(payload_size)
    idat = (
        struct.pack(">I", len(data))
        + b"IDAT"
        + data
        + struct.pack(">I", zlib.crc32(b"IDAT" + data))
    )
    return sig + chunk + idat


def test_validate_rejects_too_large_and_unknown_types():
    with pytest.raises(ImageRejected) as ei:
        validate_image(png_bytes(MAX_IMAGE_BYTES), "image/png")  # 头部 + 5 MB 数据 > 上限
    assert ei.value.code == "too_large" and "5 MB" in str(ei.value)
    with pytest.raises(ImageRejected) as ei:
        validate_image(b"%PDF-1.4 ....", "application/pdf")
    assert ei.value.code == "unsupported_type"
    with pytest.raises(ImageRejected):
        validate_image(b"", "image/png")
    assert validate_image(png_bytes(), "application/octet-stream") == "image/png"  # 以内容嗅探为准
    assert validate_image(b"\xff\xd8\xff\xe0" + b"x" * 10, None) == "image/jpeg"


@pytest.fixture
def img_store():
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    yield store
    set_image_store(None)
    app.state.image_store = None


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_upload_6mb_rejected_413_and_not_in_conversation(mem_runtime, img_store):
    async with await _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        big = png_bytes(6 * 1024 * 1024)
        resp = await client.post(
            f"/sessions/{sid}/messages",
            data=await message_form(client, f"/sessions/{sid}/messages", {"text": "看下这张图", "purpose": "fault"}),
            files={"images": ("big.png", io.BytesIO(big), "image/png")},
        )
        assert resp.status_code == 413 and resp.json()["code"] == "too_large"
        pdf = await client.post(
            f"/sessions/{sid}/messages",
            data=await message_form(client, f"/sessions/{sid}/messages", {"text": "x"}),
            files={"images": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert pdf.status_code == 415
        # 没有 run 发生：事件日志为空，快照 timeline 为空
        assert await mem_runtime.list_events(sid) == []
        assert (await client.get(f"/sessions/{sid}")).json()["timeline"] == []
    assert img_store._rows == {}


async def test_image_refs_in_state_snapshot_and_served_by_session(mem_runtime, img_store):
    set_rules_service(RulesService(RULES, hot_reload=False))
    try:
        async with await _client() as client:
            sid = (await client.post("/sessions")).json()["session_id"]
            data = png_bytes(2048)
            resp = await client.post(
                f"/sessions/{sid}/messages",
                data=await message_form(client, f"/sessions/{sid}/messages", {"text": "eufy X9 Pro 滚刷这样正常吗", "purpose": "fault"}),
                files=[("images", ("brush.png", io.BytesIO(data), "image/png"))],
            )
            assert resp.status_code == 200
            events = sse.parse(resp.text)
            assert events[-1]["type"] == "done"
            snap = (await client.get(f"/sessions/{sid}")).json()
            state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
            refs = state.values["image_refs"]
            assert len(refs) == 1 and refs[0]["purpose"] == "fault" and len(refs[0]["sha256"]) == 64
            assert (
                refs[0]["mime"] == "image/png"
                and refs[0]["size"] == len(data)
                and refs[0]["run_id"]
            )
            um = next(i for i in snap["timeline"] if i["kind"] == "user_message")
            assert um["image_ids"] == [refs[0]["image_id"]]
            assert (
                um["images"][0]["sha256"] == refs[0]["sha256"]
                and um["images"][0]["purpose"] == "fault"
            )
            got = await client.get(f"/sessions/{sid}/images/{refs[0]['image_id']}")
            assert (
                got.status_code == 200
                and got.content == data
                and got.headers["content-type"] == "image/png"
            )
            other = (await client.post("/sessions")).json()["session_id"]
            assert (
                await client.get(f"/sessions/{other}/images/{refs[0]['image_id']}")
            ).status_code == 404
    finally:
        set_rules_service(None)


async def test_cleanup_removes_old_images_with_log(img_store, caplog):
    caplog.set_level(logging.INFO, logger="images")
    fresh = await img_store.put("s", "fault", png_bytes(), "image/png")
    old = await img_store.put("s", "receipt", png_bytes(), "image/png")
    img_store._backdate(old.image_id, timedelta(hours=2))
    assert await img_store.cleanup(timedelta(hours=1)) == 1
    assert (
        await img_store.get("s", old.image_id) is None
        and await img_store.get("s", fresh.image_id) is not None
    )
    rec = next(r for r in caplog.records if getattr(r, "event", None) == "image_cleanup")
    assert rec.removed == 1


async def test_cleanup_loop_runs_periodically(img_store):
    from app.images import runtime

    old = await img_store.put("s", "fault", png_bytes(), "image/png")
    img_store._backdate(old.image_id, timedelta(hours=2))
    task = asyncio.create_task(runtime._cleanup_loop(img_store, interval_s=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    assert await img_store.get("s", old.image_id) is None


def test_no_image_files_on_local_disk():
    """图片只进数据库：仓库与编排服务目录下不应出现上传产物。"""
    suspicious = [
        p
        for p in (REPO_ROOT / "orchestrator").rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic"}
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
    ]
    assert suspicious == []
    assert (
        not (REPO_ROOT / "orchestrator" / "uploads").exists()
        and not (Path("/tmp") / "haike-images").exists()
    )


async def test_postgres_image_store_roundtrip():
    from app.images import PostgresImageStore
    from tests.test_catalog import _pool

    pool = await _pool()
    try:
        store = PostgresImageStore(pool)
        await store.setup()
        data = png_bytes(4096)
        ref = await store.put("sess-img-test", "fault", data, "image/png")
        got = await store.get("sess-img-test", ref.image_id)
        assert (
            got is not None
            and got[1] == data
            and got[0].sha256 == ref.sha256
            and got[0].mime == "image/png"
        )
        assert (await store.refs("sess-img-test", [ref.image_id, "nope"]))[
            0
        ].image_id == ref.image_id
        assert await store.get("other", ref.image_id) is None
        with pytest.raises(ImageRejected):
            await store.put("sess-img-test", "fault", png_bytes(MAX_IMAGE_BYTES), "image/png")
        async with pool.connection() as conn:
            await conn.execute(
                "update session_images set created_at = now() - interval '2 hours' where image_id = %s",
                (ref.image_id,),
            )
        assert await store.cleanup(timedelta(hours=1)) >= 1
        assert await store.get("sess-img-test", ref.image_id) is None
    finally:
        await pool.close()
