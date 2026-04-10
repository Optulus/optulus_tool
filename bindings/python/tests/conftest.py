from __future__ import annotations

import pytest

from optulus_sdk.telemetry import reset_telemetry_state


@pytest.fixture(autouse=True)
def _reset_optulus_telemetry_after_test() -> None:
    yield
    reset_telemetry_state()
