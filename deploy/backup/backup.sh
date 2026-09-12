#!/usr/bin/env bash
# PostgreSQL 逻辑备份（票 47）。用法：
#   backup.sh loop   —— 常驻：每 BACKUP_INTERVAL_S（默认 86400）备份一次并清理超过 RETENTION_DAYS（默认 7）天的文件
#   backup.sh once   —— 立即备份一次后退出
# 环境：PGHOST PGUSER PGPASSWORD（compose 注入）、BACKUP_DBS（空格分隔，默认 "haike WeKnora"）、BACKUP_DIR（默认 /backups）
set -euo pipefail
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_DBS:=haike WeKnora}"
: "${BACKUP_INTERVAL_S:=86400}"
: "${RETENTION_DAYS:=7}"
mkdir -p "$BACKUP_DIR"
LOG="$BACKUP_DIR/backup.log"

log() { local line; line="$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; echo "$line"; echo "$line" >> "$LOG"; }

backup_once() {
  local ts files=() db out
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  for db in $BACKUP_DBS; do
    out="$BACKUP_DIR/${db}_${ts}.dump"
    if pg_dump -Fc --no-owner --no-acl -d "$db" -f "$out.part"; then
      mv "$out.part" "$out"; files+=("$out")
      log "ok db=$db file=$(basename "$out") bytes=$(stat -c %s "$out" 2>/dev/null || stat -f %z "$out")"
    else
      rm -f "$out.part"; log "FAIL db=$db"; return 1
    fi
  done
  printf '%s\n%s\n' "$ts" "${files[*]}" > "$BACKUP_DIR/last_success"
  local removed
  removed=$(find "$BACKUP_DIR" -name '*.dump' -mtime +"$RETENTION_DAYS" -print -delete | wc -l | tr -d ' ')
  log "prune removed=$removed retention_days=$RETENTION_DAYS"
}

case "${1:-loop}" in
  once) backup_once ;;
  loop)
    log "start interval_s=$BACKUP_INTERVAL_S dbs='$BACKUP_DBS'"
    while true; do
      backup_once || log "backup round failed; will retry next interval"
      sleep "$BACKUP_INTERVAL_S"
    done ;;
  *) echo "usage: $0 [loop|once]" >&2; exit 2 ;;
esac
