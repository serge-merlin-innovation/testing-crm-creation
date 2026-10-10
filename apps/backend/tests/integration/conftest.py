import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "performance: marks tests as performance tests")
    config.addinivalue_line("markers", "stress: marks tests as stress tests")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        if "performance" in str(item.fspath) or "performance" in item.name:
            item.add_marker(pytest.mark.performance)

        if "stress" in item.name.lower():
            item.add_marker(pytest.mark.stress)
            item.add_marker(pytest.mark.slow)
