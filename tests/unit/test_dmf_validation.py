import json
import importlib.util
from pathlib import Path

import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms
from ase.io import read, write

from atst_tools.utils.dmf_validation import (
    summarize_abacus_candidate_comparison,
    summarize_dmf_candidate,
    summarize_irc_endpoint_connection,
    summarize_manifest,
)


def _load_abacus_comparison_script():
    script = Path(__file__).resolve().parents[2] / "scripts" / "validate_dmf_abacus_comparison.py"
    spec = importlib.util.spec_from_file_location("validate_dmf_abacus_comparison", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_lts_fallback_writes_force_structure_with_constraints(tmp_path, monkeypatch):
    module = _load_abacus_comparison_script()
    run_dir = tmp_path / "run"
    log_dir = run_dir / "OUT.ABACUS"
    log_dir.mkdir(parents=True)
    (log_dir / "running_scf.log").write_text(
        """
 TOTAL-FORCE (eV/Angstrom)
------------------------------------------------------------------------------------------
 H1 0.4000000000 0.0000000000 0.0000000000
 H2 0.0300000000 0.0000000000 0.0000000000
------------------------------------------------------------------------------------------
 !FINAL_ETOT_IS -8.9500000000000000 eV
""",
        encoding="utf-8",
    )
    source = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.80, 0.0, 0.0]])
    source.set_constraint(FixAtoms(indices=[0]))
    write(tmp_path / "source.extxyz", source)

    def fake_collect_abacus_output(*args, **kwargs):
        return {"parsed": False, "logs": ["OUT.ABACUS/running_scf.log"], "parse_error": "missing eig_occ"}

    monkeypatch.setattr(module, "collect_abacus_output", fake_collect_abacus_output)

    summary = module.collect_with_lts_fallback(
        run_dir,
        tmp_path / "summary.json",
        tmp_path / "abacus_final.extxyz",
        tmp_path / "source.extxyz",
    )
    collected = read(tmp_path / "abacus_final.extxyz")

    assert summary["parsed"] is True
    assert summary["max_force_eV_per_ang"] == pytest.approx(0.40)
    assert collected.get_forces(apply_constraint=False)[0, 0] == pytest.approx(0.40)
    assert collected.get_forces(apply_constraint=True)[0, 0] == pytest.approx(0.0)


def test_summarize_dmf_candidate_compares_abacus_and_dp_references(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    dp_dir = root / "examples" / "dp_reference_structures"
    ref_dir.mkdir(parents=True)
    dp_dir.mkdir(parents=True)

    abacus_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])
    dp_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.80, 0.0, 0.0]])
    candidate = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.78, 0.0, 0.0]])
    candidate.info["energy"] = 3.0

    write(ref_dir / "case_ts.extxyz", abacus_ts)
    write(dp_dir / "case_dp_ts.extxyz", dp_ts)
    write(root / "candidate.traj", candidate)
    _write_json(
        root / "dmf_summary.json",
        {
            "workflow": "dmf",
            "experimental": True,
            "result_type": "ts_candidate",
            "validated_ts": False,
            "tmax": 0.5,
            "n_images": 5,
            "initial_path": "cfbenm",
            "pbc_mode": "reject",
            "ipopt_status": {"status": 0},
        },
    )
    _write_json(
        root / "examples" / "reference_results.json",
        {
            "cases": {
                "case": {
                    "forward_barrier_eV": 1.2,
                    "transition_state_structure": "examples/reference_structures/case_ts.extxyz",
                }
            }
        },
    )
    _write_json(
        root / "examples" / "dp_reference_results.json",
        {
            "cases": {
                "case": {
                    "metrics": {"barrier_eV": 1.4},
                    "comparison": {"abacus_barrier_eV": 1.2, "delta_vs_abacus_eV": 0.2},
                    "structure": {"path": "dp_reference_structures/case_dp_ts.extxyz"},
                }
            }
        },
    )

    report = summarize_dmf_candidate(
        case_name="case",
        dmf_summary=root / "dmf_summary.json",
        dmf_candidate=root / "candidate.traj",
        reference_results=root / "examples" / "reference_results.json",
        dp_reference_results=root / "examples" / "dp_reference_results.json",
        root_dir=root,
    )

    assert report["schema_version"] == "atst-dmf-validation-v1"
    assert report["case"] == "case"
    assert report["experimental"] is True
    assert report["result_type"] == "ts_candidate"
    assert report["validated_ts"] is False
    assert report["dmf"]["tmax"] == pytest.approx(0.5)
    assert report["baselines"]["abacus"]["barrier_eV"] == pytest.approx(1.2)
    assert report["baselines"]["dp"]["barrier_eV"] == pytest.approx(1.4)
    assert report["candidate"]["rmsd_to_abacus_ts_ang"] == pytest.approx(0.0122474487)
    assert report["candidate"]["rmsd_to_dp_ts_ang"] == pytest.approx(0.0081649658)
    assert report["candidate"]["energy_eV"] == pytest.approx(3.0)
    assert report["status"] == "candidate_compared"


def test_summarize_dmf_candidate_rejects_atom_count_mismatch(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    ref_dir.mkdir(parents=True)
    write(ref_dir / "case_ts.extxyz", Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]]))
    write(root / "candidate.traj", Atoms("H", positions=[[0.0, 0.0, 0.0]]))
    _write_json(root / "dmf_summary.json", {"workflow": "dmf"})
    _write_json(
        root / "reference_results.json",
        {
            "cases": {
                "case": {
                    "transition_state_structure": "examples/reference_structures/case_ts.extxyz",
                }
            }
        },
    )

    with pytest.raises(ValueError, match="atom count mismatch"):
        summarize_dmf_candidate(
            case_name="case",
            dmf_summary=root / "dmf_summary.json",
            dmf_candidate=root / "candidate.traj",
            reference_results=root / "reference_results.json",
            root_dir=root,
        )


def test_summarize_manifest_writes_multi_case_report(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    ref_dir.mkdir(parents=True)
    cases = {}
    manifest_cases = []
    for index, case_name in enumerate(("case_a", "case_b")):
        candidate = Atoms("H", positions=[[float(index), 0.0, 0.0]])
        write(root / f"{case_name}_candidate.traj", candidate)
        write(ref_dir / f"{case_name}_ts.extxyz", candidate)
        _write_json(root / f"{case_name}_summary.json", {"workflow": "dmf", "tmax": 0.5})
        cases[case_name] = {
            "forward_barrier_eV": 1.0 + index,
            "transition_state_structure": f"examples/reference_structures/{case_name}_ts.extxyz",
        }
        manifest_cases.append(
            {
                "name": case_name,
                "dmf_summary": f"{case_name}_summary.json",
                "dmf_candidate": f"{case_name}_candidate.traj",
            }
        )
    _write_json(root / "reference_results.json", {"cases": cases})

    report = summarize_manifest(
        {
            "cases": manifest_cases,
            "reference_results": "reference_results.json",
        },
        root_dir=root,
        output=root / "dmf_validation_report.json",
    )

    assert report["schema_version"] == "atst-dmf-validation-suite-v1"
    assert report["status"] == "candidate_compared"
    assert [case["case"] for case in report["cases"]] == ["case_a", "case_b"]
    assert (root / "dmf_validation_report.json").is_file()


def test_summarize_irc_endpoint_connection_matches_swapped_branches(tmp_path):
    init = Atoms("H2", positions=[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    final = Atoms("H2", positions=[[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    branch_to_final = Atoms("H2", positions=[[1.02, 0.0, 0.0], [2.0, 0.0, 0.0]])
    branch_to_init = Atoms("H2", positions=[[0.01, 0.0, 0.0], [2.0, 0.0, 0.0]])
    write(tmp_path / "init.extxyz", init)
    write(tmp_path / "final.extxyz", final)
    write(tmp_path / "irc.traj", [branch_to_final, branch_to_init])

    report = summarize_irc_endpoint_connection(
        case_name="case",
        irc_trajectory=tmp_path / "irc.traj",
        init_structure=tmp_path / "init.extxyz",
        final_structure=tmp_path / "final.extxyz",
        indices=[0],
        rmsd_threshold=0.05,
    )

    assert report["schema_version"] == "atst-dmf-irc-endpoint-v1"
    assert report["status"] == "pass"
    assert report["validated_endpoint_connection"] is True
    assert report["assignment"] == "swapped"
    assert report["endpoints"]["init"]["rmsd_ang"] == pytest.approx(0.0057735027)
    assert report["endpoints"]["final"]["rmsd_ang"] == pytest.approx(0.0115470054)


def test_summarize_irc_endpoint_connection_rejects_atom_count_mismatch(tmp_path):
    write(tmp_path / "init.extxyz", Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    write(tmp_path / "final.extxyz", Atoms("H", positions=[[0.0, 0.0, 0.0]]))
    write(
        tmp_path / "irc.traj",
        [
            Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            Atoms("H2", positions=[[0.1, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        ],
    )

    with pytest.raises(ValueError, match="atom count mismatch"):
        summarize_irc_endpoint_connection(
            case_name="case",
            irc_trajectory=tmp_path / "irc.traj",
            init_structure=tmp_path / "init.extxyz",
            final_structure=tmp_path / "final.extxyz",
            indices=[0],
        )


def test_summarize_abacus_candidate_comparison_reports_barrier_force_and_rmsd(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    ref_dir.mkdir(parents=True)
    reference_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.80, 0.0, 0.0]])
    candidate_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.83, 0.0, 0.0]])
    write(ref_dir / "case_ts.extxyz", reference_ts)
    write(root / "candidate.extxyz", candidate_ts)
    _write_json(
        root / "examples" / "reference_results.json",
        {
            "cases": {
                "case": {
                    "forward_barrier_eV": 1.20,
                    "transition_state_structure": "examples/reference_structures/case_ts.extxyz",
                }
            }
        },
    )
    _write_json(
        root / "singlepoints.json",
        {
            "case": "case",
            "structures": {"candidate": "candidate.extxyz", "initial": "init.extxyz"},
            "singlepoints": {
                "initial": {"energy_eV": -10.0, "fmax_eV_per_A": 0.01},
                "candidate": {"energy_eV": -8.75, "fmax_eV_per_A": 0.04},
            },
        },
    )

    report = summarize_abacus_candidate_comparison(
        case_name="case",
        singlepoint_summary=root / "singlepoints.json",
        reference_results=root / "examples" / "reference_results.json",
        root_dir=root,
        barrier_tolerance_eV=0.10,
        rmsd_threshold_A=0.05,
        fmax_threshold_eV_per_A=0.05,
    )

    assert report["schema_version"] == "atst-dmf-abacus-comparison-v1"
    assert report["status"] == "pass"
    assert report["validated_abacus_comparison"] is True
    assert report["candidate"]["barrier_eV"] == pytest.approx(1.25)
    assert report["candidate"]["barrier_delta_vs_reference_eV"] == pytest.approx(0.05)
    assert report["candidate"]["rmsd_to_reference_ts_A"] == pytest.approx(0.0122474487)
    assert report["candidate"]["fmax_eV_per_A"] == pytest.approx(0.04)


def test_summarize_abacus_candidate_comparison_uses_constrained_candidate_forces(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    ref_dir.mkdir(parents=True)
    reference_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.80, 0.0, 0.0]])
    candidate_ts = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.80, 0.0, 0.0]])
    candidate_ts.set_constraint(FixAtoms(indices=[0]))
    candidate_ts.calc = SinglePointCalculator(
        candidate_ts,
        energy=-8.95,
        forces=[[0.40, 0.0, 0.0], [0.03, 0.0, 0.0]],
    )
    write(ref_dir / "case_ts.extxyz", reference_ts)
    write(root / "candidate.extxyz", candidate_ts)
    _write_json(
        root / "reference_results.json",
        {
            "cases": {
                "case": {
                    "forward_barrier_eV": 1.0,
                    "transition_state_structure": "examples/reference_structures/case_ts.extxyz",
                }
            }
        },
    )
    _write_json(
        root / "singlepoints.json",
        {
            "case": "case",
            "structures": {"candidate": "candidate.extxyz", "initial": "init.extxyz"},
            "singlepoints": {
                "initial": {"energy_eV": -10.0},
                "candidate": {"energy_eV": -8.95, "fmax_eV_per_A": 0.40},
            },
        },
    )

    report = summarize_abacus_candidate_comparison(
        case_name="case",
        singlepoint_summary=root / "singlepoints.json",
        reference_results=root / "reference_results.json",
        root_dir=root,
        barrier_tolerance_eV=0.10,
        rmsd_threshold_A=0.05,
        fmax_threshold_eV_per_A=0.05,
    )

    assert report["status"] == "pass"
    assert report["candidate"]["fmax_eV_per_A"] == pytest.approx(0.03)
    assert report["checks"]["fmax"]["pass"] is True


def test_summarize_abacus_candidate_comparison_fails_outside_thresholds(tmp_path):
    root = tmp_path
    ref_dir = root / "examples" / "reference_structures"
    ref_dir.mkdir(parents=True)
    write(ref_dir / "case_ts.extxyz", Atoms("H", positions=[[0.0, 0.0, 0.0]]))
    write(root / "candidate.extxyz", Atoms("H", positions=[[1.0, 0.0, 0.0]]))
    _write_json(
        root / "reference_results.json",
        {
            "cases": {
                "case": {
                    "forward_barrier_eV": 1.0,
                    "transition_state_structure": "examples/reference_structures/case_ts.extxyz",
                }
            }
        },
    )
    _write_json(
        root / "singlepoints.json",
        {
            "singlepoints": {
                "initial": {"energy_eV": -10.0},
                "candidate": {"energy_eV": -7.0, "fmax_eV_per_A": 0.20},
            },
            "structures": {"candidate": "candidate.extxyz"},
        },
    )

    report = summarize_abacus_candidate_comparison(
        case_name="case",
        singlepoint_summary=root / "singlepoints.json",
        reference_results=root / "reference_results.json",
        root_dir=root,
        barrier_tolerance_eV=0.1,
        rmsd_threshold_A=0.1,
        fmax_threshold_eV_per_A=0.05,
    )

    assert report["status"] == "fail"
    assert report["validated_abacus_comparison"] is False
    assert report["checks"]["barrier"]["pass"] is False
    assert report["checks"]["rmsd"]["pass"] is False
    assert report["checks"]["fmax"]["pass"] is False
