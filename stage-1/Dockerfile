FROM python:3.12-slim

# tzdata gives zoneinfo a full IANA database on the slim base image.
# Installed at build time; the runtime needs no outbound network.
RUN pip install --no-cache-dir tzdata

WORKDIR /app
COPY src ./src

ENV PORT=8080
EXPOSE 8080

CMD ["python", "src/server.py"]
