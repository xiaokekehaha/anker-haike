"""session_images(image_id, session_id, purpose, sha256, mime, size, bytes, created_at)（03 §3.1；07 §9 图片 1 小时）。

- 上限 5 MB（04 §1），超过或非图片抛 ImageRejected，由接口映射为 413 / 415，不进入对话流。
- 只存数据库；编排服务磁盘无图片文件。状态与快照只放 ImageRef（image_id / purpose / sha256 / size / mime）。
- InMemoryImageStore 供单测，语义与 Postgres 实现一致。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from psycopg_pool import AsyncConnectionPool

log = logging.getLogger("images")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
RETENTION = timedelta(hours=1)
Purpose = Literal["fault", "receipt"]
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/gif"}

DDL = """
create table if not exists session_images (
    image_id   text primary key,
    session_id text not null,
    purpose    text not null,
    sha256     text not null,
    mime       text not null,
    size       integer not null,
    bytes      bytea not null,
    created_at timestamptz not null default now()
);
create index if not exists session_images_session_idx on session_images(session_id);
create index if not exists session_images_created_idx on session_images(created_at);
"""


class ImageRejected(ValueError):
    def __init__(self, code: Literal["too_large", "unsupported_type", "empty"], message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ImageRef:
    image_id: str
    session_id: str
    purpose: str
    sha256: str
    mime: str
    size: int
    created_at: str

    def public(self) -> dict[str, Any]:
        """写入图状态 / 快照的形状（不含 session_id）。"""
        d = asdict(self)
        d.pop("session_id")
        return d


def sniff_mime(data: bytes, declared: str | None) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "image/heic"
    return (declared or "").split(";")[0].strip().lower()


def validate_image(data: bytes, declared_mime: str | None) -> str:
    if not data:
        raise ImageRejected("empty", "图片为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageRejected(
            "too_large", f"图片超过 5 MB（{len(data) / 1024 / 1024:.1f} MB），请压缩后重试"
        )
    mime = sniff_mime(data, declared_mime)
    if mime not in ALLOWED_MIME:
        raise ImageRejected("unsupported_type", f"不支持的图片格式 {mime or 'unknown'}")
    return mime


class ImageStore(Protocol):
    async def put(
        self, session_id: str, purpose: str, data: bytes, declared_mime: str | None
    ) -> ImageRef: ...
    async def get(self, session_id: str, image_id: str) -> tuple[ImageRef, bytes] | None: ...
    async def refs(self, session_id: str, image_ids: list[str]) -> list[ImageRef]: ...
    async def cleanup(self, older_than: timedelta = RETENTION) -> int: ...


def _ref(row: dict[str, Any]) -> ImageRef:
    created = row["created_at"]
    return ImageRef(
        image_id=row["image_id"],
        session_id=row["session_id"],
        purpose=row["purpose"],
        sha256=row["sha256"],
        mime=row["mime"],
        size=int(row["size"]),
        created_at=created.isoformat() if isinstance(created, datetime) else str(created),
    )


class PostgresImageStore:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def setup(self) -> None:
        async with self._pool.connection() as conn:
            for stmt in (x.strip() for x in DDL.split(";")):
                if stmt:
                    await conn.execute(stmt)

    async def put(
        self, session_id: str, purpose: str, data: bytes, declared_mime: str | None
    ) -> ImageRef:
        mime = validate_image(data, declared_mime)
        image_id = uuid.uuid4().hex
        sha = hashlib.sha256(data).hexdigest()
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """insert into session_images(image_id, session_id, purpose, sha256, mime, size, bytes)
                   values (%s, %s, %s, %s, %s, %s, %s) returning image_id, session_id, purpose, sha256, mime, size, created_at""",
                (image_id, session_id, purpose, sha, mime, len(data), data),
            )
            row = await cur.fetchone()
        ref = _ref(row)
        log.info(
            "image stored session=%s image=%s purpose=%s size=%d mime=%s",
            session_id,
            image_id,
            purpose,
            len(data),
            mime,
        )
        return ref

    async def get(self, session_id: str, image_id: str) -> tuple[ImageRef, bytes] | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "select * from session_images where session_id = %s and image_id = %s",
                (session_id, image_id),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return _ref(row), bytes(row["bytes"])

    async def refs(self, session_id: str, image_ids: list[str]) -> list[ImageRef]:
        if not image_ids:
            return []
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select image_id, session_id, purpose, sha256, mime, size, created_at from session_images
                   where session_id = %s and image_id = any(%s)""",
                (session_id, image_ids),
            )
            rows = await cur.fetchall()
        by_id = {r["image_id"]: _ref(r) for r in rows}
        return [by_id[i] for i in image_ids if i in by_id]

    async def cleanup(self, older_than: timedelta = RETENTION) -> int:
        cutoff = datetime.now(UTC) - older_than
        async with self._pool.connection() as conn:
            cur = await conn.execute("delete from session_images where created_at < %s", (cutoff,))
            n = cur.rowcount or 0
        if n:
            log.info(
                "image cleanup removed=%d older_than=%s",
                n,
                older_than,
                extra={"event": "image_cleanup", "removed": n},
            )
        return n


class InMemoryImageStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[ImageRef, bytes, datetime]] = {}
        self._lock = asyncio.Lock()

    async def put(
        self, session_id: str, purpose: str, data: bytes, declared_mime: str | None
    ) -> ImageRef:
        mime = validate_image(data, declared_mime)
        now = datetime.now(UTC)
        ref = ImageRef(
            uuid.uuid4().hex,
            session_id,
            purpose,
            hashlib.sha256(data).hexdigest(),
            mime,
            len(data),
            now.isoformat(),
        )
        async with self._lock:
            self._rows[ref.image_id] = (ref, data, now)
        log.info(
            "image stored session=%s image=%s purpose=%s size=%d mime=%s",
            session_id,
            ref.image_id,
            purpose,
            len(data),
            mime,
        )
        return ref

    async def get(self, session_id: str, image_id: str) -> tuple[ImageRef, bytes] | None:
        row = self._rows.get(image_id)
        if row is None or row[0].session_id != session_id:
            return None
        return row[0], row[1]

    async def refs(self, session_id: str, image_ids: list[str]) -> list[ImageRef]:
        out = []
        for i in image_ids:
            row = self._rows.get(i)
            if row and row[0].session_id == session_id:
                out.append(row[0])
        return out

    async def cleanup(self, older_than: timedelta = RETENTION) -> int:
        cutoff = datetime.now(UTC) - older_than
        old = [k for k, (_, _, t) in self._rows.items() if t < cutoff]
        for k in old:
            del self._rows[k]
        if old:
            log.info(
                "image cleanup removed=%d older_than=%s",
                len(old),
                older_than,
                extra={"event": "image_cleanup", "removed": len(old)},
            )
        return len(old)

    def _backdate(self, image_id: str, delta: timedelta) -> None:  # 测试用
        ref, data, t = self._rows[image_id]
        self._rows[image_id] = (ref, data, t - delta)
