#!/usr/bin/env bash
# 首次初始化时执行：在 WeKnora 的 PostgreSQL 实例里额外建编排服务自己的库与用户。
set -euo pipefail
: "${HAIKE_DB_USER:=haike}"
: "${HAIKE_DB_PASSWORD:=haike}"
: "${HAIKE_DB_NAME:=haike}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${HAIKE_DB_USER}') THEN
    CREATE ROLE ${HAIKE_DB_USER} LOGIN PASSWORD '${HAIKE_DB_PASSWORD}';
  END IF;
END
\$\$;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -tc "SELECT 1 FROM pg_database WHERE datname = '${HAIKE_DB_NAME}'" | grep -q 1 || \
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE ${HAIKE_DB_NAME} OWNER ${HAIKE_DB_USER}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${HAIKE_DB_NAME}" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
