import json
import logging
import traceback
from datetime import UTC, datetime


class SimpleFormatter(logging.Formatter):
    def __init__(self):
        super().__init__(fmt="[%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")


class DetailedFormatter(logging.Formatter):
    def __init__(self):
        super().__init__(fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).isoformat()
        parts = [
            f"timestamp={timestamp}",
            f"level={record.levelname}",
            f"module={record.name}",
            f'message="{record.getMessage()}"',
        ]

        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ]:
                    if isinstance(value, str):
                        parts.append(f'{key}="{value}"')
                    elif isinstance(value, int | float | bool):
                        parts.append(f"{key}={value}")
                    else:
                        parts.append(f'{key}="{str(value)}"')

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            exc_text_escaped = exc_text.replace("\n", "\\n")
            parts.append(f'exception="{exc_text_escaped}"')

        return " ".join(parts)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "function": record.funcName,
            "line_number": record.lineno,
            "thread_id": record.thread,
            "process_id": record.process,
        }

        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data, ensure_ascii=False)


def get_formatter(format_type: str) -> logging.Formatter:
    formatters: dict[str, type[logging.Formatter]] = {
        "simple": SimpleFormatter,
        "detailed": DetailedFormatter,
        "structured": StructuredFormatter,
        "json": JSONFormatter,
    }

    formatter_class = formatters.get(format_type.lower())
    if formatter_class is None:
        raise ValueError(f"Unknown format type: {format_type}. Available: {', '.join(formatters.keys())}")

    return formatter_class()
