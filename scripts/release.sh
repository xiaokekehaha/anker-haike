#!/usr/bin/env bash
# 生成 RELEASE.md 并把当前 config/ 快照到 releases/<release_id>/（票 49，04 §4 版本锁定）。
# 用法：scripts/release.sh [release_id]   默认 <UTC 日期>-<git short sha>，与 CI 镜像 tag 一致
set -euo pipefail
cd "$(dirname "$0")/.."
REL="${1:-$(date -u +%Y%m%d)-$(git rev-parse --short=7 HEAD)}"
ver() { grep -m1 -E '^version:' "$1" 2>/dev/null | awk '{print $2}' || echo "-"; }
pyconst() { grep -m1 -E "^$2\s*=" "$1" 2>/dev/null | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/' || echo "-"; }
KB_VER="$(python3 -c "import json,sys; print(json.load(open('data/knowledge/manifest.json'))['kb_ver'])" 2>/dev/null || echo "-（未入库）")"
WEKNORA_TAG="$(grep -m1 -E '^WEKNORA_VERSION=' .env 2>/dev/null | cut -d= -f2 || true)"; WEKNORA_TAG="${WEKNORA_TAG:-$(grep -m1 -oE 'WEKNORA_VERSION:-v[0-9.]+' docker-compose.yml | cut -d- -f2)}"
REPLAY="$(ls -1 replay/manifest*.json 2>/dev/null | head -1 || echo "-（票 43 未录制）")"
TBD="$(grep -c -iE 'TBD|todo' config/models.yaml || true)"
OWNER="$(git remote get-url origin 2>/dev/null | sed -E 's#.*github.com[:/]([^/]+)/.*#\1#' || echo owner)"

mkdir -p "releases/$REL"
rm -rf "releases/$REL/config" && cp -R config "releases/$REL/config"
git rev-parse HEAD > "releases/$REL/git_sha"

cat > RELEASE.md <<MD
# RELEASE $REL

生成时间：$(date -u +%FT%TZ)　Git：$(git rev-parse --short=7 HEAD)（$(git rev-parse --abbrev-ref HEAD)）

## 冻结版本（04 §4）

| 项 | 值 |
| --- | --- |
| 镜像 tag | \`ghcr.io/$OWNER/haike-orchestrator:$REL\`（CI 构建；本机 \`make up\` 为 haike/orchestrator:dev） |
| prompt_ver | system $(pyconst orchestrator/app/prompts/system.py PROMPT_VERSION) / reply $(pyconst orchestrator/app/prompts/reply.py REPLY_PROMPT_VERSION) |
| models.yaml | $(ver config/models.yaml)（TBD / TODO 计数：$TBD，须为 0 才能冻结，票 42） |
| rules_ver | $(ver config/rules/safety_terms.yaml) |
| products / plans | $(ver config/products.yaml) / $(ver config/plans.yaml) |
| kb_ver | $KB_VER |
| WeKnora 镜像 tag | $WEKNORA_TAG |
| 回放包清单 | $REPLAY |
| 业务表迁移 head | $(cd orchestrator && uv run --no-sync python -c 'from app.db.migrations import head_revision; print(head_revision())' 2>/dev/null || echo "-") |
| config 快照 | \`releases/$REL/config/\`（回滚用：\`make rollback REL=<上一版>\`） |

## 灰度验证顺序（04 §4）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42，model-selection §3.8）
2. 结构化 fixture 跑协议与规则测试（contracts / 后端 CI 绿）
3. 重新录制回放包并更新清单（票 43）
4. 演示机 \`make up\` 后 \`make health\` 全 ok，\`make db-backup\` 一次

## 回滚

\`make rollback REL=<上一版 release_id>\`：切回该版 config/ 并重启编排服务，5 分钟内健康检查通过即完成；不涉及数据迁移（迁移只前向，见 docs/runbook/database.md §4）。知识库回滚 \`make kb-snapshot DIR=…\`。
MD
echo "RELEASE.md written for $REL; config snapshot at releases/$REL/config"
