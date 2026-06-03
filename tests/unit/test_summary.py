import json

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import write

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
