#!/usr/bin/env bash
# 20-postgres.sh — Postgres 16 container (data in the keel-pg-data volume,
# localhost only) plus the grading schema, migrations 0001..0014 in order.
# Reads POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB from
# /etc/keelacademy/env. Idempotent: container is kept, schema files run in
# order with ON_ERROR_STOP, so a re-run fails loudly rather than half-applying.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

ENV_FILE=/etc/keelacademy/env
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE — copy env.grading-host.example first" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"

if [ "$POSTGRES_PASSWORD" = "CHANGE_ME_STRONG" ]; then
    echo "FATAL: POSTGRES_PASSWORD is still the template value" >&2
    exit 1
fi

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCHEMA_DIR="$REPO_DIR/platform/grading/schema"
[ -d "$SCHEMA_DIR" ] || { echo "schema dir not found: $SCHEMA_DIR" >&2; exit 1; }

echo "== starting keel-pg (127.0.0.1:5432, restart always) =="
docker inspect keel-pg >/dev/null 2>&1 || \
    docker run -d --name keel-pg --restart always \
        -e POSTGRES_USER="$POSTGRES_USER" \
        -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
        -e POSTGRES_DB="$POSTGRES_DB" \
        -v keel-pg-data:/var/lib/postgresql/data \
        -p 127.0.0.1:5432:5432 postgres:16

until docker exec keel-pg pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
    sleep 1
done
echo "postgres ready"

echo "== applying schema 0001..0014 (ON_ERROR_STOP) =="
for f in "$SCHEMA_DIR"/*.sql; do
    echo "  -> $(basename "$f")"
    docker exec -i keel-pg psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 < "$f"
done

docker exec keel-pg psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "select count(*) from information_schema.tables where table_schema='public'"
echo "20-postgres.sh OK — schema applied"
