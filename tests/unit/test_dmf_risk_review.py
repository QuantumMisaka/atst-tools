import importlib.util
from pathlib import Path

import pytest
from ase import Atoms
from ase.constraints import FixAtoms


def _load_risk_review_script():
    script = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "18_dmf_production_validation"
        / "dmf_risk_review.py"
    )
    spec = importlib.util.spec_from_file_location("dmf_risk_review", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_path_length_metrics_reports_ratio():
    module = _load_risk_review_script()
    path = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[0.5, 0.0, 0.0]]),
        Atoms("H", positions=[[1.0, 0.0, 0.0]]),
    ]
    baseline = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[0.25, 0.0, 0.0]]),
        Atoms("H", positions=[[0.5, 0.0, 0.0]]),
    ]

    metrics = module.path_length_metrics(path, baseline)

    assert metrics["path_length_A"] == pytest.approx(1.0)
    assert metrics["baseline_path_length_A"] == pytest.approx(0.5)
    assert metrics["path_length_ratio"] == pytest.approx(2.0)


def test_fixed_atom_displacement_uses_constraints():
    module = _load_risk_review_script()
    init = Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    final = init.copy()
    final.positions[0, 0] = 0.02
    init.set_constraint(FixAtoms(indices=[0]))

    assert module.max_fixed_atom_displacement(init, final) == pytest.approx(0.02)


def test_tmax_index_gap_compares_continuous_candidate_to_rounded_path_image():
    module = _load_risk_review_script()
    path = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[1.0, 0.0, 0.0]]),
        Atoms("H", positions=[[2.0, 0.0, 0.0]]),
    ]
    candidate = Atoms("H", positions=[[1.25, 0.0, 0.0]])

    metrics = module.tmax_index_gap_metrics(path, candidate, 0.6)

    assert metrics["rounded_index"] == 1
    assert metrics["candidate_vs_rounded_rmsd_A"] == pytest.approx(0.25)
    assert metrics["exceeds_threshold"] is True


def test_analyze_case_marks_invalid_pbc_cfbenm_as_guard_covered(tmp_path, monkeypatch):
    module = _load_risk_review_script()
    root = tmp_path / "example"
    root.mkdir()
    config = root / "config.yaml"
    config.write_text(
        """
calculation:
  type: dmf
  init_file: init.extxyz
  final_file: final.extxyz
  initial_path: cfbenm
  pbc_mode: cartesian_unwrapped
  confirm_pbc_risk: true
  remove_rotation_and_translation: false
calculator:
  name: dp
  dp:
    model: model.pb
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", root)

    report = module.analyze_case(
        {
            "name": "Li-Si_pbc_cfbenm",
            "config": "config.yaml",
            "summary": "missing_summary.json",
            "path": "missing_path.traj",
            "candidate": "missing_candidate.traj",
        }
    )

    assert report["status"] == "guard_covered"
    assert report["risk_confirmed"] is False
    assert report["checks"]["pbc_fbenm_guard"]["pass"] is True


def test_analyze_case_marks_case_timeout_as_confirmed_runtime_risk(tmp_path, monkeypatch):
    module = _load_risk_review_script()
    root = tmp_path / "example"
    case_dir = root / "risk_cases" / "H2-Au_wrapped_final_image"
    case_dir.mkdir(parents=True)
    config = case_dir / "config.yaml"
    config.write_text(
        """
calculation:
  type: dmf
  init_file: init.extxyz
  final_file: final.extxyz
  initial_path: linear
  pbc_mode: cartesian_unwrapped
  confirm_pbc_risk: true
  remove_rotation_and_translation: false
calculator:
  name: dp
  dp:
    model: model.pb
""",
        encoding="utf-8",
    )
    status_path = case_dir / "run_status.json"
    status_path.write_text(
        '{"status": "timeout", "exit_code": 124, "elapsed_seconds": 1200}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", root)

    report = module.analyze_case(
        {
            "name": "H2-Au_wrapped_final_image",
            "config": "risk_cases/H2-Au_wrapped_final_image/config.yaml",
            "summary": "risk_cases/H2-Au_wrapped_final_image/missing_summary.json",
            "path": "risk_cases/H2-Au_wrapped_final_image/missing_path.traj",
            "candidate": "risk_cases/H2-Au_wrapped_final_image/missing_candidate.traj",
            "run_status": "risk_cases/H2-Au_wrapped_final_image/run_status.json",
        }
    )

    assert report["status"] == "timeout"
    assert report["risk_confirmed"] is True
    assert report["checks"]["runtime_completion"]["pass"] is False
