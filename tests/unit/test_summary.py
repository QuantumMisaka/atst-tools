import hashlib
import json

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write

from atst_tools.utils.summary import (
    summarize_artifact_manifest,
    summarize_d2s_config,
    summarize_neb_trajectory,
    summarize_trajectory,
)


def _atoms(energy=0.0, force=0.0, x=0.0):
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=[[force, 0.0, 0.0]])
    atoms.info["energy"] = energy
    atoms.arrays["forces"] = np.array([[force, 0.0, 0.0]], dtype=float)
    return atoms


def test_neb_summary_reports_complete_steps_and_max_force_image(tmp_path):
    traj = tmp_path / "neb.traj"
    images = [
        _atoms(0.0, 0.0, 0.0),
        _atoms(1.0, 0.2, 1.0),
        _atoms(0.1, 0.1, 2.0),
        _atoms(0.0, 0.0, 0.0),
        _atoms(0.7, 0.4, 1.0),
        _atoms(0.2, 0.1, 2.0),
    ]
    write(traj, images)

    summary = summarize_neb_trajectory(traj, n_max=1)

    assert summary["schema_version"] == "atst-summary-v1"
    assert summary["workflow"] == "neb"
    assert summary["status"]["n_frames"] == 6
    assert summary["status"]["n_images"] == 3
    assert summary["status"]["complete_steps"] == 2
    assert summary["status"]["remainder_frames"] == 0
    assert summary["steps"][0]["max_force_image"] == 1
    assert summary["steps"][0]["max_force_eV_per_A"] == pytest.approx(0.2)
    assert summary["steps"][0]["max_force_image_energy_eV"] == pytest.approx(1.0)
    assert summary["latest"]["barrier_eV"] == pytest.approx(0.7)
    assert summary["latest"]["ts_image"] == 1


def test_neb_summary_strict_rejects_incomplete_band(tmp_path):
    traj = tmp_path / "neb.traj"
    write(traj, [_atoms(0.0), _atoms(1.0), _atoms(0.0), _atoms(0.2)])

    summary = summarize_neb_trajectory(traj, n_max=1)

    assert summary["status"]["complete_steps"] == 1
    assert summary["status"]["remainder_frames"] == 1
    with pytest.raises(ValueError, match="not a whole number"):
        summarize_neb_trajectory(traj, n_max=1, strict=True)


def test_trajectory_summary_reports_latest_energy_and_fmax(tmp_path):
    traj = tmp_path / "relax.traj"
    write(traj, [_atoms(-1.0, 0.3), _atoms(-1.5, 0.05)])

    summary = summarize_trajectory(traj, workflow="relax")

    assert summary["workflow"] == "relax"
    assert summary["status"]["n_frames"] == 2
    assert summary["latest"]["energy_eV"] == pytest.approx(-1.5)
    assert summary["latest"]["max_force_eV_per_A"] == pytest.approx(0.05)
    assert [frame["step"] for frame in summary["frames"]] == [0, 1]


def _write_sella_events(path, *, trajectory, actual_steps=2, converged=True):
    """Write the small stable event vocabulary used by the Sella producer."""
    records = [
        {
            "schema_version": "sella-events-v1",
            "event": "run_start",
            "trajectory": trajectory.name,
            "capabilities": {
                "frame_ids": True,
                "hessian_progress": True,
                "optimizer_checkpoints": True,
            },
        },
        {
            "schema_version": "sella-events-v1",
            "event": "initial_state",
            "optimizer_step": 0,
            "frame_index": 0,
            "converged": False,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "hessian_start",
            "cycle": 1,
            "optimizer_step": 0,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "hessian_evaluation",
            "cycle": 1,
            "optimizer_step": 0,
            "frame_index": 1,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "hessian_done",
            "cycle": 1,
            "optimizer_step": 0,
            "evaluations": 1,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "optimizer_step",
            "optimizer_step": 1,
            "frame_index": 2,
            "converged": False,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "optimizer_step",
            "optimizer_step": actual_steps,
            "frame_index": 4,
            "converged": converged,
        },
    ]
    trajectory_frames = len(read(str(trajectory), index=":"))
    records.append(
        {
            "schema_version": "sella-events-v1",
            "event": "run_end",
            "actual_steps": actual_steps,
            "converged": converged,
            "trajectory_sha256": hashlib.sha256(trajectory.read_bytes()).hexdigest(),
            "trajectory_frames": trajectory_frames,
        }
    )
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def test_trajectory_summary_distinguishes_sella_frames_and_optimizer_steps(tmp_path):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(float(index), x=index) for index in range(5)])
    _write_sella_events(traj.with_suffix(".events.jsonl"), trajectory=traj)

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["n_frames"] == 5
    assert summary["status"]["complete"] is True
    assert summary["status"]["actual_steps"] == 2
    assert summary["status"]["converged"] is True
    assert summary["status"]["events"]["status"] == "complete"
    assert [frame["step"] for frame in summary["frames"]] == [0, 1, 2, 3, 4]
    assert summary["frames"][0]["frame_kind"] == "optimizer_state"
    assert summary["frames"][0]["optimizer_step"] == 0
    assert summary["frames"][1]["frame_kind"] == "hessian_probe"
    assert summary["frames"][1]["optimizer_step"] == 0
    assert summary["frames"][2]["frame_kind"] == "optimizer_state"
    assert summary["frames"][2]["optimizer_step"] == 1
    assert summary["frames"][4]["optimizer_step"] == 2


def test_trajectory_summary_keeps_local_events_but_rejects_truncated_sidecar(tmp_path):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(float(index), x=index) for index in range(3)])
    events = traj.with_suffix(".events.jsonl")
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {"schema_version": "sella-events-v1", "event": "run_start"}
                ),
                json.dumps(
                    {
                        "schema_version": "sella-events-v1",
                        "event": "optimizer_step",
                        "optimizer_step": 1,
                        "frame_index": 2,
                        "converged": False,
                    }
                ),
            ]
        )
        + "\n{",
        encoding="utf-8",
    )

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["events"]["status"] == "partial_unverified"
    assert summary["status"]["complete"] is True
    assert summary["status"]["events_complete"] is False
    assert summary["status"]["events"]["complete"] is False
    assert summary["status"]["actual_steps"] is None
    assert summary["status"]["converged"] is None
    assert summary["frames"][2]["frame_kind"] == "unclassified_evaluation"
    assert any("invalid JSON" in item for item in summary["status"]["events"]["diagnostics"])


def test_trajectory_summary_rejects_sidecar_for_a_different_trajectory(tmp_path):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(float(index), x=index) for index in range(3)])
    events = traj.with_suffix(".events.jsonl")
    events.write_text(
        "\n".join(
            [
                json.dumps({"schema_version": "sella-events-v1", "event": "run_start"}),
                json.dumps(
                    {
                        "schema_version": "sella-events-v1",
                        "event": "optimizer_step",
                        "optimizer_step": 1,
                        "frame_index": 2,
                        "converged": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "sella-events-v1",
                        "event": "run_end",
                        "actual_steps": 1,
                        "converged": True,
                        "trajectory_sha256": "0" * 64,
                        "trajectory_frames": 3,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["events"]["status"] == "invalid"
    assert summary["status"]["complete"] is True
    assert summary["status"]["events_complete"] is False
    assert summary["status"]["actual_steps"] is None
    assert summary["status"]["converged"] is None
    assert summary["frames"][2]["frame_kind"] == "unclassified_evaluation"


def test_trajectory_summary_rejects_missing_optimizer_checkpoint(tmp_path):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(float(index), x=index) for index in range(5)])
    events = traj.with_suffix(".events.jsonl")
    _write_sella_events(events, trajectory=traj)
    events.write_text(
        events.read_text(encoding="utf-8").replace('"actual_steps": 2', '"actual_steps": 3'),
        encoding="utf-8",
    )

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["events"]["status"] == "invalid"
    assert summary["status"]["actual_steps"] is None
    assert any(
        "checkpoints do not cover" in item
        for item in summary["status"]["events"]["diagnostics"]
    )


def test_trajectory_summary_keeps_step_fact_when_frame_ids_are_unavailable(tmp_path):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(0.0), _atoms(-0.2)])
    events = traj.with_suffix(".events.jsonl")
    records = [
        {
            "schema_version": "sella-events-v1",
            "event": "run_start",
            "capabilities": {"frame_ids": False, "optimizer_checkpoints": True},
        },
        {
            "schema_version": "sella-events-v1",
            "event": "initial_state",
            "optimizer_step": 0,
            "converged": False,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "optimizer_step",
            "optimizer_step": 1,
            "converged": True,
        },
        {
            "schema_version": "sella-events-v1",
            "event": "run_end",
            "actual_steps": 1,
            "converged": True,
            "trajectory_sha256": hashlib.sha256(traj.read_bytes()).hexdigest(),
            "trajectory_frames": 2,
        },
    ]
    events.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["events"]["status"] == "complete"
    assert summary["status"]["actual_steps"] == 1
    assert summary["status"]["events"]["step_count_verified"] is True
    assert all(frame["frame_kind"] == "unclassified_evaluation" for frame in summary["frames"])


@pytest.mark.parametrize("terminal_value", [None, "invalid", "missing"])
def test_trajectory_summary_rejects_untrusted_terminal_convergence_without_frame_ids(
    tmp_path, terminal_value
):
    traj = tmp_path / "sella.traj"
    write(traj, [_atoms(0.0), _atoms(-0.2)])
    events = traj.with_suffix(".events.jsonl")
    terminal = {
        "schema_version": "sella-events-v1",
        "event": "optimizer_step",
        "optimizer_step": 1,
        "converged": terminal_value,
    }
    if terminal_value == "missing":
        terminal.pop("converged")
    records = [
        {
            "schema_version": "sella-events-v1",
            "event": "run_start",
            "capabilities": {"trajectory_frame_id": False, "optimizer_checkpoints": True},
        },
        {
            "schema_version": "sella-events-v1",
            "event": "initial_state",
            "optimizer_step": 0,
            "converged": False,
        },
        terminal,
        {
            "schema_version": "sella-events-v1",
            "event": "run_end",
            "actual_steps": 1,
            "converged": True,
            "trajectory_sha256": hashlib.sha256(traj.read_bytes()).hexdigest(),
            "trajectory_frames": 2,
        },
    ]
    events.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )

    summary = summarize_trajectory(traj, workflow="sella")

    assert summary["status"]["events"]["status"] == "invalid"
    assert summary["status"]["actual_steps"] is None
    assert any("converged" in item for item in summary["status"]["events"]["diagnostics"])


def test_d2s_summary_marks_missing_stages_and_reads_present_rough_neb(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write("neb_rough.traj", [_atoms(0.0), _atoms(0.9), _atoms(0.1)])
    config = tmp_path / "d2s.yaml"
    config.write_text(
        """
calculation:
  type: d2s
  init_file: init.traj
  final_file: final.traj
  method: dimer
  neb:
    n_images: 1
  dimer:
    trajectory: dimer.traj
calculator:
  name: abacus
  abacus:
    parameters: {}
""",
        encoding="utf-8",
    )

    summary = summarize_d2s_config(config)

    assert summary["workflow"] == "d2s"
    assert summary["stages"]["rough_neb"]["status"] == "present"
    assert summary["stages"]["rough_neb"]["latest"]["barrier_eV"] == pytest.approx(0.9)
    assert summary["stages"]["single_ended"]["status"] == "missing"


def test_d2s_summary_resolves_outputs_relative_to_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write(run_dir / "neb_rough.traj", [_atoms(0.0), _atoms(0.5), _atoms(0.0)])
    config = run_dir / "d2s.yaml"
    config.write_text(
        """
calculation:
  type: d2s
  init_file: init.traj
  final_file: final.traj
  method: dimer
  neb:
    n_images: 1
calculator:
  name: abacus
  abacus:
    parameters: {}
""",
        encoding="utf-8",
    )

    summary = summarize_d2s_config(config)

    assert summary["stages"]["rough_neb"]["status"] == "present"
    assert summary["stages"]["rough_neb"]["source"].endswith("run/neb_rough.traj")


def test_artifact_manifest_summary_reports_existing_and_missing_files(tmp_path):
    from atst_tools.utils.artifacts import write_artifact_manifest

    present = tmp_path / "ts.traj"
    present.write_text("placeholder", encoding="utf-8")
    manifest = write_artifact_manifest(
        tmp_path / "atst_artifacts.json",
        workflow="ccqn",
        artifacts=[
            {"role": "ts_structure", "path": "ts.traj"},
            {"role": "validation", "path": "missing.json"},
        ],
        stages=[{"name": "ccqn", "status": "complete"}],
    )

    summary = summarize_artifact_manifest(tmp_path / "atst_artifacts.json")

    assert manifest["schema_version"] == "atst-artifacts-v1"
    assert summary["workflow"] == "ccqn"
    assert summary["artifacts"][0]["exists"] is True
    assert summary["artifacts"][1]["exists"] is False


def test_artifact_manifest_writes_numpy_scalars(tmp_path):
    import json

    import numpy as np

    from atst_tools.utils.artifacts import write_artifact_manifest

    write_artifact_manifest(
        tmp_path / "atst_artifacts.json",
        workflow="neb",
        artifacts=[],
        metadata={"parallel": np.bool_(True), "images": np.int64(5), "fmax": np.float64(0.12)},
    )

    manifest = json.loads((tmp_path / "atst_artifacts.json").read_text(encoding="utf-8"))

    assert manifest["metadata"] == {"parallel": True, "images": 5, "fmax": 0.12}


def test_ts_validation_summary_classifies_one_imaginary_mode():
    from atst_tools.utils.ts_validation import build_ts_validation_summary

    validation = build_ts_validation_summary(
        {
            "frequencies": [100.0, 200.0, 300.0],
            "imaginary_frequencies": [120.0, 0.0, 0.0],
        },
        fmax=0.03,
        fmax_threshold=0.05,
    )

    assert validation["status"] == "pass"
    assert validation["checks"]["n_imaginary_modes"]["value"] == 1
