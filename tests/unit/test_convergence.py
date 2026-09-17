"""Tests for shared convergence stage records and unconverged advisories."""

from __future__ import annotations

import io
import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from atst_tools.utils.convergence import (
    EXECUTION_STATUSES,
    StageRecord,
    as_finite_float,
    as_step_count,
    emit_unconverged_advisory,
)
from helpers import FakeReducingWorld, FakeWorld


ADVISORY_TAIL = "Execution completion does not imply optimizer convergence.\n"


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        (True, True),
        (False, False),
        (np.bool_(True), True),
        (np.bool_(False), False),
        (None, None),
        (0, None),
        (1, None),
        ("false", None),
        (np.float64(0.0), None),
        (object(), None),
    ],
)
def test_converged_signal_is_a_strict_tri_state(signal, expected):
    """Only bool/numpy.bool_ are trusted; everything else becomes unknown."""
    record = StageRecord(name="final_neb", converged=signal)

    assert record.converged is expected
    assert isinstance(record.converged, (bool, type(None)))


def test_defaults_and_status_enum():
    """The documented defaults are applied and the status enum is exported."""
    record = StageRecord(name="ci_neb")

    assert record.status == "complete"
    assert record.fmax_unit == "eV/Angstrom"
    assert record.converged is None
    assert EXECUTION_STATUSES == ("complete", "skipped", "failed")
    for status in EXECUTION_STATUSES:
        assert StageRecord(name="ci_neb", status=status).status == status


@pytest.mark.parametrize("status", ["running", "COMPLETE", "", None, 3])
def test_unknown_status_is_rejected(status):
    """A status outside EXECUTION_STATUSES is a contract violation."""
    with pytest.raises(ValueError, match="status"):
        StageRecord(name="ci_neb", status=status)


@pytest.mark.parametrize("name", ["", "   ", None, 7])
def test_empty_name_is_rejected(name):
    """Every stage record needs a non-empty string identity."""
    with pytest.raises(ValueError, match="name"):
        StageRecord(name=name)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_fmax_is_rejected(value):
    """A non-finite threshold would make the advisory untruthful."""
    with pytest.raises(ValueError, match="finite"):
        StageRecord(name="ci_neb", fmax=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_measured_is_rejected(value):
    """Measured quantities are finite facts only."""
    with pytest.raises(ValueError, match="finite"):
        StageRecord(name="ci_neb", measured={"fmax": value})


@pytest.mark.parametrize("field_name", ["iteration", "steps", "actual_steps"])
def test_negative_counts_are_rejected(field_name):
    """Step and iteration counts are non-negative."""
    with pytest.raises(ValueError, match="non-negative"):
        StageRecord(name="ci_neb", **{field_name: -1})


@pytest.mark.parametrize("field_name", ["iteration", "steps", "actual_steps"])
@pytest.mark.parametrize("value", [True, 1.5, "3"])
def test_non_integer_counts_are_rejected(field_name, value):
    """``bool`` and non-integral values are not step counts."""
    with pytest.raises(TypeError, match="non-negative integer"):
        StageRecord(name="ci_neb", **{field_name: value})


def test_measured_must_be_a_string_keyed_mapping():
    """Measured values are stored as a JSON-safe string-keyed mapping."""
    with pytest.raises(TypeError, match="measured"):
        StageRecord(name="ci_neb", measured=[("fmax", 0.05)])
    with pytest.raises(TypeError, match="keys"):
        StageRecord(name="ci_neb", measured={1: 0.05})
    with pytest.raises(TypeError, match="finite number"):
        StageRecord(name="ci_neb", measured={"fmax": "0.05"})


def test_records_are_frozen_and_copy_measured():
    """Records are immutable and never share the caller's measured mapping."""
    source = {"fmax": np.float64(0.05)}
    record = StageRecord(name="ci_neb", measured=source)

    source["fmax"] = 99.0
    source["extra"] = 1.0
    assert record.measured == {"fmax": 0.05}
    with pytest.raises(FrozenInstanceError):
        record.measured = {}


def test_to_manifest_minimal_keys_and_json_null():
    """Only name/status/converged are always present; unknown converges to null."""
    manifest = StageRecord(name="ci_neb").to_manifest()

    # A unit alone would be misleading, so it is emitted only with a threshold.
    assert list(manifest) == ["name", "status", "converged"]
    assert manifest["converged"] is None
    round_tripped = json.loads(json.dumps(manifest))
    assert round_tripped == manifest
    assert round_tripped["converged"] is None

    with_threshold = StageRecord(name="ci_neb", fmax=0.05).to_manifest()
    assert list(with_threshold) == ["name", "status", "converged", "fmax", "fmax_unit"]
    assert with_threshold["fmax_unit"] == "eV/Angstrom"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, None),
        (0, 0),
        (7, 7),
        (np.int64(5), 5),
        (3.0, 3),
        (np.float64(4.0), 4),
        (True, None),
        (-1, None),
        (1.5, None),
        (float("nan"), None),
        (float("inf"), None),
        ("5", None),
        (object(), None),
    ),
)
def test_as_step_count_degrades_unusable_values(value, expected):
    """Foreign optimizer step counts degrade to None instead of raising."""
    assert as_step_count(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, None),
        (0.05, 0.05),
        (0, 0.0),
        (np.float64(0.1), 0.1),
        (True, None),
        (float("nan"), None),
        (float("inf"), None),
        ("0.05", None),
        (object(), None),
    ),
)
def test_as_finite_float_degrades_unusable_values(value, expected):
    """Caller-supplied numeric facts degrade to None instead of raising."""
    assert as_finite_float(value) == expected


def test_to_manifest_includes_present_optionals_and_round_trips():
    """Every populated optional key is emitted and survives json.dumps."""
    record = StageRecord(
        name="ci_neb",
        status="complete",
        converged=np.bool_(False),
        role="final",
        criterion="fmax_and_saddle_region",
        direction="forward",
        iteration=np.int64(2),
        fmax=np.float64(0.05),
        fmax_unit="eV/Angstrom",
        steps=np.int32(100),
        actual_steps=42,
        measured={"fmax": np.float32(0.125)},
        measured_unit="eV/Angstrom",
    )

    manifest = record.to_manifest()

    assert list(manifest) == [
        "name",
        "status",
        "converged",
        "role",
        "criterion",
        "direction",
        "iteration",
        "fmax",
        "fmax_unit",
        "steps",
        "actual_steps",
        "measured",
        "measured_unit",
    ]
    assert manifest["converged"] is False
    assert manifest["role"] == "final"
    assert manifest["criterion"] == "fmax_and_saddle_region"
    assert manifest["direction"] == "forward"
    assert manifest["iteration"] == 2
    assert manifest["fmax"] == 0.05
    assert manifest["fmax_unit"] == "eV/Angstrom"
    assert manifest["steps"] == 100
    assert manifest["actual_steps"] == 42
    assert manifest["measured"] == {"fmax": 0.125}
    assert manifest["measured_unit"] == "eV/Angstrom"
    assert isinstance(manifest["fmax"], float)
    assert isinstance(manifest["iteration"], int)
    assert isinstance(manifest["steps"], int)
    assert isinstance(manifest["measured"], dict)
    assert json.loads(json.dumps(manifest)) == manifest


def test_to_manifest_omits_none_valued_optionals():
    """Optional keys are omitted, never written as null, when unset."""
    record = StageRecord(
        name="ordinary_neb_warmup",
        status="skipped",
        converged=True,
        fmax_unit=None,
        steps=20,
    )

    manifest = record.to_manifest()

    assert manifest == {
        "name": "ordinary_neb_warmup",
        "status": "skipped",
        "converged": True,
        "steps": 20,
    }
    assert "fmax" not in manifest
    assert "role" not in manifest
    assert "measured" not in manifest
    assert json.loads(json.dumps(manifest)) == manifest


def test_advisory_message_tokens_for_unconverged_stage(capsys):
    """An explicit False prints exactly one advisory with the canonical rendering.

    This is the single deliberate full-rendering test; the other advisory tests
    lock only stable semantic tokens so wording can evolve without breaking them.
    """
    record = StageRecord(
        name="ci_neb",
        converged=False,
        fmax=0.05,
        actual_steps=42,
        steps=100,
    )

    emitted = emit_unconverged_advisory(record, workflow="neb")

    captured = capsys.readouterr()
    assert emitted is True
    assert captured.out == (
        "Warning: NEB finished without satisfying its optimizer convergence criteria\n"
        "(workflow=neb, stage=ci_neb, threshold_fmax=0.05 eV/Angstrom, "
        "nsteps=42, max_steps=100).\n" + ADVISORY_TAIL
    )
    assert captured.out.count("Warning:") == 1
    assert captured.err == ""


def test_advisory_appends_direction_and_iteration_tokens(capsys):
    """IRC direction and AutoNEB iteration tokens are appended when present."""
    record = StageRecord(
        name="irc_backward",
        converged=False,
        direction="backward",
        iteration=3,
        fmax=0.02,
    )

    assert emit_unconverged_advisory(record, workflow="irc") is True

    captured = capsys.readouterr()
    for token in (
        "workflow=irc",
        "stage=irc_backward",
        "threshold_fmax=0.02 eV/Angstrom",
        "direction=backward",
        "iteration=3",
    ):
        assert token in captured.out
    assert captured.out.endswith(ADVISORY_TAIL)


def test_advisory_omits_absent_optional_tokens(capsys):
    """Unset thresholds and step counts are omitted, not printed as None."""
    record = StageRecord(name="endpoint_relax", converged=False, fmax_unit=None)

    assert emit_unconverged_advisory(record, workflow="autoneb") is True

    captured = capsys.readouterr()
    assert "workflow=autoneb" in captured.out
    assert "stage=endpoint_relax" in captured.out
    assert captured.out.endswith(ADVISORY_TAIL)
    assert "None" not in captured.out


@pytest.mark.parametrize("signal", [True, np.bool_(True), None])
def test_advisory_is_silent_when_not_explicitly_false(capsys, signal):
    """A converged or unknown signal never produces an advisory."""
    record = StageRecord(name="ci_neb", converged=signal, fmax=0.05, steps=100)

    assert emit_unconverged_advisory(record, workflow="neb") is False

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_advisory_uses_the_supplied_stream():
    """``stream`` overrides sys.stdout for the single print call."""
    stream = io.StringIO()
    record = StageRecord(name="ci_neb", converged=False, fmax=0.05, steps=10)

    assert emit_unconverged_advisory(record, workflow="neb", stream=stream) is True

    assert stream.getvalue().startswith("Warning: NEB finished without satisfying")
    assert stream.getvalue().endswith(ADVISORY_TAIL)


def test_advisory_prints_directly_on_a_single_rank_world(capsys):
    """A single-rank world prints locally without a root section."""
    record = StageRecord(name="ci_neb", converged=False, fmax=0.05, steps=10)
    world = FakeReducingWorld(size=1, rank=0)

    assert emit_unconverged_advisory(record, workflow="neb", world=world) is True

    captured = capsys.readouterr()
    assert captured.out.startswith("Warning: NEB finished")
    assert world.sums == 0


def test_advisory_is_root_only_on_a_multi_rank_world(capsys):
    """On a size-2 world only rank 0 prints; rank 1 leaves a reduction record."""
    record = StageRecord(
        name="ci_neb",
        converged=False,
        fmax=0.05,
        actual_steps=42,
        steps=100,
    )
    root = FakeWorld(size=2, rank=0)
    follower = FakeWorld(size=2, rank=1)

    root_emitted = emit_unconverged_advisory(record, workflow="neb", world=root)
    root_output = capsys.readouterr()
    follower_emitted = emit_unconverged_advisory(record, workflow="neb", world=follower)
    follower_output = capsys.readouterr()

    for token in (
        "workflow=neb",
        "stage=ci_neb",
        "threshold_fmax=0.05 eV/Angstrom",
        "nsteps=42",
        "max_steps=100",
    ):
        assert token in root_output.out
    assert root_output.out.endswith(ADVISORY_TAIL)
    assert follower_output.out == ""
    assert follower_output.err == ""
    # The return value is rank-independent so callers never branch on rank state.
    assert root_emitted is follower_emitted is True


def test_advisory_is_silent_on_every_rank_when_converged(capsys):
    """No rank prints, and no reduction is required, when converged is True."""
    record = StageRecord(name="ci_neb", converged=True, fmax=0.05, steps=100)
    root = FakeReducingWorld(size=2, rank=0)

    assert emit_unconverged_advisory(record, workflow="neb", world=root) is False

    captured = capsys.readouterr()
    assert captured.out == ""
    assert root.sums == 0


@pytest.mark.parametrize("workflow", ["", "   ", None, 3])
def test_advisory_requires_a_workflow_label(workflow):
    """The workflow label is mandatory message context."""
    record = StageRecord(name="ci_neb", converged=False)

    with pytest.raises(ValueError, match="workflow"):
        emit_unconverged_advisory(record, workflow=workflow)
