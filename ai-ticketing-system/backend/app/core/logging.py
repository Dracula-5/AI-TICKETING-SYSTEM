"""
Structured (JSON-lines) logging configuration. No new dependency — a small
logging.Formatter subclass is enough for container-friendly stdout logs that
any log aggregator (CloudWatch, Loki, Datadog, ...) can parse directly.
"""
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Any extra=... fields passed to the log call are merged in verbatim.
        standard_keys = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
        for key, value in record.__dict__.items():
            if key not in standard_keys and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
