"""ASGI entry point: ``uvicorn leadforge_api.app:app``."""

from leadforge_api.main import create_app

app = create_app()
