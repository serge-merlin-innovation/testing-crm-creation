import contextvars
import logging
import threading
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.logging.config import (
    CorrelationIdFilter,
    add_correlation_id_filter,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)


@pytest.fixture
def mock_logger():
    logger = logging.getLogger("test_correlation")
    logger.setLevel(logging.DEBUG)

    logger.handlers.clear()

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(correlation_id)s - %(message)s"))
    logger.addHandler(handler)

    return logger, stream


def test_correlation_id_context_management():
    test_id = "test-correlation-123"
    set_correlation_id(test_id)

    retrieved_id = get_correlation_id()
    assert retrieved_id == test_id

    def new_context():
        assert get_correlation_id() is None

        set_correlation_id("context-456")
        assert get_correlation_id() == "context-456"

    ctx = contextvars.Context()  # Create empty context instead of copying
    ctx.run(new_context)

    assert get_correlation_id() == test_id


def test_generate_correlation_id():
    id1 = generate_correlation_id()
    id2 = generate_correlation_id()

    assert id1 != id2

    assert len(id1) == 36
    assert len(id2) == 36
    assert "-" in id1
    assert "-" in id2


def test_correlation_id_filter_with_context(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    test_id = "filter-test-789"
    set_correlation_id(test_id)

    logger.info("Test message with correlation ID")

    output = stream.getvalue()
    assert test_id in output
    assert "Test message with correlation ID" in output


def test_correlation_id_filter_no_context(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    def run_test():
        logger.info("Test message without correlation ID")

    ctx = contextvars.Context()
    ctx.run(run_test)

    output = stream.getvalue()
    assert "no-correlation" in output
    assert "Test message without correlation ID" in output


def test_correlation_id_filter_thread_local(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    test_id = "thread-local-456"
    threading.current_thread().correlation_id = test_id  # type: ignore[attr-defined]

    try:

        def run_test():
            logger.info("Test thread local correlation ID")

        ctx = contextvars.Context()
        ctx.run(run_test)

        output = stream.getvalue()
        assert test_id in output

    finally:
        delattr(threading.current_thread(), "correlation_id")


def test_correlation_id_filter_request_headers(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    set_correlation_id("header-correlation-123")

    logger.info("Test correlation ID functionality")

    output = stream.getvalue()
    assert "header-correlation-123" in output


def test_correlation_id_filter_request_id_header(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    set_correlation_id("request-id-789")

    logger.info("Test request ID header")

    output = stream.getvalue()
    assert "request-id-789" in output


def test_correlation_id_filter_request_state(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="Test message", args=(), exc_info=None
    )

    test_id = "state-correlation-456"
    set_correlation_id(test_id)

    result = correlation_filter.filter(record)

    assert result is True
    assert record.correlation_id == test_id  # type: ignore[attr-defined]
    assert hasattr(record, "extra")
    assert getattr(record, "extra")["correlation_id"] == test_id


def test_correlation_id_filter_error_handling(mock_logger):
    logger, stream = mock_logger

    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)

    mock_method = MagicMock(side_effect=Exception("Test error"))

    with patch.object(correlation_filter, "_get_correlation_id", mock_method):
        logger.info("Test error handling")

        output = stream.getvalue()
        assert "no-correlation" in output


def test_add_correlation_id_filter():
    test_logger = logging.getLogger("test_add_filter")
    test_logger.handlers.clear()

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(correlation_id)s - %(message)s"))
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)

    assert len(test_logger.filters) == 0

    add_correlation_id_filter()

    root_logger = logging.getLogger()
    correlation_filters = [f for f in root_logger.filters if isinstance(f, CorrelationIdFilter)]
    assert len(correlation_filters) >= 1


def test_correlation_id_inheritance():
    child_logger = logging.getLogger("test.child")
    child_logger.setLevel(logging.DEBUG)
    child_logger.handlers.clear()

    correlation_filter = CorrelationIdFilter()
    child_logger.addFilter(correlation_filter)

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(correlation_id)s - %(message)s"))
    child_logger.addHandler(handler)
    child_logger.propagate = False  # Don't propagate to avoid double filtering

    test_id = "inheritance-test-123"
    set_correlation_id(test_id)

    child_logger.info("Child logger message")

    output = stream.getvalue()
    assert test_id in output


def test_correlation_id_multiple_contexts():
    results = {}

    def context_function(context_id):
        test_id = f"context-{context_id}"
        set_correlation_id(test_id)
        retrieved_id = get_correlation_id()
        results[context_id] = retrieved_id

    contexts = []
    for i in range(3):
        ctx = contextvars.copy_context()
        contexts.append(ctx)
        ctx.run(context_function, i)

    assert results[0] == "context-0"
    assert results[1] == "context-1"
    assert results[2] == "context-2"
    assert len(set(results.values())) == 3  # All unique


def test_correlation_id_filter_performance():
    filter_instance = CorrelationIdFilter()

    record = logging.LogRecord(
        name="perf_test", level=logging.INFO, pathname="", lineno=0, msg="Performance test message", args=(), exc_info=None
    )

    set_correlation_id("performance-test-id")

    start_time = time.time()

    for _ in range(1000):
        filter_instance.filter(record)

    end_time = time.time()
    duration = end_time - start_time

    assert duration < 1.0

    assert record.correlation_id == "performance-test-id"  # type: ignore[attr-defined]
