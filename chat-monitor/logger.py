"""
logger.py — Structured JSON logging with rotation.
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone


LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")


class JsonLineFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        # Access record.msg directly before getMessage() coerces it to str.
        if isinstance(record.msg, dict):
            entry = record.msg
        else:
            entry = {"message": record.getMessage()}

        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        entry.setdefault("level", record.levelname)

        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False)


class StructuredLogger(logging.Logger):
    """Logger with a .structured() helper for emitting dict payloads."""

    def structured(self, data: dict, level: int = logging.INFO) -> None:
        if self.isEnabledFor(level):
            record = self.makeRecord(
                self.name, level, "(structured)", 0, data, (), None
            )
            self.handle(record)


# Set at module level so it applies consistently without affecting other modules
# that import logging before setup_logger is called.
logging.setLoggerClass(StructuredLogger)


def setup_logger(
    name: str = "chat_monitor",
    log_max_bytes: int = 5 * 1024 * 1024,
    log_backup_count: int = 5,
) -> StructuredLogger:
    """
    Build and return a StructuredLogger writing JSON lines to:
      - logs/monitor.log  (rotating file)
      - stdout            (human-readable single-line JSON)
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "monitor.log")

    logger: StructuredLogger = logging.getLogger(name)  # type: ignore[assignment]
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    fmt = JsonLineFormatter()

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
