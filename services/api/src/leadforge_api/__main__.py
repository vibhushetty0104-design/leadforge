"""``python -m leadforge_api`` — run the API with uvicorn."""

from __future__ import annotations

import uvicorn

from leadforge_api.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "leadforge_api.app:app",
        host=settings.host,
        port=settings.port,
        log_config=None,  # logging is configured by create_app
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        server_header=False,
    )


if __name__ == "__main__":
    main()
