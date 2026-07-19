"""CLI entrypoint for the DocRunr API."""

from __future__ import annotations

import logging

import uvicorn

from docrunr_api.app import create_app
from docrunr_api.config import ApiSettings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = ApiSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
