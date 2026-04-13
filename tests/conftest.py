"""Root test config: integration CLI flags must live here so ``pytest tests/`` sees them."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("integration", "integration sample corpus")
    group.addoption(
        "--integration-sample-limit",
        action="store",
        default=None,
        type=int,
        metavar="N",
        help="Use N random picks from the glob pool. "
        "When N <= pool size this is a random subset; when N > pool size picks repeat. "
        "Default: all. Env: INTEGRATION_SAMPLE_LIMIT",
    )
    group.addoption(
        "--integration-repeat-to",
        action="store",
        default=None,
        type=int,
        metavar="N",
        help="Cycle through resolved samples until N paths (e.g. stress with 100). "
        "Env: INTEGRATION_REPEAT_TO",
    )
    group.addoption(
        "--integration-sample-source",
        action="store",
        default=None,
        metavar="SOURCE",
        help="Integration sample source: 'samples' (tests/samples) or "
        "'downloads' (.data/downloads). Env: INTEGRATION_SAMPLE_SOURCE",
    )
