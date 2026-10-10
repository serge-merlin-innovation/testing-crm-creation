"""Appends one line per failed test to the repo's check-failures.log (see scripts/check-failures).

It lives here, at the pytest rootdir, so it runs however pytest is started: pnpm, ``uv run
pytest <file>``, an IDE or an agent.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_RECORDER = Path(__file__).resolve().parents[2] / "scripts" / "check-failures" / "record.mjs"
_failures: list[dict[str, str]] = []
_interrupted = False


def _kind(nodeid: str) -> str:
    return "test:integration" if nodeid.startswith("tests/integration") else "test:unit"


def _message(report: pytest.CollectReport | pytest.TestReport) -> str:
    crash = getattr(report.longrepr, "reprcrash", None)
    if crash is not None and crash.message:
        return str(crash.message).splitlines()[0]
    text = report.longreprtext or ""
    lines = [line for line in text.splitlines() if line.strip()]
    errors = [line[2:] for line in lines if line.startswith("E ")]
    return (errors or lines or ["failed"])[0].strip()


def _add(report: pytest.CollectReport | pytest.TestReport, prefix: str = "") -> None:
    nodeid = report.nodeid or "<collection>"
    _failures.append({"kind": _kind(nodeid), "app": "backend", "location": nodeid, "message": prefix + _message(report)})


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed:
        _add(report, "collection error: ")


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.failed:
        _add(report, "" if report.when == "call" else f"error in {report.when}: ")


def pytest_keyboard_interrupt(excinfo: pytest.ExceptionInfo[BaseException]) -> None:
    # pytest raises collection errors as Session.Interrupted, a KeyboardInterrupt subclass.
    global _interrupted
    _interrupted = not isinstance(excinfo.value, pytest.Session.Interrupted)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # xdist workers report to the controller, which is the only process that writes.
    if hasattr(session.config, "workerinput") or _interrupted:
        return
    if not _failures or os.environ.get("CI"):
        return
    node = shutil.which("node")
    if node is None or not _RECORDER.exists():
        return
    try:
        subprocess.run([node, str(_RECORDER)], input=json.dumps(_failures), text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
