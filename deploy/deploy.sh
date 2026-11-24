#!/usr/bin/env bash
set -euo pipefail
cd /opt/lab-agent
exec 9>.deploy.lock
flock -w 600 9
service="${1:-all}"
case "$service" in api|web|all) ;; *) echo 'Expected api, web, or all' >&2; exit 1 ;; esac
if [ "$service" = all ]; then
  docker compose pull
else
  docker compose pull "$service"
fi
docker compose up -d --wait redis
if [ "$service" != web ]; then
  docker compose run --rm --no-deps api /app/.venv/bin/alembic upgrade head
fi
# Recreate web after API replacement to refresh Nginx upstream DNS.
if [ "$service" = api ] || [ "$service" = all ]; then
  docker compose up -d --wait --wait-timeout 180 api
  docker compose up -d --wait --wait-timeout 180 --force-recreate web
else
  docker compose up -d --wait --wait-timeout 180 web
fi
docker compose ps
