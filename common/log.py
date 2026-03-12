from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    _ensure_configured()
    return logging.getLogger(name)


def _ensure_configured() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root = logging.getLogger("decoupling")
    root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
