"""Tests for the Sella optimizer event sidecar."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.emt import EMT


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class _FakeTrajectory:
    def __init__(self, filename, mode, atoms):
        self.filename = str(filename)
        self.frames = []

    def __len__(self):
        return len(self.frames)

    def close(self):
        return None


class _FakePES:
    def __init__(self, *, with_frame_id=True):
        self.curr = {"traj_id": 0 if with_frame_id else None}
        if with_frame_id:
            self._last_eval_traj_id = 0

    def diag(self, gamma=0.1, threepoint=False, maxiter=None, progress=None):
        return None


class _FakeSella:
    instances = []

    def __init__(self, atoms, trajectory=None, eta=None, order=None, hessian_progress=False):
        self.atoms = atoms
        self.trajectory = trajectory
        self.pes = _FakePES()
        self.native_events = []
        self.diagkwargs = {
            "progress": self._native_progress if hessian_progress else None,
        }
        self.nsteps = 0
        self.__class__.instances.append(self)

    def _native_progress(self, event, evaluations):
        self.native_events.append((event, evaluations))

    def run(self, fmax=0.05, steps=100000000):
        result = None
        for result in self.irun(fmax=fmax, steps=steps):
            pass
        return result

    def irun(self, fmax=0.05, steps=100000000):
        self.pes.curr["traj_id"] = 1
        self.pes._last_eval_traj_id = 1
        yield False
        if self.diagkwargs["progress"] is not None:
            self.diagkwargs["progress"]("start", 0)
            self.pes._last_eval_traj_id = 2
            self.diagkwargs["progress"]("evaluation", 1)
            self.diagkwargs["progress"]("done", 1)
        self.nsteps = 1
        self.pes.curr["traj_id"] = 3
        yield True


def _workflow(monkeypatch, tmp_path, *, record_events=True, hessian_progress=False):
    from atst_tools.mep import sella as sella_module

    _FakeSella.instances.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sella_module, "Trajectory", _FakeTrajectory)
    monkeypatch.setattr(sella_module, "Sella", _FakeSella)
    monkeypatch.setattr(
        sella_module.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: object(),
    )
    workflow = sella_module.AbacusSella(
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "directory": "sella_run",
            "max_steps": 3,
            "record_events": record_events,
            "hessian_progress": hessian_progress,
            "artifact_manifest": None,
        },
        traj_file=str(tmp_path / "sella.traj"),
    )
    workflow.run()
    return workflow, _FakeSella.instances[-1]


def test_event_sidecar_distinguishes_initial_and_optimizer_steps(monkeypatch, tmp_path):
    workflow, dyn = _workflow(monkeypatch, tmp_path, hessian_progress=True)

    events = _read_events(tmp_path / "sella.events.jsonl")
    assert [event["event"] for event in events] == [
        "run_start",
        "initial_state",
        "hessian_start",
        "hessian_evaluation",
        "hessian_done",
        "optimizer_step",
        "run_end",
    ]
    assert events[0]["schema_version"] == "sella-events-v1"
    assert events[0]["capabilities"] == {
        "events": True,
        "hessian_progress": True,
        "optimizer_checkpoints": True,
        "trajectory_frame_id": True,
    }
    assert events[1]["optimizer_step"] == 0
    assert events[1]["frame_index"] == 1
    assert events[2]["cycle"] == 1
    assert events[2]["optimizer_step"] == 0
    assert events[3]["frame_index"] == 2
    assert events[5]["optimizer_step"] == 1
    assert events[5]["frame_index"] == 3
    assert events[-1]["actual_steps"] == 1
    assert events[-1]["converged"] is True
    assert events[-1]["trajectory_frames"] == 0
    assert workflow.last_events_file == str(tmp_path / "sella.events.jsonl")
    assert dyn.native_events == [
        ("start", 0),
        ("evaluation", 1),
        ("done", 1),
    ]


def test_record_events_false_removes_stale_sidecar_and_keeps_run(monkeypatch, tmp_path):
    stale = tmp_path / "sella.events.jsonl"
    stale.write_text('{"schema":"sella-events-v1"}\n', encoding="utf-8")
    workflow, _ = _workflow(monkeypatch, tmp_path, record_events=False)

    assert not stale.exists()
    assert workflow.last_events_file is None


def test_failure_flushes_run_failed_and_reraises(monkeypatch, tmp_path):
    from atst_tools.mep import sella as sella_module

    class FailingSella(_FakeSella):
        def irun(self, fmax=0.05, steps=100000000):
            self.pes.curr["traj_id"] = 4
            yield False
            raise RuntimeError("synthetic optimizer failure")

    monkeypatch.setattr(sella_module, "Trajectory", _FakeTrajectory)
    monkeypatch.setattr(sella_module, "Sella", FailingSella)
    monkeypatch.setattr(
        sella_module.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: object(),
    )
    workflow = sella_module.AbacusSella(
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"artifact_manifest": None},
        traj_file=str(tmp_path / "sella.traj"),
    )

    with pytest.raises(RuntimeError, match="synthetic optimizer failure"):
        workflow.run()

    events = _read_events(tmp_path / "sella.events.jsonl")
    assert events[-1]["event"] == "run_failed"
    assert events[-1]["actual_steps"] == 0
    assert events[-1]["error_type"] == "RuntimeError"


def test_native_hessian_callback_failure_is_not_swallowed(monkeypatch, tmp_path):
    from atst_tools.mep import sella as sella_module

    class CallbackFailSella(_FakeSella):
        def _native_progress(self, event, evaluations):
            raise ValueError("native progress failed")

    monkeypatch.setattr(sella_module, "Trajectory", _FakeTrajectory)
    monkeypatch.setattr(sella_module, "Sella", CallbackFailSella)
    monkeypatch.setattr(
        sella_module.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: object(),
    )
    workflow = sella_module.AbacusSella(
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"artifact_manifest": None, "hessian_progress": True},
        traj_file=str(tmp_path / "sella.traj"),
    )

    with pytest.raises(ValueError, match="native progress failed"):
        workflow.run()

    assert _read_events(tmp_path / "sella.events.jsonl")[-1]["event"] == "run_failed"


def test_missing_hessian_progress_capability_is_explicit_when_requested(monkeypatch, tmp_path):
    from atst_tools.mep import sella as sella_module

    class NoProgressSella:
        def __init__(self, atoms, trajectory=None, eta=None, order=None):
            self.pes = object()
            self.nsteps = 0

    monkeypatch.setattr(sella_module, "Trajectory", _FakeTrajectory)
    monkeypatch.setattr(sella_module, "Sella", NoProgressSella)
    monkeypatch.setattr(
        sella_module.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: object(),
    )
    workflow = sella_module.AbacusSella(
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"artifact_manifest": None, "hessian_progress": True},
        traj_file=str(tmp_path / "sella.traj"),
    )

    with pytest.raises(RuntimeError, match="hessian_progress"):
        workflow.run()


def test_missing_frame_id_is_reported_without_inventing_one(monkeypatch, tmp_path):
    from atst_tools.mep import sella as sella_module

    class NoFrameSella(_FakeSella):
        def __init__(self, atoms, trajectory=None, eta=None, order=None, hessian_progress=False):
            super().__init__(atoms, trajectory, eta, order, hessian_progress)
            self.pes.curr = {}
            del self.pes._last_eval_traj_id

        def irun(self, fmax=0.05, steps=100000000):
            yield False
            self.nsteps = 1
            yield False

    monkeypatch.setattr(sella_module, "Trajectory", _FakeTrajectory)
    monkeypatch.setattr(sella_module, "Sella", NoFrameSella)
    monkeypatch.setattr(
        sella_module.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: object(),
    )
    workflow = sella_module.AbacusSella(
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"artifact_manifest": None},
        traj_file=str(tmp_path / "sella.traj"),
    )
    workflow.run()

    events = _read_events(tmp_path / "sella.events.jsonl")
    assert events[0]["capabilities"]["trajectory_frame_id"] is False
    assert events[1]["frame_index"] is None
    assert events[2]["frame_index"] is None


def test_config_exposes_event_controls():
    from atst_tools.utils.config import ConfigLoader

    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "sella",
                "init_structure": "sella_init.stru",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["record_events"] is True
    assert config["calculation"]["hessian_progress"] is False


def test_config_rejects_non_boolean_event_controls():
    from atst_tools.utils.config import ConfigLoader

    with pytest.raises(ValueError, match="record_events"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "sella",
                    "init_structure": "sella_init.stru",
                    "record_events": "yes",
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


@pytest.mark.parametrize("fmax", (0.01, 100.0))
def test_real_sella_event_recording_preserves_steps_positions_and_evaluations(
    monkeypatch, tmp_path, fmax
):
    """The public ``irun`` instrumentation is numerically transparent."""
    from atst_tools.mep import sella as sella_module

    class CountingEMT(EMT):
        def __init__(self):
            super().__init__()
            self.calculations = 0

        def calculate(self, atoms=None, properties=("energy",), system_changes=None):
            self.calculations += 1
            return super().calculate(atoms, properties, system_changes)

    active_calc = None

    def factory(*args, **kwargs):
        return active_calc

    monkeypatch.setattr(sella_module.CalculatorFactory, "get_calculator", factory)

    baseline_atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]])
    baseline_calc = CountingEMT()
    active_calc = baseline_calc
    baseline = sella_module.AbacusSella(
        baseline_atoms,
        {"calculator": {"name": "emt", "emt": {}}},
        "emt",
        {"max_steps": 2, "artifact_manifest": None, "record_events": False},
        traj_file=str(tmp_path / "baseline.traj"),
        fmax=fmax,
    )
    baseline.run()
    baseline_steps = baseline.last_stage_record.actual_steps
    baseline_positions = baseline_atoms.positions.copy()

    candidate_atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]])
    candidate_calc = CountingEMT()
    active_calc = candidate_calc
    candidate = sella_module.AbacusSella(
        candidate_atoms,
        {"calculator": {"name": "emt", "emt": {}}},
        "emt",
        {"max_steps": 2, "artifact_manifest": None},
        traj_file=str(tmp_path / "candidate.traj"),
        fmax=fmax,
    )
    candidate.run()

    assert candidate.last_stage_record.actual_steps == baseline_steps
    assert candidate_calc.calculations == baseline_calc.calculations
    assert baseline_steps == (0 if fmax == 100.0 else 2)
    assert candidate_calc.results["energy"] == pytest.approx(baseline_calc.results["energy"], abs=1e-14)
    np.testing.assert_allclose(candidate_calc.results["forces"], baseline_calc.results["forces"], atol=1e-14)
    np.testing.assert_allclose(candidate_atoms.positions, baseline_positions, atol=1e-14)
    run_end = _read_events(tmp_path / "candidate.events.jsonl")[-1]
    assert run_end["actual_steps"] == baseline_steps
    digest = hashlib.sha256((tmp_path / "candidate.traj").read_bytes()).hexdigest()
    assert run_end["trajectory_sha256"] == digest
    from atst_tools.utils.summary import summarize_trajectory

    summary = summarize_trajectory(tmp_path / "candidate.traj", workflow="sella")
    assert summary["status"]["actual_steps"] == baseline_steps
    assert summary["status"]["converged"] is baseline.last_stage_record.converged
    assert summary["status"]["events"]["status"] == "complete"
    assert not (tmp_path / "baseline.events.jsonl").exists()
