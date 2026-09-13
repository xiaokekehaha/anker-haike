"""票 48：数据保留与脱敏（07 §12 记忆分类 TTL、§15 数据）。

- 按会话删除：DELETE /sessions/{id}（X-Admin-Token）→ 快照 404、事件 / 图片 / checkpoint 无残留。
- TTL 清理：purge_expired 只删过期且无 active run 的会话与孤儿事件，有统计；日志轮转备份按 7 天清理。
- 脱敏：跑一条含手机号 / 订单号 / 地址的消息后，JSONL 里用正则搜不到明文。
"""

from __future__ import annotations

from tests.message_form import message_form

import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.images.runtime import set_image_store
from app.images.store import InMemoryImageStore
from app.main import app
from app.observability.privacy import sanitize
from app.observability.runtime import configure_logging, record, set_exporter
from app.retention import PurgeStats, purge_expired, purge_log_backups, ttl_config
from app.retention import main as retention_main
from app.sessions import sse
from app.sessions.store import SessionNotFound
from app.settings import settings
from tests.test_images import png_bytes

PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ORDER = re.compile(r"AK\d{8,}")


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "t0ken")
    return {"X-Admin-Token": "t0ken"}


@pytest.fixture
def img_store():
    store = InMemoryImageStore()
    set_image_store(store)
    app.state.image_store = store
    yield store
    set_image_store(None)
    app.state.image_store = None


async def _send(client, sid: str, text: str, files=None) -> list[dict]:
    resp = await client.post(f"/sessions/{sid}/messages", data=await message_form(client, f"/sessions/{sid}/messages", {"text": text}), files=files or [])
    assert resp.status_code == 200, resp.text
    return sse.parse(resp.text)


# ---------------- 按会话删除 ----------------


async def test_delete_session_removes_snapshot_events_images_and_checkpoint(mem_runtime, admin, img_store):
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        ev = await _send(
            client, sid, "扫地机 X9 不吸了", files=[("images", ("a.png", png_bytes(128), "image/png"))]
        )
        snap = (await client.get(f"/sessions/{sid}")).json()
        image_id = next(i for i in snap["timeline"] if i["kind"] == "user_message")["image_ids"][0]
        assert (await client.get(f"/sessions/{sid}/images/{image_id}")).status_code == 200
        # 无口令 / 错口令 → 403，数据不动
        assert (await client.delete(f"/sessions/{sid}")).status_code == 403
        assert (await client.delete(f"/sessions/{sid}", headers={"X-Admin-Token": "x"})).status_code == 403
        assert (await client.get(f"/sessions/{sid}")).status_code == 200

        r = await client.delete(f"/sessions/{sid}", headers=admin)
        assert r.status_code == 200, r.text
        deleted = r.json()["deleted"]
        assert deleted["sessions"] == 1 and deleted["session_events"] >= 3 and deleted["session_images"] == 1
        # 快照 404、图片 404、事件续接 404、checkpoint 线程为空
        assert (await client.get(f"/sessions/{sid}")).status_code == 404
        assert (await client.get(f"/sessions/{sid}/images/{image_id}")).status_code == 404
        run_id = ev[0]["run_id"]
        assert (await client.get(f"/sessions/{sid}/runs/{run_id}/events")).status_code == 404
        state = await app.state.session_graph.aget_state({"configurable": {"thread_id": sid}})
        assert not state.values
        with pytest.raises(SessionNotFound):
            await mem_runtime.list_events(sid)
        # 再删一次 → 404（已无数据）
        assert (await client.delete(f"/sessions/{sid}", headers=admin)).status_code == 404


async def test_delete_disabled_without_admin_token(mem_runtime, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        r = await client.delete(f"/sessions/{sid}", headers={"X-Admin-Token": ""})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_disabled"
        assert (await client.get(f"/sessions/{sid}")).status_code == 200


# ---------------- TTL 清理（真实 Postgres，可连时运行） ----------------


async def test_purge_expired_sessions_real_postgres_keeps_active_and_fresh():
    from tests.test_catalog import _pool

    pool = await _pool()
    try:
        from app.images import PostgresImageStore
        from app.sessions.store import PostgresSessionStore

        store = PostgresSessionStore(pool)
        await store.setup()
        images = PostgresImageStore(pool)
        await images.setup()
        old = (await store.create_session()).session_id
        fresh = (await store.create_session()).session_id
        active = (await store.create_session()).session_id
        await store.reserve_input(active, "active-input", {"kind": "message", "text": "处理中"}, expected_version=0)
        for sid in (old, fresh, active):
            await store.append_event(sid, "r1", {"type": "run_started", "resumed": False, "deadline_ms": 1})
            await images.put(sid, "fault", png_bytes(64), "image/png")
        orphan = "orphan-" + old[:8]
        await store.append_event(orphan, "r0", {"type": "ping"})
        async with pool.connection() as conn:
            stale = datetime.now(UTC) - timedelta(hours=30)
            await conn.execute("update sessions set updated_at = %s where session_id in (%s, %s)", (stale, old, active))
            await conn.execute("update session_events set created_at = %s where session_id = %s", (stale, orphan))
            # 造一条 checkpoint 行（表可能尚不存在：由 saver 建；这里只在存在时验证）
            cur = await conn.execute("select (to_regclass('checkpoints') is not null) as has")
            has_ckpt = (await cur.fetchone())["has"]
            if has_ckpt:
                await conn.execute(
                    """insert into checkpoints(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                       values (%s, '', 'c1', null, 'json', '{}'::jsonb, '{}'::jsonb) on conflict do nothing""",
                    (old,),
                )

        stats = await purge_expired(pool, session_ttl=timedelta(hours=24))
        assert isinstance(stats, PurgeStats)
        # 库里可能还有更早失败运行留下的过期数据，因此按「至少」与按 id 断言
        assert stats.sessions >= 1 and stats.orphan_sessions >= 1
        assert stats.deleted["sessions"] == stats.sessions
        assert stats.deleted["session_events"] >= 2
        assert stats.deleted["session_images"] >= 1
        if has_ckpt:
            assert stats.deleted["checkpoints"] >= 1
        # 过期会话没了；新会话与有 active run 的过期会话都保留
        assert not await store.session_exists(old) and await store.session_exists(fresh)
        assert await store.session_exists(active) and await store.list_events(active)
        assert await store.list_events(orphan) == []
        async with pool.connection() as conn:
            cur = await conn.execute(
                "select count(*) as n from session_images where session_id = any(%s)",
                ([old, fresh, active],),
            )
            assert (await cur.fetchone())["n"] == 2
            await conn.execute("delete from sessions where session_id = any(%s)", ([fresh, active],))
            await conn.execute("delete from session_events where session_id = any(%s)", ([fresh, active],))
            await conn.execute("delete from session_images where session_id = any(%s)", ([fresh, active],))
    finally:
        await pool.close()


def test_purge_log_backups_removes_only_old_rotated_files(tmp_path):
    current = tmp_path / "events.jsonl"
    current.write_text("{}\n")
    old_backup, new_backup = tmp_path / "events.jsonl.1", tmp_path / "events.jsonl.2"
    old_backup.write_text("{}\n")
    new_backup.write_text("{}\n")
    stale = time.time() - 8 * 86400
    os.utime(old_backup, (stale, stale))
    assert purge_log_backups(str(current), timedelta(days=7)) == 1
    assert current.exists() and new_backup.exists() and not old_backup.exists()
    assert purge_log_backups(str(tmp_path / "missing" / "x.jsonl"), timedelta(days=7)) == 0


def test_ttl_defaults_match_design_and_cli_prints_them(capsys):
    ttl = ttl_config()
    assert ttl["images"] == timedelta(hours=1)
    assert ttl["sessions"] == timedelta(hours=24) and ttl["traces"] == timedelta(days=7)
    assert retention_main(["ttl"]) == 0
    out = capsys.readouterr().out
    assert "sessions: 1 day, 0:00:00" in out and "traces: 7 days" in out


# ---------------- 脱敏：JSONL 里搜不到明文 ----------------


@pytest.fixture
def logs(tmp_path):
    path = tmp_path / "events.jsonl"
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.INFO)
    handler = configure_logging(str(path))
    yield path
    root.removeHandler(handler)
    handler.close()
    root.setLevel(level)
    set_exporter(None)


async def test_jsonl_has_no_plaintext_phone_order_or_address(mem_runtime, logs):
    text = "我的 X9 不吸了，手机 13912345678，订单号 AK2026091200123，收货地址 上海市浦东新区张江路 100 号 3 栋 502 室，帮我查一下"
    async with _client() as client:
        sid = (await client.post("/sessions")).json()["session_id"]
        await _send(client, sid, text)
    record("manual_note", session_id=sid, note=text, address="北京市朝阳区某某路 1 号", phone="13800138000")
    logging.getLogger("test").info("plain %s", text)
    for h in logging.getLogger().handlers:
        h.flush()
    raw = logs.read_text(encoding="utf-8")
    assert raw.strip(), "JSONL 应有内容"
    assert not PHONE.search(raw), "明文手机号泄漏"
    assert not ORDER.search(raw), "明文订单号泄漏"
    assert "张江路" not in raw and "朝阳区" not in raw, "明文地址泄漏"
    # 逐行仍是合法 JSON，且 session_id 未被脱敏（供追踪关联）
    lines = [json.loads(l) for l in raw.splitlines() if l.strip()]
    assert any(sid in json.dumps(x) for x in lines)


def test_sanitize_masks_address_labels_but_keeps_symptoms():
    out = sanitize("扫地机不吸了，地址：杭州市西湖区文三路 90 号，明天到")
    assert "文三路" not in out and "扫地机不吸了" in out and out.endswith("明天到")
    assert sanitize({"shipping_address": "x", "note": "寄到 深圳市南山区科技园 1 栋"}) == {
        "shipping_address": "[REDACTED]",
        "note": "寄到 [REDACTED]",
    }
