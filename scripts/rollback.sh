#!/usr/bin/env bash
# 回滚到某个 release 的 config/ 并重启编排服务，等健康检查通过（票 49；04 §4「切回上一版 config 目录并重启」）。
# 用法：scripts/rollback.sh <release_id> [timeout_s=300]
set -euo pipefail
cd "$(dirname "$0")/.."
REL="${1:?release_id required (see releases/)}"; TIMEOUT="${2:-300}"
SRC="releases/$REL/config"; [ -d "$SRC" ] || { echo "no config snapshot at $SRC" >&2; ls releases 2>/dev/null; exit 1; }
PORT="$(grep -m1 -E '^ORCHESTRATOR_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"; PORT="${PORT:-8000}"
start=$(date +%s)
echo "$(date -u +%FT%TZ) rollback -> $REL"
mkdir -p releases/_pre-rollback && rm -rf releases/_pre-rollback/config && cp -R config releases/_pre-rollback/config
rsync -a --delete "$SRC/" config/
# config/ 以只读卷挂进容器（docker-compose.yml），重启即生效，无需重建镜像
docker compose restart orchestrator >/dev/null
until curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; do
  if [ $(( $(date +%s) - start )) -ge "$TIMEOUT" ]; then echo "health check not ok within ${TIMEOUT}s" >&2; exit 1; fi
  sleep 2
done
echo "$(date -u +%FT%TZ) rollback done in $(( $(date +%s) - start ))s; previous config kept at releases/_pre-rollback/config"
