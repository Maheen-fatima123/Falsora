"""Consistent logging across the AI engine.

Scripts print progress; libraries log. Every module here uses ``get_logger``
so that Ujala's FastAPI process can capture our output through standard logging
configuration rather than having stray ``print`` calls appear in the server log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

__all__ = ["get_logger", "configure_logging"]

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
_DATEFMT = "%H:%M:%S"
_configured = False


def configure_logging(
    level: int | str = logging.INFO,
    log_file: str | Path | None = None,
) -> None:
    """Configure the root logger once. Repeat calls are ignored."""
    global _configured
    if _configured:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger. Safe to call at module import time."""
    return logging.getLogger(name)
