"""内存版 WeKnora（只实现票 26 用到的接口），挂在 httpx.MockTransport 上。"""

from __future__ import annotations

import json
import uuid

import httpx


class FakeWeKnora:
    def __init__(self, *, api_key: str = "sk-test", models: list[dict] | None = None):
        self.api_key = api_key
        self.models = models if models is not None else []
        self.kbs: dict[str, dict] = {}
        self.knowledge: dict[str, dict] = {}
        self.faq: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []
        self.registered: dict[str, dict] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # ---- helpers ----
    @staticmethod
    def _ok(data, status=200, **extra):
        return httpx.Response(status, json={"success": True, "data": data, **extra})

    @staticmethod
    def _err(status, msg):
        return httpx.Response(status, json={"success": False, "error": msg})

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        method = request.method
        self.calls.append((method, path))
        body = (
            json.loads(request.content)
            if request.content
            and request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if path.startswith("/auth/"):
            return self._auth(path, body)
        if path.startswith("/tenants/") and path.endswith("/api-keys"):
            return self._api_keys(request, body)
        if request.headers.get("X-API-Key") != self.api_key:
            return self._err(401, "Unauthorized: missing authentication")
        parts = path.strip("/").split("/")
        if path == "/models":
            if method == "GET":
                return self._ok(self.models)
            m = {**body, "id": uuid.uuid4().hex}
            self.models.append(m)
            return self._ok(m)
        if path == "/knowledge-bases":
            if method == "GET":
                return self._ok(list(self.kbs.values()))
            kb = {**body, "id": uuid.uuid4().hex, "knowledge_count": 0}
            self.kbs[kb["id"]] = kb
            return self._ok(kb)
        if parts[0] == "knowledge-bases" and len(parts) >= 2:
            kb_id = parts[1]
            if kb_id not in self.kbs:
                return self._err(404, "kb not found")
            rest = parts[2:]
            if rest == ["knowledge"] and method == "GET":
                items = [k for k in self.knowledge.values() if k["knowledge_base_id"] == kb_id]
                page = int(request.url.params.get("page", 1))
                size = int(request.url.params.get("page_size", 20))
                chunk = items[(page - 1) * size : page * size]
                return self._ok(chunk, total=len(items), page=page, page_size=size)
            if rest == ["knowledge", "manual"]:
                k = {
                    "id": uuid.uuid4().hex,
                    "knowledge_base_id": kb_id,
                    "title": body["title"],
                    "content": body["content"],
                    "type": "manual",
                    "parse_status": "completed",
                    "custom_metadata": None,
                }
                self.knowledge[k["id"]] = k
                return self._ok(k)
            if rest == ["faq", "entries"]:
                if method == "GET":
                    return self._ok(self.faq.get(kb_id, []), total=len(self.faq.get(kb_id, [])))
                if body.get("mode") == "replace":
                    self.faq[kb_id] = list(body["entries"])
                else:
                    self.faq.setdefault(kb_id, []).extend(body["entries"])
                return self._ok({"task_id": uuid.uuid4().hex})
            if rest == ["hybrid-search"]:
                return self._ok([])
        if parts[0] == "knowledge" and len(parts) == 2:
            k = self.knowledge.get(parts[1])
            if k is None:
                return self._err(404, "knowledge not found")
            if method == "GET":
                return self._ok(k)
            if method == "PUT":
                k.update({key: v for key, v in body.items()})
                return self._ok({})
            if method == "DELETE":
                del self.knowledge[parts[1]]
                return self._ok({})
        if path == "/knowledge-search":
            ids = set(body.get("knowledge_ids") or [])
            kbs = set(body.get("knowledge_base_ids") or [])
            hits = [
                {
                    "id": f"c-{k['id']}",
                    "knowledge_id": k["id"],
                    "content": k["content"][:50],
                    "score": 0.5,
                    "knowledge_title": k["title"],
                    "metadata": k.get("custom_metadata"),
                }
                for k in self.knowledge.values()
                if k["knowledge_base_id"] in kbs
                and (not ids or k["id"] in ids)
                and body["query"] in k["content"]
            ]
            return self._ok(hits)
        return self._err(404, f"no route {method} {path}")

    def _auth(self, path, body):
        if path == "/auth/config":
            return httpx.Response(200, json={"registration_mode": "self_serve", "success": True})
        if path == "/auth/register":
            if body["email"] in self.registered:
                return self._err(400, "email exists")
            t = {"id": uuid.uuid4().hex, "name": body["username"], "api_key": self.api_key}
            self.registered[body["email"]] = {"password": body["password"], "tenant": t}
            return self._ok({"user": {"id": "u1", "tenant_id": t["id"]}, "tenant": t})
        if path == "/auth/login":
            u = self.registered.get(body["email"])
            if not u or u["password"] != body["password"]:
                return self._err(401, "bad credentials")
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "user": {"id": "u1"},
                    "active_tenant": {"id": 10001, "name": "ws"},
                    "token": "jwt",
                },
            )
        return self._err(404, "no auth route")

    def _api_keys(self, request, body):
        if request.headers.get("Authorization") != "Bearer jwt":
            return self._err(401, "owner jwt required")
        if not body.get("name"):
            return self._err(400, "name is required")
        if not body.get("full_access") and not body.get("capabilities"):
            return self._err(400, "capabilities are required for scoped API keys")
        return httpx.Response(
            201,
            json={
                "success": True,
                "data": {
                    "id": "k1",
                    "name": body["name"],
                    "api_key": self.api_key,
                    "full_access": bool(body.get("full_access")),
                },
            },
        )
