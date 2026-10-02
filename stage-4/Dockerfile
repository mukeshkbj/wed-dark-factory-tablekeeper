FROM python:3.12-slim

# IANA timezone database for zoneinfo (needed for DST-correct local times).
# Build-time network fetch is permitted; nothing external is used at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "src/server.py"]
