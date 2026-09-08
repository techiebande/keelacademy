#!/usr/bin/env bash
# 50-backup.sh — nightly Postgres dump with 7-day retention via /etc/cron.d.
# Reads DB credentials through the running keel-pg container (no secrets in
# the cron entry). Restores with:
#   gunzip -c /var/backups/keel/keel-YYYY-MM-DD.sql.gz | \
#     docker exec -i keel-pg psql -U <user> -d grading
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

install -d -m 700 -o ubuntu -g ubuntu /var/backups/keel

cat > /etc/cron.d/keel-backup <<'CRON'
# nightly grading-DB dump, 02:20 UTC, keep 7
20 2 * * * ubuntu /bin/bash -c \
  'set -e; f=/var/backups/keel/keel-$(date -u +%F).sql.gz; \
   docker exec keel-pg pg_dump -U keel -d grading | gzip > "$f"; \
   ls -1t /var/backups/keel/keel-*.sql.gz | tail -n +8 | xargs -r rm --'
CRON
chmod 644 /etc/cron.d/keel-backup

echo "50-backup.sh OK — first dump lands at 02:20 UTC; test one now with:"
echo "  docker exec keel-pg pg_dump -U keel -d grading | gzip > /var/backups/keel/keel-test.sql.gz"
