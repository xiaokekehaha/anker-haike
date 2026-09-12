#!/usr/bin/env bash
# 生成 / 追加基础认证账号到 deploy/proxy/.htpasswd（bcrypt）。用法：scripts/proxy-passwd.sh <user> [password]
# 不传密码则随机生成并打印一次；文件已 gitignore，不进镜像。
set -euo pipefail
cd "$(dirname "$0")/.."
USER_="${1:?user required}"; PASS="${2:-$(openssl rand -base64 18)}"
FILE=deploy/proxy/.htpasswd; touch "$FILE"
if command -v htpasswd >/dev/null; then htpasswd -B -b "$FILE" "$USER_" "$PASS" >/dev/null
else printf '%s:%s\n' "$USER_" "$(openssl passwd -apr1 "$PASS")" >> "$FILE"; fi
chmod 600 "$FILE"; echo "user=$USER_ password=$PASS  (written to $FILE; 只显示这一次)"
