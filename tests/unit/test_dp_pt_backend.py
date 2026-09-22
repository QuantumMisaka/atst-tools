"""Behaviour evidence for the DeepMD-kit PT artifact contract.

The claims pinned here are:

* the artifact itself decides the DP model kind (raw PT checkpoint, frozen PT
  archive, TF graph or something else) and a missing or unreadable artifact is
  reported with a clear error,
* a multi-task PT model without a usable ``head`` fails closed at construction
  time with an actionable ATST-Tools error instead of leaking the bare
  DeepMD-kit ``AssertionError``,
* an operator mismatch of a version-locked frozen archive is translated at
  evaluation time into an actionable error, and
* :func:`atst_tools.calculators.dp.dp_model_identity` reports the facts the
  evidence layer needs without evaluating the model.

Every claim except the ``skip``-guarded real-model cases is driven by a
stand-in DeepMD-kit module, so the assertions stay about ATST behaviour.  The
real-model cases use the multi-task PT artifact given by
``ATST_DP_PT_TEST_MODEL``, ``temp_repos/dp_model/DPA-3.1-3M.pt`` in this
checkout or its known maintainer location, and skip when none of them exists.
"""

from __future__ import annotations

import math
import os
import sys
import types
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator

from atst_tools.calculators import dp as dp_adapter
from atst_tools.calculators import factory as calculator_factory

REPO_ROOT = Path(__file__).resolve().parents[2]

# Verbatim DeepMD-kit 3.1.2 messages, reproduced on the local multi-task model.
MULTITASK_WITHOUT_HEAD_MESSAGE = (
    "Head must be set for multitask model! Available heads are: ['Domains_Alloy', "
    "'Domains_Anode', 'Omat24', 'SPICE2'], use `dp --pt show your_model.pt "
    "model-branch` to show detail information."
)
MULTITASK_UNKNOWN_HEAD_MESSAGE = (
    "No head or alias named Nope in model! Available heads are: ['Domains_Alloy', "
    "'Domains_Anode', 'Omat24', 'SPICE2'],use `dp --pt show your_model.pt "
    "model-branch` to show detail information."
)
# A multi-task model whose head list cannot be read out of the message text.
MULTITASK_HEADLESS_MESSAGE = "Head must be set for multitask model!"
# Verbatim frozen-archive operator mismatch of a foreign deepmd-kit build.
FROZEN_ARCHIVE_OPERATOR_MESSAGE = (
    "Unknown keyword argument 'use_tebd_bias' for operator 'forward_common_lower'"
)
UNRELATED_RUNTIME_MESSAGE = "CUDA out of memory. Tried to allocate 2.00 GiB"

LOCAL_MULTITASK_MODEL = Path("temp_repos/dp_model/DPA-3.1-3M.pt")
MAINTAINER_MULTITASK_MODEL = Path(
    "/home/james/work/sidereus/app-tools/toolbox/ABACUS/deps/atst-tools"
).joinpath(LOCAL_MULTITASK_MODEL)
MULTITASK_HEAD = "Omat24"


def _multitask_model_path() -> Path | None:
    """Return the local multi-task PT artifact, or None when it is absent."""
    candidates = [
        os.environ.get("ATST_DP_PT_TEST_MODEL"),
        REPO_ROOT / LOCAL_MULTITASK_MODEL,
        MAINTAINER_MULTITASK_MODEL,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


@pytest.fixture(scope="module")
def multitask_model() -> Iterator[Path]:
    """Yield the real multi-task PT artifact or skip with the search reason."""
    path = _multitask_model_path()
    if path is None:
        pytest.skip(
            "no multi-task PT artifact: set ATST_DP_PT_TEST_MODEL or place "
            f"{LOCAL_MULTITASK_MODEL} under {REPO_ROOT} (temp_repos/ is not in git)"
        )
    pytest.importorskip("deepmd.calculator")
    yield path


@pytest.fixture(scope="module")
def real_identity(multitask_model: Path) -> dict[str, Any]:
    """Return the identity of the real multi-task artifact for its branch."""
    return dp_adapter.dp_model_identity(multitask_model, head=MULTITASK_HEAD)


def _install_deepmd(
    monkeypatch, *, calculator_class: type, infer_class: type | None = None
):
    """Install a stand-in DeepMD-kit module tree for the factory and the adapter."""
    deepmd_module = types.ModuleType("deepmd")
    deepmd_module.__version__ = "0.0.0-standin"
    calculator_module = types.ModuleType("deepmd.calculator")
    calculator_module.DP = calculator_class
    monkeypatch.setitem(sys.modules, "deepmd", deepmd_module)
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator_module)
    if infer_class is not None:
        infer_module = types.ModuleType("deepmd.infer")
        infer_module.DeepPot = infer_class
        monkeypatch.setitem(sys.modules, "deepmd.infer", infer_module)
    dp_adapter.DeepPotentialFactory._instances.clear()
    return calculator_class


def _config(model: str, **parameters: Any) -> dict[str, Any]:
    """Return a minimal DP calculator configuration."""
    return {"calculator": {"name": "dp", "dp": {"model": model, **parameters}}}


# --------------------------------------------------------------------------
# artifact kind
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("model.pt", dp_adapter.DP_KIND_PT_CHECKPOINT),
        ("model.PT", dp_adapter.DP_KIND_PT_CHECKPOINT),
        ("dpa3_frozen.pth", dp_adapter.DP_KIND_FROZEN_ARCHIVE),
        ("frozen_model.pb", dp_adapter.DP_KIND_TF_GRAPH),
        ("graph.pbtxt", dp_adapter.DP_KIND_TF_GRAPH),
        ("frozen_model", dp_adapter.DP_KIND_UNKNOWN),
        ("archive.pth.bak", dp_adapter.DP_KIND_UNKNOWN),
    ],
)
def test_model_kind_follows_the_artifact_suffix(name, expected):
    """The artifact decides the kind: PT checkpoint, frozen archive or TF graph."""
    assert dp_adapter.dp_model_kind(name) == expected


def test_model_kind_of_an_unknown_artifact_is_unknown():
    """A model without a known suffix is reported as unknown, not guessed."""
    assert dp_adapter.dp_model_kind(None) == dp_adapter.DP_KIND_UNKNOWN
    assert dp_adapter.dp_model_kind("archive.tar.gz") == dp_adapter.DP_KIND_UNKNOWN


def test_missing_artifact_is_rejected_with_a_clear_error(tmp_path):
    """A missing artifact fails closed before any DeepMD-kit work happens."""
    missing = tmp_path / "absent.pt"
    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        dp_adapter.dp_model_identity(missing)
    assert "not found" in str(error.value)
    assert str(missing) in str(error.value)


def test_empty_artifact_is_rejected_with_a_clear_error(tmp_path):
    """A zero-byte artifact is not a model and is rejected with its path."""
    empty = tmp_path / "empty.pth"
    empty.write_bytes(b"")
    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        dp_adapter.dp_model_identity(empty)
    assert "empty" in str(error.value)
    assert str(empty) in str(error.value)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unreadable_artifact_is_rejected_with_a_clear_error(tmp_path):
    """An artifact the process cannot read is rejected with its path."""
    locked = tmp_path / "locked.pt"
    locked.write_bytes(b"not a model")
    locked.chmod(0o000)
    try:
        with pytest.raises(dp_adapter.DeepPotentialError) as error:
            dp_adapter.dp_model_identity(locked)
    finally:
        locked.chmod(0o644)
    assert "not readable" in str(error.value)
    assert str(locked) in str(error.value)


# --------------------------------------------------------------------------
# multi-task head handling at construction time
# --------------------------------------------------------------------------


def test_available_heads_are_read_from_the_deepmd_error_text():
    """The available branch list is extracted from the DeepMD-kit message."""
    heads = dp_adapter.dp_available_heads_from_message(MULTITASK_WITHOUT_HEAD_MESSAGE)
    assert heads == ["Domains_Alloy", "Domains_Anode", "Omat24", "SPICE2"]
    assert dp_adapter.dp_available_heads_from_message(
        MULTITASK_UNKNOWN_HEAD_MESSAGE
    ) == ["Domains_Alloy", "Domains_Anode", "Omat24", "SPICE2"]


@pytest.mark.parametrize(
    "message",
    [
        MULTITASK_HEADLESS_MESSAGE,
        "Available heads are: not-a-list",
        "",
    ],
)
def test_available_heads_are_none_when_the_text_has_no_list(message):
    """Unparseable messages report no heads instead of guessing them."""
    assert dp_adapter.dp_available_heads_from_message(message) is None


def test_multitask_model_without_head_raises_an_actionable_error(monkeypatch):
    """A missing branch fails closed at construction with the branch list."""

    class _HeadRequiringDP:
        def __init__(self, **kwargs):
            raise AssertionError(MULTITASK_WITHOUT_HEAD_MESSAGE)

    _install_deepmd(monkeypatch, calculator_class=_HeadRequiringDP)

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        calculator_factory.CalculatorFactory.get_calculator("dp", _config("multi.pt"))

    message = str(error.value)
    assert "multi.pt" in message
    assert "head" in message
    assert "Omat24" in message
    assert "dp --pt show" in message
    assert not isinstance(error.value, AssertionError)


def test_multitask_model_with_unknown_head_raises_an_actionable_error(monkeypatch):
    """A wrong branch name fails closed and lists the available branches."""

    class _HeadCheckingDP:
        def __init__(self, **kwargs):
            raise AssertionError(MULTITASK_UNKNOWN_HEAD_MESSAGE)

    _install_deepmd(monkeypatch, calculator_class=_HeadCheckingDP)

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        calculator_factory.CalculatorFactory.get_calculator(
            "dp", _config("multi.pt", head="Nope")
        )

    message = str(error.value)
    assert "Nope" in message
    assert "Omat24" in message
    assert "dp --pt show" in message


def test_head_error_without_a_branch_list_points_at_the_dp_command(monkeypatch):
    """Without an extractable list the error still names the discovery command."""

    class _OpaqueHeadDP:
        def __init__(self, **kwargs):
            raise AssertionError(MULTITASK_HEADLESS_MESSAGE)

    _install_deepmd(monkeypatch, calculator_class=_OpaqueHeadDP)

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        calculator_factory.CalculatorFactory.get_calculator("dp", _config("multi.pt"))

    assert "dp --pt show" in str(error.value)
    assert "multi.pt" in str(error.value)


def test_valid_head_is_passed_through_unchanged(monkeypatch):
    """A usable branch keeps reaching the backend exactly as configured."""

    class _RecordingDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    _install_deepmd(monkeypatch, calculator_class=_RecordingDP)

    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config("model.pt", head=MULTITASK_HEAD)
    )

    assert calc.kwargs["head"] == MULTITASK_HEAD
    assert calc.kwargs["model"] == "model.pt"


def test_the_artifact_kind_is_recorded_on_the_calculator(monkeypatch):
    """The built calculator carries the artifact kind and backend it came from."""

    class _RecordingDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    _install_deepmd(monkeypatch, calculator_class=_RecordingDP)

    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config("frozen.pth", head=MULTITASK_HEAD)
    )

    assert calc.atst_model_kind == dp_adapter.DP_KIND_FROZEN_ARCHIVE
    assert calc.atst_model_backend == "pt"
    assert calc.atst_model_head == MULTITASK_HEAD
    assert calc.atst_model.endswith("frozen.pth")


# --------------------------------------------------------------------------
# version-locked PT artifacts at evaluation time
# --------------------------------------------------------------------------


class _OperatorLockedDP(Calculator):
    """Stand-in backend whose first evaluation exposes a foreign build."""

    implemented_properties = ("energy", "forces")

    def __init__(self, model, **kwargs):
        super().__init__()
        self.model = model
        self.kwargs = kwargs
        self.calculations = 0

    def calculate(self, atoms=None, properties=("energy",), system_changes=()):
        self.calculations += 1
        raise RuntimeError(FROZEN_ARCHIVE_OPERATOR_MESSAGE)


def _evaluate(calculator) -> None:
    """Drive one evaluation through the ASE calculator protocol."""
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
    atoms.calc = calculator
    atoms.get_potential_energy()


def test_frozen_archive_operator_mismatch_is_translated_at_evaluation(monkeypatch):
    """A version-locked frozen archive reports the lock and the escape routes."""
    _install_deepmd(monkeypatch, calculator_class=_OperatorLockedDP)
    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config("dpa3_frozen.pth", head=MULTITASK_HEAD)
    )

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        _evaluate(calc)

    message = str(error.value)
    assert calc.calculations == 1
    assert "dpa3_frozen.pth" in message
    assert FROZEN_ARCHIVE_OPERATOR_MESSAGE in message
    assert "frozen" in message
    assert "*.pt" in message
    assert "dp --pt freeze" in message


def test_checkpoint_operator_mismatch_names_the_matching_build(monkeypatch):
    """A raw checkpoint mismatch asks for a build matching the checkpoint."""
    _install_deepmd(monkeypatch, calculator_class=_OperatorLockedDP)
    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config("model.pt", head=MULTITASK_HEAD)
    )

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        _evaluate(calc)

    message = str(error.value)
    assert "model.pt" in message
    assert FROZEN_ARCHIVE_OPERATOR_MESSAGE in message
    assert "deepmd-kit build" in message


def test_unrelated_evaluation_errors_are_not_reinterpreted(monkeypatch):
    """Backend failures ATST-Tools cannot explain stay untouched."""

    class _OutOfMemoryDP(Calculator):
        implemented_properties = ("energy",)

        def __init__(self, model, **kwargs):
            super().__init__()

        def calculate(self, atoms=None, properties=("energy",), system_changes=()):
            raise RuntimeError(UNRELATED_RUNTIME_MESSAGE)

    _install_deepmd(monkeypatch, calculator_class=_OutOfMemoryDP)
    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config("dpa3_frozen.pth")
    )

    with pytest.raises(RuntimeError) as error:
        _evaluate(calc)

    assert not isinstance(error.value, dp_adapter.DeepPotentialError)
    assert str(error.value) == UNRELATED_RUNTIME_MESSAGE


# --------------------------------------------------------------------------
# identity facts without evaluation
# --------------------------------------------------------------------------


class _RecordingDeepPot:
    """Stand-in PT ``DeepPot`` recording every public fact read from it."""

    calls: list[str] = []

    def __init__(self, model, head=None, **kwargs):
        self.model = model
        self.head = head
        self.calls.append(f"__init__({head})")
        self.deep_eval = types.SimpleNamespace(
            multi_task=True,
            get_model_branch=lambda: (
                {"Domains_Alloy": "Domains_Alloy", "Omat24": "Omat24"},
                {"Domains_Alloy": {"alias": []}, "Omat24": {"alias": []}},
            ),
        )

    def get_ntypes(self):
        self.calls.append("get_ntypes")
        return 2

    def get_rcut(self):
        self.calls.append("get_rcut")
        return 5.5

    def get_type_map(self):
        self.calls.append("get_type_map")
        return ["H", "O"]

    def get_sel_type(self):
        self.calls.append("get_sel_type")
        return []

    def get_dim_fparam(self):
        self.calls.append("get_dim_fparam")
        return 0

    def get_dim_aparam(self):
        self.calls.append("get_dim_aparam")
        return 0

    def get_model_def_script(self):
        self.calls.append("get_model_def_script")
        return {
            "shared_dict": {"type_map_all": ["H", "O"]},
            "model_dict": {"Domains_Alloy": {}, "Omat24": {}},
        }

    def eval(self, *args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("dp_model_identity must not evaluate the model")


def test_identity_reports_public_facts_without_evaluating(monkeypatch, tmp_path):
    """The identity helper reads metadata only and never evaluates the model."""
    _RecordingDeepPot.calls = []
    artifact = tmp_path / "multi.pt"
    artifact.write_bytes(b"checkpoint")
    _install_deepmd(
        monkeypatch,
        calculator_class=_RecordingDeepPot,
        infer_class=_RecordingDeepPot,
    )

    facts = dp_adapter.dp_model_identity(artifact, head=MULTITASK_HEAD)

    assert facts["model"] == str(artifact)
    assert facts["kind"] == dp_adapter.DP_KIND_PT_CHECKPOINT
    assert facts["backend"] == "pt"
    assert facts["head"] == MULTITASK_HEAD
    assert facts["metadata_available"] is True
    assert facts["size_bytes"] == artifact.stat().st_size
    assert facts["ntypes"] == 2
    assert facts["rcut"] == 5.5
    assert facts["type_map"] == ["H", "O"]
    assert facts["type_map_all"] == ["H", "O"]
    assert facts["multi_task"] is True
    assert facts["available_heads"] == ["Domains_Alloy", "Omat24"]
    assert "eval" not in _RecordingDeepPot.calls


def test_identity_reports_an_unreadable_backend_without_raising(monkeypatch, tmp_path):
    """A model the backend cannot load still reports its artifact-level facts."""

    class _BrokenDeepPot:
        def __init__(self, model, head=None, **kwargs):
            raise ValueError("The checkpoint is truncated")

    artifact = tmp_path / "broken.pth"
    artifact.write_bytes(b"truncated")
    _install_deepmd(
        monkeypatch, calculator_class=_BrokenDeepPot, infer_class=_BrokenDeepPot
    )

    facts = dp_adapter.dp_model_identity(artifact)

    assert facts["kind"] == dp_adapter.DP_KIND_FROZEN_ARCHIVE
    assert facts["metadata_available"] is False
    assert "checkpoint is truncated" in facts["metadata_error"]
    assert facts["available_heads"] is None


def test_identity_translates_the_multitask_head_failure(monkeypatch, tmp_path):
    """The identity of a multi-task model without a branch fails closed."""

    class _HeadRequiringDeepPot:
        def __init__(self, model, head=None, **kwargs):
            raise AssertionError(MULTITASK_WITHOUT_HEAD_MESSAGE)

    artifact = tmp_path / "multi.pt"
    artifact.write_bytes(b"checkpoint")
    _install_deepmd(
        monkeypatch,
        calculator_class=_HeadRequiringDeepPot,
        infer_class=_HeadRequiringDeepPot,
    )

    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        dp_adapter.dp_model_identity(artifact)

    assert "Omat24" in str(error.value)
    assert "dp --pt show" in str(error.value)


# --------------------------------------------------------------------------
# real multi-task PT artifact
# --------------------------------------------------------------------------


def test_real_multitask_pt_identity(real_identity):
    """The real multi-task PT checkpoint reports its branch and fingerprint."""
    assert real_identity["kind"] == dp_adapter.DP_KIND_PT_CHECKPOINT
    assert real_identity["backend"] == "pt"
    assert real_identity["head"] == MULTITASK_HEAD
    assert real_identity["multi_task"] is True
    assert MULTITASK_HEAD in real_identity["available_heads"]
    assert len(real_identity["available_heads"]) > 5
    assert real_identity["ntypes"] == len(real_identity["type_map"])
    assert "H" in real_identity["type_map"]
    assert real_identity["rcut"] > 0
    # Selected branch and full checkpoint type map are both visible facts.
    assert "H" in real_identity["type_map_all"]
    assert real_identity["metadata_available"] is True


def test_real_multitask_pt_model_without_head_fails_closed(multitask_model):
    """The local multi-task artifact rejects a construction without a branch."""
    with pytest.raises(dp_adapter.DeepPotentialError) as error:
        calculator_factory.CalculatorFactory.get_calculator(
            "dp", _config(str(multitask_model))
        )

    message = str(error.value)
    assert MULTITASK_HEAD in message
    assert "dp --pt show" in message


def test_real_multitask_pt_model_evaluates_with_the_selected_head(multitask_model):
    """The guarded calculator keeps evaluating the real artifact through ASE."""
    calculator_factory.DeepPotentialFactory._instances.clear()
    calc = calculator_factory.CalculatorFactory.get_calculator(
        "dp", _config(str(multitask_model), head=MULTITASK_HEAD)
    )
    assert calc.atst_model_kind == dp_adapter.DP_KIND_PT_CHECKPOINT

    atoms = Atoms(
        "H2O",
        positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.96], [0.92, 0.0, -0.30]],
        cell=[8.0, 8.0, 8.0],
        pbc=True,
    )
    atoms.calc = calc

    energy = atoms.get_potential_energy()
    forces = atoms.get_forces()

    assert math.isfinite(energy)
    assert forces.shape == (3, 3)
    assert np.isfinite(forces).all()
    # A non-equilibrium geometry: a calculator that silently skipped the
    # backend would report zeros here.
    assert np.abs(forces).max() > 1e-6
