#!/usr/bin/env bash
# 票 46：扫描仓库（已跟踪文件）与镜像里有没有真实密钥。用法：scripts/scan-secrets.sh [镜像名]
set -uo pipefail
cd "$(dirname "$0")/.."
PAT='\bsk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AIza[0-9A-Za-z_-]{35}'
rc=0
echo "== git 跟踪文件"
# 允许：测试用的占位串（sk-test-…）或行尾标注 scan-secrets:allow
if git grep -nE "$PAT" -- ':!*.lock' ':!package-lock.json' | grep -vE 'sk-test-|scan-secrets:allow' | grep .; then echo "!! 发现疑似密钥"; rc=1; else echo "ok"; fi
echo "== .env 是否被跟踪"
if git ls-files --error-unmatch .env >/dev/null 2>&1; then echo "!! .env 已被 git 跟踪"; rc=1; else echo "ok"; fi
echo "== .env.example 的密钥项必须为空"
if grep -E '^[A-Z_]*(KEY|SECRET|TOKEN)=[^ #]+' .env.example | grep -vE '=(text-embedding|gte-|haike-dev-)' ; then echo "!! .env.example 里有非空密钥"; rc=1; else echo "ok"; fi
if [ -n "${1:-}" ]; then
  echo "== 镜像 $1"
  if docker run --rm --entrypoint sh "$1" -c "test ! -e /srv/.env && ! grep -rIE '$PAT' /srv/app /srv/config /srv/static 2>/dev/null"; then echo "ok（无 .env，无密钥字样）"; else echo "!! 镜像内发现 .env 或密钥字样"; rc=1; fi
fi
exit $rc
