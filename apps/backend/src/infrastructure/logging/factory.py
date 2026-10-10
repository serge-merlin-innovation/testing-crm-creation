import inspect
import logging
from collections.abc import MutableMapping
from threading import Lock
from typing import Any, Union

from ..config.settings import get_settings
from .config import get_configured_logger, setup_logging_configuration

_logging_configured = False
_configuration_lock = Lock()


def get_logger(name: str | None = None, **extra_context) -> logging.Logger | logging.LoggerAdapter:
    _ensure_logging_configured()

    if name is None:
        name = _detect_calling_module()

    base_logger = get_configured_logger(name)

    if extra_context:
        logger: logging.Logger | logging.LoggerAdapter = logging.LoggerAdapter(base_logger, extra_context)
    else:
        logger = base_logger

    return logger


def configure_logging() -> None:
    global _logging_configured

    with _configuration_lock:
        if not _logging_configured:
            setup_logging_configuration()
            _logging_configured = True

            logger = logging.getLogger(__name__)
            try:
                settings = get_settings()
                logger.info(
                    f"Logging configured for {settings.ENVIRONMENT.value} environment",
                    extra={
                        "log_level": settings.LOG_LEVEL,
                        "log_format": settings.LOG_FORMAT,
                        "console_enabled": settings.LOG_CONSOLE_ENABLED,
                        "file_enabled": settings.LOG_FILE_ENABLED,
                    },
                )
            except Exception:
                logger.info("Logging configured for development environment")


def _ensure_logging_configured() -> None:
    global _logging_configured

    if not _logging_configured:
        configure_logging()


def _detect_calling_module() -> str:
    frame = inspect.currentframe()

    try:
        for _ in range(3):
            if frame is None:
                break
            frame = frame.f_back

        if frame is not None:
            module_name = frame.f_globals.get("__name__", "unknown")
            return str(module_name)
        else:
            return "unknown"

    finally:
        del frame


class LoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, extra: dict[str, Any]):
        super().__init__(logger, extra)

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.get("extra", {})

        adapter_extra = self.extra if isinstance(self.extra, dict) else {}
        if isinstance(extra, dict):
            merged_extra = {**adapter_extra, **extra}
        else:
            merged_extra = adapter_extra

        kwargs["extra"] = merged_extra

        return msg, kwargs


def create_child_logger(
    parent_logger: logging.Logger, child_name: str, **extra_context
) -> Union[logging.Logger, "LoggerAdapter"]:
    child_logger_name = f"{parent_logger.name}.{child_name}"
    base_child_logger = get_configured_logger(child_logger_name)

    if extra_context:
        child_logger: logging.Logger | LoggerAdapter = LoggerAdapter(base_child_logger, extra_context)
    else:
        child_logger = base_child_logger

    return child_logger


def get_logger_with_correlation_id(correlation_id: str, name: str | None = None) -> LoggerAdapter:
    logger = get_logger(name)
    if isinstance(logger, logging.LoggerAdapter):
        base_logger = logger.logger
    else:
        base_logger = logger
    return LoggerAdapter(base_logger, {"correlation_id": correlation_id})
