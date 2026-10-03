#!/bin/sh
# Single-container demo entrypoint:
#   1. app on 127.0.0.1:18080 (internal — never published)
#   2. seed the synthetic fixture via loopback /_test/reset
#   3. nginx on the public port ($PORT or 80) blocks /_test*
set -e

APP_PORT=18080
PUBLIC_PORT="${PORT:-80}"

PORT=$APP_PORT python src/server.py &
APP_PID=$!

trap 'kill $APP_PID 2>/dev/null' EXIT

# Wait for the app, then load the synthetic demo fixture over loopback.
APP_URL="http://127.0.0.1:$APP_PORT" python /app/seed.py

sed -i "s/__PORT__/$PUBLIC_PORT/" /etc/nginx/conf.d/default.conf

# nginx becomes the foreground process; SIGTERM still reaches the trap.
exec nginx -g 'daemon off;'
