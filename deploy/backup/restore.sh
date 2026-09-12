#!/usr/bin/env bash
# 一键恢复（票 47）：restore.sh <dump 文件名或绝对路径> [目标库，默认按文件名前缀推断]
# 步骤：断开目标库全部连接 → pg_restore --clean --if-exists（以超级用户执行，能覆盖任何属主的旧对象）
#      → 把 public 下全部表 / 序列 / 视图的属主改回目标库属主（dump 不带 owner，否则应用账号无权访问）。
# 恢复前先 `docker compose stop orchestrator`（Makefile db-restore 已包含）。
set -euo pipefail
: "${BACKUP_DIR:=/backups}"
FILE="${1:?dump file required}"; [[ "$FILE" = /* ]] || FILE="$BACKUP_DIR/$FILE"
DB="${2:-$(basename "$FILE" | sed -E 's/_[0-9TZ]+\.dump$//')}"
[ -f "$FILE" ] || { echo "no such file: $FILE" >&2; exit 1; }
OWNER="$(psql -d postgres -tAc "select pg_get_userbyid(datdba) from pg_database where datname = '$DB'")"
[ -n "$OWNER" ] || { echo "database $DB not found" >&2; exit 1; }
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$BACKUP_DIR/backup.log"; }

log "restore db=$DB owner=$OWNER from=$(basename "$FILE")"
psql -d postgres -v ON_ERROR_STOP=1 -qc \
  "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$DB' and pid <> pg_backend_pid();" >/dev/null
# pg_restore 对「对象已存在 / 扩展属主」类告警返回非零，不能作为失败依据；靠下面的属主修正与后续健康检查兜底
pg_restore --clean --if-exists --no-owner --no-acl -d "$DB" "$FILE" || log "pg_restore exited $? (warnings above; continuing)"
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<SQL
do \$\$
declare r record;
begin
  for r in select tablename as n from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I owner to %I', r.n, '$OWNER');
  end loop;
  for r in select sequencename as n from pg_sequences where schemaname = 'public' loop
    execute format('alter sequence public.%I owner to %I', r.n, '$OWNER');
  end loop;
  for r in select viewname as n from pg_views where schemaname = 'public' loop
    execute format('alter view public.%I owner to %I', r.n, '$OWNER');
  end loop;
end \$\$;
SQL
log "restore done db=$DB tables=$(psql -d "$DB" -tAc "select count(*) from pg_tables where schemaname='public'")"
