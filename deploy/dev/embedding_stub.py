"""本机开发用 OpenAI 兼容 embedding 桩：确定性 1024 维向量（按词元哈希），无需任何厂商 key。

用途：没有百炼 key 时真实跑通 WeKnora 入库 / 检索链路（票 26 / 27 验证）。不用于演示与评测。
启动：cd orchestrator && uv run uvicorn --app-dir ../deploy/dev embedding_stub:app --port 8099
容器内地址：http://host.docker.internal:8099/v1
"""

from __future__ import annotations

import hashlib
import math
import re
from itertools import pairwise

from fastapi import FastAPI
from pydantic import BaseModel

DIM = 1024
app = FastAPI(title="embedding-stub")
_TOK = re.compile(r"[一-鿿]|[a-zA-Z0-9]+")


class EmbeddingsRequest(BaseModel):
    model: str = "stub"
    input: str | list[str]
    dimensions: int | None = None


def embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    toks = _TOK.findall(text.lower()) or [text]
    # 单字 + 相邻二元组，让语义相近的中文片段有重叠
    grams = toks + [a + b for a, b in pairwise(toks)]
    for g in grams:
        h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@app.post("/v1/embeddings")
def embeddings(req: EmbeddingsRequest):
    inputs = [req.input] if isinstance(req.input, str) else req.input
    dim = req.dimensions or DIM
    return {
        "object": "list",
        "model": req.model,
        "data": [
            {"object": "embedding", "index": i, "embedding": embed(t, dim)}
            for i, t in enumerate(inputs)
        ],
        "usage": {
            "prompt_tokens": sum(len(t) for t in inputs),
            "total_tokens": sum(len(t) for t in inputs),
        },
    }


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "stub-embedding-1024", "object": "model"}]}
