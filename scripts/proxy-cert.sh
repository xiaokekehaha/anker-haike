#!/usr/bin/env bash
# 生成自签证书到 deploy/proxy/certs/（演示 / 内网用）。线上把 CA 签发的 fullchain.pem / privkey.pem 放同一目录即可。
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:-localhost}"; OUT=deploy/proxy/certs; mkdir -p "$OUT"
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout "$OUT/privkey.pem" -out "$OUT/fullchain.pem" \
  -subj "/CN=$HOST" -addext "subjectAltName=DNS:$HOST,DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
chmod 600 "$OUT/privkey.pem"; echo "self-signed cert for $HOST -> $OUT/ (gitignored)"
