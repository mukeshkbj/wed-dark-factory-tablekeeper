# All-in-one Tablekeeper demo image — for single-container hosts
# (Render, Railway, Fly.io, Cloud Run, a VPS, ...).
#
# One container, two listeners: nginx on the public port ($PORT or 80)
# blocks /_test* and proxies to the app on an internal port (18080) that is
# NEVER published. The app stays in seedable judge mode; a startup seed step
# loads the synthetic fixture over loopback before traffic matters.
#
# Build context must be the REPOSITORY ROOT:
#   docker build -f submission/deploy/single/Dockerfile -t tablekeeper-demo .

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

# Frozen product tree — unchanged.
COPY stage-4/ /app/
COPY submission/deploy/seed.py /app/seed.py
COPY submission/deploy/single/nginx.single.conf /etc/nginx/conf.d/default.conf
COPY submission/deploy/single/start.sh /app/start.sh

RUN chmod +x /app/start.sh

# Public port. Hosts that inject their own port set $PORT (e.g. Cloud Run).
EXPOSE 80

CMD ["/app/start.sh"]
