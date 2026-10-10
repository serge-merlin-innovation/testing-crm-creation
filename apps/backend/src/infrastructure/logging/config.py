import contextvars
import inspect
import logging
import logging.config
import threading
import uuid

from ..config import LogFormat
from ..config.settings import EnvironmentOption, get_settings
from .handlers import (
    create_console_handler,
    create_file_handler,
    create_null_handler,
)


def setup_logging_configuration() -> None:
    settings = get_settings()

    logging.getLogger().handlers.clear()

    if settings.ENVIRONMENT == EnvironmentOption.DEVELOPMENT:
        _configure_development_logging(settings)
    elif settings.ENVIRONMENT == EnvironmentOption.STAGING:
        _configure_staging_logging(settings)
    elif settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        _configure_production_logging(settings)
    else:
        _configure_development_logging(settings)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL_INT)

    if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        _configure_noisy_loggers()


def _configure_development_logging(settings) -> None:
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_level = logging.DEBUG if settings.LOG_DEVELOPMENT_VERBOSE else settings.LOG_LEVEL_INT
        console_handler = create_console_handler(format_type=LogFormat.DETAILED.value, level=console_level, use_colors=True)
        handlers.append(console_handler)

    if settings.LOG_FILE_ENABLED:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=LogFormat.STRUCTURED.value,
            level=logging.DEBUG,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_staging_logging(settings) -> None:
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_handler = create_console_handler(
            format_type=LogFormat.STRUCTURED.value,
            level=settings.LOG_LEVEL_INT,
            use_colors=False,
        )
        handlers.append(console_handler)

    file_enabled = settings.LOG_FILE_ENABLED
    if file_enabled:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=LogFormat.STRUCTURED.value,
            level=logging.DEBUG,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_production_logging(settings) -> None:
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_level = logging.WARNING if settings.LOG_PRODUCTION_OPTIMIZE else settings.LOG_LEVEL_INT
        console_handler = create_console_handler(format_type=LogFormat.JSON.value, level=console_level, use_colors=False)
        handlers.append(console_handler)

    if settings.LOG_FILE_ENABLED:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=LogFormat.JSON.value,
            level=settings.LOG_LEVEL_INT,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_noisy_loggers() -> None:
    noisy_loggers = {
        "urllib3.connectionpool": logging.WARNING,
        "requests.packages.urllib3": logging.WARNING,
        "asyncpg": logging.WARNING,
        "sqlalchemy.engine": logging.WARNING,
        "sqlalchemy.dialects": logging.WARNING,
        "sqlalchemy.pool": logging.WARNING,
    }

    for logger_name, level in noisy_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def configure_testing_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    root_logger.addHandler(create_null_handler())

    root_logger.setLevel(logging.ERROR)

    test_loggers = {
        "sqlalchemy.engine": logging.ERROR,
        "asyncpg": logging.ERROR,
    }

    for logger_name, level in test_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def get_configured_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def add_correlation_id_filter() -> None:
    root_logger = logging.getLogger()
    correlation_filter = CorrelationIdFilter()
    root_logger.addFilter(correlation_filter)


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            correlation_id = self._get_correlation_id()
        except Exception:
            correlation_id = None

        setattr(record, "correlation_id", correlation_id or "no-correlation")

        if not hasattr(record, "extra"):
            setattr(record, "extra", {})
        getattr(record, "extra")["correlation_id"] = getattr(record, "correlation_id")

        return True

    def _get_correlation_id(self) -> str | None:
        try:
            correlation_id = correlation_id_var.get()
            if correlation_id:
                return correlation_id
        except (LookupError, AttributeError):
            pass

        try:
            thread_local = getattr(threading.current_thread(), "correlation_id", None)
            if thread_local:
                return str(thread_local)
        except AttributeError:
            pass

        try:
            frame = inspect.currentframe()
            while frame:
                if "request" in frame.f_locals:
                    request = frame.f_locals["request"]
                    if hasattr(request, "state") and hasattr(request.state, "correlation_id"):
                        return str(request.state.correlation_id)
                    if hasattr(request, "headers"):
                        correlation_id = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
                        if correlation_id:
                            return str(correlation_id)
                frame = frame.f_back
        except Exception:
            pass

        return None


correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id")


def set_correlation_id(correlation_id: str) -> None:
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    try:
        return correlation_id_var.get()
    except LookupError:
        return None


def generate_correlation_id() -> str:
    return str(uuid.uuid4())


def reconfigure_logger_level(logger_name: str, level: int) -> None:
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    logging.getLogger(__name__).info(f"Logger level changed: {logger_name} -> {logging.getLevelName(level)}")
