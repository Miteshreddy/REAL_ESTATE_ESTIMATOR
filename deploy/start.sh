#!/bin/sh
# Container start: SearXNG (private, 127.0.0.1:8888) in the background, then the PWD Estimator on $PORT.
set -e
mkdir -p "${EST_DATA_DIR:-/var/data}"
SECRET="${SEARXNG_SECRET:-$(python -c 'import secrets;print(secrets.token_hex(32))')}"
sed "s/__SEARXNG_SECRET__/${SECRET}/" /app/deploy/searxng/settings.yml > /tmp/searxng.yml
if [ "${SEARXNG_ENABLED:-1}" = "1" ]; then
  (cd /opt/searxng && SEARXNG_SETTINGS_PATH=/tmp/searxng.yml /opt/searxng-venv/bin/python -m searx.webapp > /tmp/searxng.log 2>&1 &)
fi
# the Llama model ships through Git LFS; if the host cloned only the LFS pointer, fetch the exact file once (checksum verified)
python /app/deploy/ensure_model.py || echo "[start] Llama model unavailable - the app runs without written summaries"
exec python -m uvicorn app:app --app-dir /app/backend --host 0.0.0.0 --port "${PORT:-8000}"
