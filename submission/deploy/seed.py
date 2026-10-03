"""One-shot demo seeder for the Tablekeeper public demo stack.

Runs inside the internal docker network where the app's /_test/* routes are
reachable. Waits for /health, then POSTs the product's own synthetic
demo_seed() fixture to /_test/reset. Never touches the public proxy.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, "src")
import fixtures  # noqa: E402  (app image WORKDIR is /app)

APP_URL = os.environ.get("APP_URL", "http://app:8080").rstrip("/")


def _get(path):
    with urllib.request.urlopen(APP_URL + path, timeout=5) as resp:
        return resp.status


def _post(path, body):
    req = urllib.request.Request(
        APP_URL + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def main():
    deadline = time.time() + 60
    while True:
        try:
            if _get("/health") == 200:
                break
        except Exception:
            pass
        if time.time() > deadline:
            sys.exit("app did not become healthy within 60s")
        time.sleep(1)

    status = _post("/_test/reset", fixtures.demo_seed())
    if status != 204:
        sys.exit(f"seed reset returned {status}")
    print("seeded synthetic demo fixture via internal /_test/reset")


if __name__ == "__main__":
    main()
