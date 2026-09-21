"""Joint acceptance for the constant-potential and runtime sections (SPEC 7A).

The constant-potential work and the GPU runtime work only add optional fields
to the same schema. This module proves that a configuration enabling both still
validates strictly, and that either side's validation errors still fail closed
while the other side is present.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from atst_tools.utils.config import ConfigLoader

BASE = {
    "calculation": {"type": "constant_potential", "init_structure": "input.xyz"},
    "calculator": {
        "name": "abacus",
        "abacus": {"parameters": {"nelec": 10}},
        "constant_potential": {
            "energy_boundary": "reference_fcp",
            "potential_v": 1.0,
            "work_ref": 4.6,
            "work_ref_source": "fixture",
            "reference_electrons": 10,
        },
    },
}


def _with_runtime(runtime):
    config = deepcopy(BASE)
    config["runtime"] = runtime
    return config


def test_constant_potential_and_runtime_validate_together():
    """Both feature sets keep working when enabled in one configuration."""
    normalized = ConfigLoader.normalize(
        _with_runtime({"devices": [0], "threads": 4, "telemetry": {"enabled": True}})
    )
    assert normalized["calculation"]["type"] == "constant_potential"
    assert normalized["calculator"]["constant_potential"]["reference_electrons"] == 10.0
    assert normalized["runtime"] == {
        "devices": [0],
        "binding": "inherit",
        "threads": 4,
        "telemetry": {"enabled": True, "interval_s": 1.0},
    }


def test_compensated_gate_candidate_accepts_runtime_fields():
    """The gate-boundary candidate (the production path) also combines cleanly."""
    config = _with_runtime({"devices": [0], "telemetry": True})
    config["calculator"]["constant_potential"] = {
        "energy_boundary": "compensated_gate",
        "reference_electrode": "custom",
        "target_mu_ev": -5.0,
        "reference_electrons": 8.0,
    }
    normalized = ConfigLoader.normalize(config)
    boundary = normalized["calculator"]["constant_potential"]["energy_boundary"]
    assert boundary == "compensated_gate"
    assert normalized["runtime"] == {
        "devices": [0],
        "binding": "inherit",
        "telemetry": True,
    }


def test_runtime_errors_still_fail_closed_next_to_constant_potential():
    with pytest.raises(ValueError) as caught:
        ConfigLoader.normalize(_with_runtime({"devices": []}))
    assert "runtime.devices must not be empty" in str(caught.value)

    with pytest.raises(ValueError) as caught:
        ConfigLoader.normalize(_with_runtime({"telemetry": {"interval_s": 0}}))
    assert "runtime.telemetry.interval_s must be a positive number" in str(caught.value)

    with pytest.raises(ValueError) as caught:
        ConfigLoader.normalize(_with_runtime({"nope": 1}))
    assert "Extra inputs are not permitted" in str(caught.value)


def test_constant_potential_errors_still_fail_closed_next_to_runtime():
    config = deepcopy(BASE)
    config["runtime"] = {"devices": [0]}
    del config["calculator"]["constant_potential"]["work_ref_source"]
    with pytest.raises(ValueError, match="work_ref_source"):
        ConfigLoader.validate(config)

    unknown = deepcopy(BASE)
    unknown["runtime"] = {"devices": [0]}
    unknown["calculator"]["constant_potential"]["unknown_field"] = 1
    with pytest.raises(ValueError, match="unknown"):
        ConfigLoader.validate(unknown)
