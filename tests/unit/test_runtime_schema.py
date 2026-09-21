"""Schema-level tests for the optional ``runtime`` YAML section."""

from __future__ import annotations

import re
from copy import deepcopy

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
        {"threads": "auto"},
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


def test_runtime_section_uses_the_frozen_interface_messages():
    """The interface freeze fixes these user-visible validation messages."""
    cases = [
        (["devices"], "runtime must be a mapping"),
        (
            {"devices": {}},
            "runtime.devices must be a device index, GPU UUID or a list of them",
        ),
        (
            {"devices": True},
            "runtime.devices entry 'True' is not a valid 0-based device index or full GPU UUID",
        ),
        (
            {"devices": [1.5]},
            "runtime.devices entry '1.5' is not a valid 0-based device index or full GPU UUID",
        ),
        (
            {"devices": []},
            "runtime.devices must not be empty; omit the field to inherit all visible devices",
        ),
        (
            {"devices": [0, 0]},
            "runtime.devices must not contain duplicate entries (0)",
        ),
        (
            {"devices": ["MIG-aa11bb22-cc33-4455-6677-8899aabbccdd"]},
            "runtime.devices does not support MIG device selection "
            "('MIG-aa11bb22-cc33-4455-6677-8899aabbccdd'); "
            "pass a full physical GPU UUID instead",
        ),
        ({"threads": 0}, "runtime.threads must be a positive integer"),
        (
            {"binding": "pinned"},
            "runtime.binding 'pinned' is not one of: inherit, round_robin",
        ),
        (
            {"telemetry": "yes"},
            "runtime.telemetry must be a boolean or a mapping with 'enabled'",
        ),
        (
            {"telemetry": {"enabled": "yes"}},
            "runtime.telemetry.enabled must be a boolean",
        ),
        (
            {"telemetry": {"interval_s": 0}},
            "runtime.telemetry.interval_s must be a positive number",
        ),
        (
            {"telemetry": {"interval_s": "fast"}},
            "runtime.telemetry.interval_s must be a positive number",
        ),
    ]
    for runtime, expected in cases:
        with pytest.raises(ValueError) as caught:
            _normalize(runtime)
        text = str(caught.value)
        assert expected in text, (runtime, expected, text)
        # The telemetry union must not leak the boolean member's pydantic error.
        assert "runtime.telemetry.bool" not in text


def test_runtime_section_is_absent_by_default_and_keeps_defaults_when_empty():
    assert "runtime" not in _normalize(None)
    assert _normalize({})["runtime"]["binding"] == "inherit"
