"""``python -m leadforge_worker`` — run the worker until SIGINT/SIGTERM."""

from __future__ import annotations

from leadforge_core.db import build_session_factory, engine_from_settings
from leadforge_core.log import configure_logging
from leadforge_worker.handlers import default_registry
from leadforge_worker.settings import WorkerSettings
from leadforge_worker.worker import Worker


def main() -> None:
    settings = WorkerSettings()  # populated from the environment
    configure_logging(settings.log_level, json_output=settings.log_json)
    engine = engine_from_settings(settings)
    try:
        worker = Worker(build_session_factory(engine), default_registry(), settings)
        worker.install_signal_handlers()
        worker.run_forever()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
