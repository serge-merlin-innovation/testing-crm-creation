"""Writes the published OpenAPI document to docs/api/openapi.json.

Run after any API change: `uv run python -m scripts.export_openapi`. CI fails while the committed
file differs from what the app serves.
"""

import json
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from src.infrastructure.logging import get_logger  # noqa: E402
from src.interfaces.main import app  # noqa: E402

logger = get_logger()

SPEC_PATH = backend_dir.parent.parent / "docs" / "api" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(render())
    logger.info(f"Wrote {SPEC_PATH}")


if __name__ == "__main__":
    main()
