from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "sailwind_mod_sync"


def setup_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    target = str(log_file.resolve())
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == Path(target):
            return logger
        if isinstance(handler, RotatingFileHandler):
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        target,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.info("Logging to %s", target)
    return logger


@contextmanager
def log_duration(logger: logging.Logger, message: str) -> Iterator[None]:
    started = time.perf_counter()
    logger.info("start %s", message)
    try:
        yield
    except Exception:
        logger.exception("failed %s after %.1fs", message, time.perf_counter() - started)
        raise
    logger.info("done %s (%.1fs)", message, time.perf_counter() - started)
