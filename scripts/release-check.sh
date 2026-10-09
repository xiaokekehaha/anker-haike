#!/usr/bin/env bash
# 校验 RELEASE.md 抬头声明的版本与仓库现状一致（票 49 配套）。
#
# 为什么需要：RELEASE.md 由 scripts/release.sh 从真实来源生成，但生成后会被手工补注，
# 之后 config/ 再改动就没人重新生成，清单于是悄悄失真——曾出现清单写 models.yaml
# 2026-09-13.1、bake-off 报告写 .2、实际已是 .3 的情况。冻结清单一旦对不上实际部署，
# 回滚与验收都失去依据，所以这里让漂移直接非零退出。
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
note() { printf '  %s\n' "$1"; }
check() { # check <项> <期望(实际值)> <清单中声明值>
  if [ "$2" = "$3" ]; then
    printf '✓ %-22s %s\n' "$1" "$2"
  else
    printf '✗ %-22s 实际 %s ≠ 清单 %s\n' "$1" "$2" "$3"
    fail=1
  fi
}

if [ ! -f RELEASE.md ]; then
  echo "RELEASE.md 不存在，先跑 make release"
  exit 1
fi

ver() { grep -m1 -E '^version:' "$1" 2>/dev/null | awk '{print $2}'; }
pyconst() { grep -m1 -E "^$2\s*=" "$1" 2>/dev/null | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/'; }
# 取 RELEASE.md 表格里某一行的值列，剥掉反引号与括号补注
declared() { grep -m1 -E "^\| $1 \|" RELEASE.md | awk -F'|' '{print $3}' | sed -E 's/^ *//; s/ *$//; s/`//g; s/（.*//'; }

check "models.yaml"   "$(ver config/models.yaml)"              "$(declared 'models.yaml')"
check "rules_ver"     "$(ver config/rules/safety_terms.yaml)"  "$(declared 'rules_ver')"
QA_VER="$(grep -m1 -oE 'sha256=[0-9a-f]{12}' data/official/qa.yaml | cut -d= -f2 || echo "-")"
check "products/官方 Q&A" "$(ver config/products.yaml) / ${QA_VER}" "$(declared 'products / 官方 Q&A')"
check "prompt_ver" \
  "system $(pyconst orchestrator/app/prompts/system.py PROMPT_VERSION) / reply $(pyconst orchestrator/app/prompts/reply.py REPLY_PROMPT_VERSION)" \
  "$(declared 'prompt_ver')"

head_rev="$(cd orchestrator && uv run --no-sync python -c 'from app.db.migrations import head_revision; print(head_revision())' 2>/dev/null || echo '-')"
check "业务表迁移 head" "$head_rev" "$(declared '业务表迁移 head')"

if [ -f data/knowledge/manifest.json ]; then
  check "kb_ver" \
    "$(python3 -c "import json;print(json.load(open('data/knowledge/manifest.json'))['kb_ver'])")" \
    "$(declared 'kb_ver')"
fi

# bake-off 报告记录的是「跑评测时」的 models.yaml 版本：与当前不一致说明模型配置改过而没重跑，
# 报告里的裁决不能再作为冻结依据（票 42）。
if [ -f reports/bakeoff/bakeoff.md ]; then
  bo="$(head -1 reports/bakeoff/bakeoff.md | sed -E 's/.*models\.yaml ([^,）]+).*/\1/')"
  cur="$(ver config/models.yaml)"
  if [ "$bo" = "$cur" ]; then
    printf '✓ %-22s %s\n' "bake-off 报告" "$bo"
  else
    printf '✗ %-22s 报告基于 %s，当前 %s —— 需重跑 make bakeoff\n' "bake-off 报告" "$bo" "$cur"
    fail=1
  fi
fi

# 回放包与模型配置同源：模型配置改版后旧包会 replay-verify 失败（见 overall-acceptance/findings.md）
if [ "$fail" = 0 ]; then
  echo "RELEASE.md 与仓库现状一致"
else
  echo
  note "修复：改完 config/ 后重新生成清单 —— make release"
  note "若模型配置变更，还需 make bakeoff 重跑评测、make replay-record 重录回放包"
fi
exit "$fail"
