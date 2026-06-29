#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] WatchVault starting…"

# Run forward-only, checksum-guarded migrations BEFORE serving traffic.
# Aborts the container on schema drift (see migrations_runner).
python /app/backend/migrate.py

echo "[entrypoint] migrations applied — launching supervisor."
exec supervisord -c /etc/supervisor/conf.d/watchvault.conf
