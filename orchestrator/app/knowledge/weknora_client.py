"""WeKnora v0.8.0 HTTP 客户端（docs/api/*.md 于 commit 1edcd54 核对）。

- 鉴权：`X-API-Key`；注册 / 登录接口无需 key。
- 所有响应统一解包 `{"success", "data"}`；HTTP 非 2xx 或 success=false 抛 WeKnoraError（含状态码与消息，不含 key）。
- 只封装票 26 / 27 需要的接口；参数名与官方文档一致。
"""

from __future__ import annotations

from typing import Any, Self

import httpx

API_PREFIX = "/api/v1"


class WeKnoraError(RuntimeError):
    def __init__(self, status: int, message: str, path: str):
        self.status = status
        self.path = path
        super().__init__(f"WeKnora {status} on {path}: {message[:300]}")


class WeKnoraClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key or None
        self._client = httpx.AsyncClient(
            base_url=self.base_url + API_PREFIX, timeout=timeout_s, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ---- 基础 ----
    def _headers(self, auth: bool = True) -> dict[str, str]:
        h: dict[str, str] = {}
        if auth and self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    async def _req(self, method: str, path: str, *, auth: bool = True, **kw: Any) -> Any:
        resp = await self._client.request(method, path, headers=self._headers(auth), **kw)
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"raw": resp.text[:300]}
        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("success") is False):
            msg = (
                body.get("error") or body.get("message") or body if isinstance(body, dict) else body
            )
            raise WeKnoraError(resp.status_code, str(msg), path)
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    # ---- 认证 / tenant ----
    async def auth_config(self) -> dict:
        return await self._req("GET", "/auth/config", auth=False)

    async def register(self, username: str, email: str, password: str) -> dict:
        """自助注册；返回含 user / tenant(id, api_key) 的 data。"""
        return await self._req(
            "POST",
            "/auth/register",
            auth=False,
            json={"username": username, "email": email, "password": password},
        )

    async def login(self, email: str, password: str) -> dict:
        return await self._req(
            "POST", "/auth/login", auth=False, json={"email": email, "password": password}
        )

    async def list_tenants(self) -> list[dict]:
        return await self._req("GET", "/tenants") or []

    async def create_api_key(
        self,
        tenant_id: int | str,
        jwt: str,
        *,
        name: str,
        role: str = "admin",
        full_access: bool = True,
        capabilities: list[str] | None = None,
    ) -> dict:
        """需要 Owner 的 JWT。full_access=true 为全权限 key；否则必须给 capabilities（retrieve / ingest / manage_kbs）。"""
        payload: dict[str, Any] = {"name": name, "role": role, "full_access": full_access}
        if not full_access:
            payload["capabilities"] = capabilities or ["retrieve", "ingest", "manage_kbs"]
        resp = await self._client.post(
            f"/tenants/{tenant_id}/api-keys",
            json=payload,
            headers={"Authorization": f"Bearer {jwt}"},
        )
        body = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise WeKnoraError(
                resp.status_code, str(body.get("error") or body), "/tenants/api-keys"
            )
        return body.get("data", body)

    # ---- 模型 ----
    async def list_models(self) -> list[dict]:
        return await self._req("GET", "/models") or []

    async def create_model(self, payload: dict) -> dict:
        return await self._req("POST", "/models", json=payload)

    # ---- 知识库 ----
    async def list_knowledge_bases(self) -> list[dict]:
        return await self._req("GET", "/knowledge-bases") or []

    async def get_knowledge_base(self, kb_id: str) -> dict:
        return await self._req("GET", f"/knowledge-bases/{kb_id}")

    async def create_knowledge_base(self, payload: dict) -> dict:
        return await self._req("POST", "/knowledge-bases", json=payload)

    async def delete_knowledge_base(self, kb_id: str) -> None:
        await self._req("DELETE", f"/knowledge-bases/{kb_id}")

    # ---- 知识 ----
    async def list_knowledge(self, kb_id: str, *, page_size: int = 100) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/knowledge-bases/{kb_id}/knowledge",
                params={"page": page, "page_size": page_size},
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise WeKnoraError(
                    resp.status_code, resp.text, f"/knowledge-bases/{kb_id}/knowledge"
                )
            body = resp.json()
            items = body.get("data") or []
            out.extend(items)
            total = body.get("total", len(out))
            if not items or len(out) >= total:
                return out
            page += 1

    async def create_manual_knowledge(
        self, kb_id: str, *, title: str, content: str, status: str = "publish"
    ) -> dict:
        return await self._req(
            "POST",
            f"/knowledge-bases/{kb_id}/knowledge/manual",
            json={"title": title, "content": content, "status": status},
        )

    async def upload_file(
        self, kb_id: str, filename: str, data: bytes, metadata: dict | None = None
    ) -> dict:
        import json as _json

        files = {"file": (filename, data)}
        form = {"fileName": filename}
        if metadata:
            form["metadata"] = _json.dumps(metadata, ensure_ascii=False)
        return await self._req(
            "POST", f"/knowledge-bases/{kb_id}/knowledge/file", files=files, data=form
        )

    async def get_knowledge(self, knowledge_id: str) -> dict:
        return await self._req("GET", f"/knowledge/{knowledge_id}")

    async def update_knowledge(
        self, knowledge_id: str, *, custom_metadata: dict | None = None, **fields: Any
    ) -> None:
        payload = dict(fields)
        if custom_metadata is not None:
            payload["custom_metadata"] = custom_metadata
        await self._req("PUT", f"/knowledge/{knowledge_id}", json=payload)

    async def delete_knowledge(self, knowledge_id: str) -> None:
        await self._req("DELETE", f"/knowledge/{knowledge_id}")

    # ---- FAQ ----
    async def list_faq_entries(self, kb_id: str, *, page_size: int = 200) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/knowledge-bases/{kb_id}/faq/entries",
                params={"page": page, "page_size": page_size},
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise WeKnoraError(resp.status_code, resp.text, "faq/entries")
            body = resp.json()
            data = body.get("data")
            # v0.8.0 实测响应形状：{"data": {"total", "page", "page_size", "data": [...]}}
            items = (
                (data.get("data") or data.get("entries") or [])
                if isinstance(data, dict)
                else (data or [])
            )
            out.extend(items)
            total = (
                body.get("total")
                or (data.get("total") if isinstance(data, dict) else None)
                or len(out)
            )
            if not items or len(out) >= total:
                return out
            page += 1

    async def upsert_faq_entries(
        self, kb_id: str, entries: list[dict], *, mode: str = "replace"
    ) -> dict:
        return await self._req(
            "POST", f"/knowledge-bases/{kb_id}/faq/entries", json={"mode": mode, "entries": entries}
        )

    async def faq_import_progress(self, task_id: str) -> dict:
        return await self._req("GET", f"/faq/import/progress/{task_id}")

    async def faq_search(
        self, kb_id: str, query: str, *, match_count: int = 10, **opts: Any
    ) -> list[dict]:
        return (
            await self._req(
                "POST",
                f"/knowledge-bases/{kb_id}/faq/search",
                json={"query_text": query, "match_count": match_count, **opts},
            )
            or []
        )

    async def list_chunks(self, knowledge_id: str, *, page_size: int = 100) -> list[dict]:
        """v0.8.0：GET /chunks/{knowledge_id} 只列子块（含 parent_chunk_id / chunk_index / pre|next_chunk_id），
        父块本身没有读取接口（/chunks/{parent_id} → Knowledge not found，2026-09-13 实测）。"""
        out: list[dict] = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/chunks/{knowledge_id}",
                params={"page": page, "page_size": page_size},
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise WeKnoraError(resp.status_code, resp.text, f"/chunks/{knowledge_id}")
            body = resp.json()
            items = body.get("data") or []
            out.extend(items)
            total = body.get("total") or len(out)
            if not items or len(out) >= total:
                return out
            page += 1

    # ---- 检索 ----
    async def knowledge_search(
        self, query: str, *, knowledge_base_ids: list[str], knowledge_ids: list[str] | None = None
    ) -> list[dict]:
        payload: dict[str, Any] = {"query": query, "knowledge_base_ids": knowledge_base_ids}
        if knowledge_ids is not None:
            payload["knowledge_ids"] = knowledge_ids
        return await self._req("POST", "/knowledge-search", json=payload) or []

    async def hybrid_search(
        self, kb_id: str, query: str, *, match_count: int = 10, **opts: Any
    ) -> list[dict]:
        return (
            await self._req(
                "POST",
                f"/knowledge-bases/{kb_id}/hybrid-search",
                json={"query_text": query, "match_count": match_count, **opts},
            )
            or []
        )
