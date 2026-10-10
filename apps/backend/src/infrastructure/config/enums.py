from enum import StrEnum


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    SIMPLE = "simple"
    DETAILED = "detailed"
    STRUCTURED = "structured"
    JSON = "json"
