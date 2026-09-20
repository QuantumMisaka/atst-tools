"""Schema-level tests for the optional ``runtime`` YAML section."""

from __future__ import annotations

from copy import deepcopy
import re

import pytest

from atst_tools.utils.config import ConfigLoader

UUID_A = "GPU-12345678-1234-1234-1234-123456789abc"

BASE_CONFIG = {
    "calculation": {"type": "relax", "init_structure": "init.stru"},
    "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
}


def _normalize(runtime):
    config = deepcopy(BASE_CONFIG)
    if runtime is not None:
        config["runtime"] = runtime
    return ConfigLoader.normalize(config)


@pytest.mark.parametrize(
    "runtime",
    [
        {"devices": [0]},
        {"devices": [0, UUID_A]},
        {"devices": 1},
        {"binding": "round_robin"},
        {"threads": 4},
        {"telemetry": True},
        {"telemetry": {"enabled": True, "interval_s": 2.5}},
    ],
)
def test_runtime_section_accepts_governed_values(runtime):
    normalized = _normalize(runtime)
    assert "runtime" in normalized


@pytest.mark.parametrize(
    "runtime,needle",
    [
        ({"devices": []}, "must not be empty"),
        ({"devices": [1, 1]}, "must not contain duplicate entries"),
        ({"devices": True}, "not a valid 0-based device index"),
        ({"devices": -1}, "not a valid 0-based device index"),
        ({"devices": "MIG-aa11bb22-cc33-4455-6677-8899aabbccdd"}, "MIG"),
        ({"threads": 0}, "runtime.threads must be a positive integer"),
        ({"threads": True}, "runtime.threads must be a positive integer"),
        ({"threads": "4"}, "runtime.threads must be a positive integer"),
        ({"binding": "pinned"}, "is not one of: inherit, round_robin"),
        ({"telemetry": "yes"}, "telemetry"),
        ({"bogus": 1}, "Extra inputs are not permitted"),
    ],
)
def test_runtime_section_rejects_invalid_values(runtime, needle):
    with pytest.raises(ValueError) as caught:
        _normalize(runtime)
    assert re.search(re.escape(needle), str(caught.value))


def test_runtime_section_must_be_a_mapping():
    with pytest.raises(ValueError):
        _normalize(["devices"])


def test_runtime_section_is_absent_by_default_and_keeps_defaults_when_empty():
    assert "runtime" not in _normalize(None)
    assert _normalize({})["runtime"]["binding"] == "inherit"
