"""Business logic — plain Python, no Modal imports. Runs anywhere."""

import structlog

log = structlog.get_logger()


def run(payload: dict) -> dict:
    log.info("processing", payload=payload)
    # TODO: Spotify -> Notion sync pipeline goes here
    return {"ok": True, "received": payload}
