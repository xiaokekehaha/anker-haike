#!/usr/bin/env bash
# 本机复现 .github/workflows/backend.yml + contracts.yml 的检查步骤（票 49）。需要本机 Postgres（make up）。
set -euo pipefail
cd "$(dirname "$0")/.."
export HAIKE_LLM=off HAIKE_KNOWLEDGE=off
echo "== ruff";       (cd orchestrator && uv run ruff check .)
echo "== db-check";   (cd orchestrator && uv run haike-db upgrade >/dev/null && uv run haike-db check)
echo "== pytest";     (cd orchestrator && uv run pytest -q)
echo "== contracts";  make contracts-check && (cd contracts && uv run --group dev pytest -q)
echo "== frontend";   (cd frontend && npm run contracts:check && npm test -- --run && npm run build >/dev/null)
echo "CI-local: all green"
