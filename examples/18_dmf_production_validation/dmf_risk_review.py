#!/usr/bin/env python
"""Prepare and summarize DMF risk-review cases for example 18."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read, write
from ruamel.yaml import YAML

from atst_tools.utils.config_schema import parse_config


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
RISK_ROOT = ROOT / "risk_cases"
REPORT_PATH = ROOT / "dmf_risk_case_report.json"
PATH_LENGTH_RATIO_THRESHOLD = 2.0
TMAX_GAP_THRESHOLD_A = 0.05
FIXED_DISPLACEMENT_THRESHOLD_A = 1.0e-3


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def same_order_rmsd(atoms: Atoms, reference: Atoms, indices: list[int] | None = None) -> float:
    """Return same-order Cartesian RMSD in Angstrom."""
    positions = atoms.get_positions()
    reference_positions = reference.get_positions()
    if indices is not None:
        positions = positions[indices]
        reference_positions = reference_positions[indices]
    delta = positions - reference_positions
    return float(np.sqrt(np.mean(np.sum(delta * delta, axis=1))))


def path_length(images: list[Atoms]) -> float:
    """Return cumulative same-order Cartesian path length in Angstrom."""
    if len(images) < 2:
        return 0.0
    total = 0.0
    for before, after in zip(images[:-1], images[1:]):
        delta = after.get_positions() - before.get_positions()
        total += float(np.sqrt(np.sum(delta * delta)))
    return total


def path_length_metrics(images: list[Atoms], baseline_images: list[Atoms] | None = None) -> dict[str, Any]:
    """Summarize path length and optional ratio to a baseline path."""
    length = path_length(images)
    baseline_length = path_length(baseline_images) if baseline_images else None
    ratio = None
    if baseline_length is not None and baseline_length > 0.0:
        ratio = length / baseline_length
    return {
        "path_length_A": length,
        "baseline_path_length_A": baseline_length,
        "path_length_ratio": ratio,
        "ratio_threshold": PATH_LENGTH_RATIO_THRESHOLD,
        "ratio_exceeds_threshold": bool(ratio is not None and ratio >= PATH_LENGTH_RATIO_THRESHOLD),
    }


def _fixed_indices(atoms: Atoms) -> list[int]:
    indices: list[int] = []
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            indices.extend(int(index) for index in constraint.index)
    return sorted(set(indices))


def max_fixed_atom_displacement(initial: Atoms, final: Atoms) -> float | None:
    """Return max displacement for atoms fixed by constraints on the initial structure."""
    indices = _fixed_indices(initial)
    if not indices:
        return None
    delta = final.get_positions()[indices] - initial.get_positions()[indices]
    return float(np.sqrt(np.sum(delta * delta, axis=1)).max())


def tmax_index_gap_metrics(images: list[Atoms], candidate: Atoms, tmax: float | None) -> dict[str, Any]:
    """Compare the continuous DMF candidate with the rounded image index used by follow-up tools."""
    if tmax is None or not images:
        return {
            "tmax": tmax,
            "rounded_index": None,
            "candidate_vs_rounded_rmsd_A": None,
            "threshold_A": TMAX_GAP_THRESHOLD_A,
            "exceeds_threshold": False,
        }
    index = int(round(float(tmax) * max(len(images) - 1, 0)))
    index = min(max(index, 0), len(images) - 1)
    rmsd = same_order_rmsd(candidate, images[index])
    return {
        "tmax": float(tmax),
        "rounded_index": index,
        "candidate_vs_rounded_rmsd_A": rmsd,
        "threshold_A": TMAX_GAP_THRESHOLD_A,
        "exceeds_threshold": bool(rmsd > TMAX_GAP_THRESHOLD_A),
    }


def _yaml() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    return _yaml().load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        _yaml().dump(payload, handle)


def _copy_with_mutation(source: Path, target: Path, mutation) -> None:
    atoms = read(source)
    mutation(atoms)
    target.parent.mkdir(parents=True, exist_ok=True)
    write(target, atoms)


def _case_config(base_config: Path, case_name: str, init_file: Path, final_file: Path, *, initial_path: str | None = None) -> Path:
    config = _load_yaml(base_config)
    calc = config["calculation"]
    case_dir = RISK_ROOT / case_name
    calc["init_file"] = str(init_file.relative_to(ROOT))
    calc["final_file"] = str(final_file.relative_to(ROOT))
    calc["directory"] = str((case_dir / "dmf_run").relative_to(ROOT))
    calc["trajectory"] = str((case_dir / "dmf_path.traj").relative_to(ROOT))
    calc["tmax_trajectory"] = str((case_dir / "dmf_tmax.traj").relative_to(ROOT))
    calc["summary_file"] = str((case_dir / "dmf_summary.json").relative_to(ROOT))
    calc["artifact_manifest"] = str((case_dir / "atst_artifacts.json").relative_to(ROOT))
    calc.setdefault("ipopt_options", {})["max_iter"] = 80
    calc.setdefault("ipopt_options", {})["print_level"] = 0
    if initial_path is not None:
        calc["initial_path"] = initial_path
    output = case_dir / "config.yaml"
    _write_yaml(output, config)
    return output


def prepare_cases() -> dict[str, Any]:
    """Create mutated inputs and YAML configs for the DP risk-review Slurm job."""
    RISK_ROOT.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []

    h2_init_src = ROOT / "inputs" / "02_neb_H2-Au_init.extxyz"
    h2_final_src = ROOT / "inputs" / "02_neb_H2-Au_final.extxyz"
    li_init_src = ROOT / "inputs" / "01_neb_Li-Si_init.extxyz"
    li_final_src = ROOT / "inputs" / "01_neb_Li-Si_final.extxyz"

    def add_case(name: str, base_config: Path, init_src: Path, final_src: Path, mutation, *, initial_path: str | None = None, baseline: str):
        case_dir = RISK_ROOT / name
        init_file = case_dir / "inputs" / "init.extxyz"
        final_file = case_dir / "inputs" / "final.extxyz"
        init_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(init_src, init_file)
        _copy_with_mutation(final_src, final_file, mutation)
        config = _case_config(base_config, name, init_file, final_file, initial_path=initial_path)
        cases.append(
            {
                "name": name,
                "config": str(config.relative_to(ROOT)),
                "init": str(init_file.relative_to(ROOT)),
                "final": str(final_file.relative_to(ROOT)),
                "summary": str((case_dir / "dmf_summary.json").relative_to(ROOT)),
                "path": str((case_dir / "dmf_path.traj").relative_to(ROOT)),
                "candidate": str((case_dir / "dmf_tmax.traj").relative_to(ROOT)),
                "run_status": str((case_dir / "run_status.json").relative_to(ROOT)),
                "baseline_path": baseline,
            }
        )

    add_case(
        "H2-Au_wrapped_final_image",
        ROOT / "config_02_H2-Au_dmf_dp.yaml",
        h2_init_src,
        h2_final_src,
        lambda atoms: atoms.positions.__setitem__(0, atoms.positions[0] + atoms.cell.array[0]),
        baseline="runs/02_neb_H2-Au/dmf_path.traj",
    )
    add_case(
        "H2-Au_swapped_H_indices",
        ROOT / "config_02_H2-Au_dmf_dp.yaml",
        h2_init_src,
        h2_final_src,
        lambda atoms: atoms.positions.__setitem__([0, 1], atoms.positions[[1, 0]]),
        baseline="runs/02_neb_H2-Au/dmf_path.traj",
    )
    add_case(
        "H2-Au_inconsistent_fixed_slab",
        ROOT / "config_02_H2-Au_dmf_dp.yaml",
        h2_init_src,
        h2_final_src,
        lambda atoms: atoms.positions.__setitem__(2, atoms.positions[2] + np.array([0.10, 0.0, 0.0])),
        baseline="runs/02_neb_H2-Au/dmf_path.traj",
    )
    add_case(
        "Li-Si_pbc_cfbenm",
        ROOT / "config_01_Li-Si_dmf_dp.yaml",
        li_init_src,
        li_final_src,
        lambda atoms: None,
        initial_path="cfbenm",
        baseline="runs/01_neb_Li-Si/dmf_path.traj",
    )

    manifest = {"schema_version": "atst-dmf-risk-cases-v1", "cases": cases}
    (RISK_ROOT / "risk_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    """Analyze one risk case after DMF has run."""
    summary_path = ROOT / case["summary"]
    path_path = ROOT / case["path"]
    candidate_path = ROOT / case["candidate"]
    result: dict[str, Any] = {
        "name": case["name"],
        "status": "not_run",
        "risk_confirmed": False,
        "checks": {},
    }
    if not (summary_path.exists() and path_path.exists() and candidate_path.exists()):
        status_path = ROOT / case["run_status"] if case.get("run_status") else None
        if status_path and status_path.exists():
            run_status = json.loads(status_path.read_text(encoding="utf-8"))
            status = run_status.get("status", "failed")
            result["status"] = status
            result["run_status"] = run_status
            result["risk_confirmed"] = status in {"timeout", "failed"}
            result["checks"]["runtime_completion"] = {
                "pass": False,
                "status": status,
                "exit_code": run_status.get("exit_code"),
                "elapsed_seconds": run_status.get("elapsed_seconds"),
                "reason": "DMF risk case did not produce complete summary/path/candidate artifacts.",
            }
            return result
        config = _load_yaml(ROOT / case["config"])
        calc = config["calculation"]
        if calc.get("pbc_mode") == "cartesian_unwrapped" and calc.get("initial_path") in {"fbenm", "cfbenm"}:
            try:
                parse_config(config)
            except Exception as exc:
                result["status"] = "guard_covered"
                result["risk_confirmed"] = False
                result["checks"]["pbc_fbenm_guard"] = {
                    "pass": True,
                    "reason": str(exc),
                }
                return result
            result["status"] = "guard_missing"
            result["risk_confirmed"] = True
            result["checks"]["pbc_fbenm_guard"] = {
                "pass": False,
                "reason": "PBC cartesian_unwrapped config accepted FBENM/CFBENM.",
            }
        return result

    init_path = ROOT / case["init"]
    final_path = ROOT / case["final"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    images = read(path_path, index=":")
    candidate = read(candidate_path)
    baseline_images = read(ROOT / case["baseline_path"], index=":") if case.get("baseline_path") else None
    init_atoms = read(init_path)
    final_atoms = read(final_path)

    path_metrics = path_length_metrics(images, baseline_images)
    tmax_metrics = tmax_index_gap_metrics(images, candidate, summary.get("tmax"))
    fixed_displacement = max_fixed_atom_displacement(init_atoms, final_atoms)
    fixed_displacement_exceeds = bool(
        fixed_displacement is not None and fixed_displacement > FIXED_DISPLACEMENT_THRESHOLD_A
    )
    config = _load_yaml(ROOT / case["config"])
    calc = config["calculation"]
    pbc_fbenm_guard_missing = bool(
        calc.get("pbc_mode") == "cartesian_unwrapped" and calc.get("initial_path") in {"fbenm", "cfbenm"}
    )

    result.update(
        {
            "status": "analyzed",
            "summary": case["summary"],
            "path": case["path"],
            "candidate": case["candidate"],
            "tmax_candidate": summary.get("tmax_candidate", {}),
            "checks": {
                "path_length": path_metrics,
                "tmax_index_gap": tmax_metrics,
                "fixed_atom_displacement": {
                    "max_displacement_A": fixed_displacement,
                    "threshold_A": FIXED_DISPLACEMENT_THRESHOLD_A,
                    "exceeds_threshold": fixed_displacement_exceeds,
                },
                "pbc_fbenm_guard": {
                    "guard_missing": pbc_fbenm_guard_missing,
                    "initial_path": calc.get("initial_path"),
                    "pbc_mode": calc.get("pbc_mode"),
                },
            },
        }
    )
    result["risk_confirmed"] = bool(
        path_metrics["ratio_exceeds_threshold"]
        or tmax_metrics["exceeds_threshold"]
        or fixed_displacement_exceeds
        or pbc_fbenm_guard_missing
    )
    return result


def analyze_existing_tmax_gap() -> dict[str, Any]:
    """Analyze tmax-to-rounded-image gap for existing successful DMF outputs."""
    cases = []
    for name, source in {
        "Li-Si_d2s_dmf_vib": ROOT / "runs" / "05_Li-Si_d2s_dmf_vib",
        "H2-Au_d2s_dmf_vib": ROOT / "runs" / "06_H2-Au_d2s_dmf_vib",
    }.items():
        summary_path = source / "dmf_summary.json"
        path_path = source / "dmf_path.traj"
        candidate_path = source / "dmf_tmax.traj"
        if not (summary_path.exists() and path_path.exists() and candidate_path.exists()):
            cases.append({"name": name, "status": "missing"})
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = tmax_index_gap_metrics(read(path_path, index=":"), read(candidate_path), summary.get("tmax"))
        cases.append({"name": name, "status": "analyzed", **metrics})
    return {
        "name": "existing_tmax_index_gap",
        "status": "analyzed",
        "risk_confirmed": any(case.get("exceeds_threshold", False) for case in cases),
        "cases": cases,
    }


def mark_run_status(case_name: str, status: str, exit_code: int, elapsed_seconds: int) -> dict[str, Any]:
    """Write per-case runtime status for Slurm risk-review jobs."""
    payload = {
        "status": status,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed_seconds,
    }
    output = RISK_ROOT / case_name / "run_status.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def summarize_cases(manifest_path: Path = RISK_ROOT / "risk_manifest.json", output: Path = REPORT_PATH) -> dict[str, Any]:
    """Write the risk-case report JSON."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = [analyze_case(case) for case in manifest["cases"]]
    existing = analyze_existing_tmax_gap()
    report = {
        "schema_version": "atst-dmf-risk-review-v1",
        "workflow": "dmf_risk_review",
        "experimental": True,
        "case_count": len(cases),
        "risk_confirmed_count": sum(1 for case in cases if case["risk_confirmed"]) + int(existing["risk_confirmed"]),
        "cases": cases,
        "existing_evidence": [existing],
    }
    output.write_text(json.dumps(_json_ready(report), indent=2), encoding="utf-8")
    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["prepare", "summarize", "mark-run-status"],
        help="Prepare inputs/configs, record one run status, or summarize results.",
    )
    parser.add_argument("--manifest", type=Path, default=RISK_ROOT / "risk_manifest.json")
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    parser.add_argument("--case", help="Risk case name for mark-run-status.")
    parser.add_argument("--status", choices=["completed", "failed", "timeout"], help="Runtime status.")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--elapsed-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.action == "prepare":
        payload = prepare_cases()
    elif args.action == "mark-run-status":
        if not args.case or not args.status:
            parser.error("mark-run-status requires --case and --status")
        payload = mark_run_status(args.case, args.status, args.exit_code, args.elapsed_seconds)
    else:
        payload = summarize_cases(args.manifest, args.output)
    print(json.dumps(_json_ready(payload), indent=2))


if __name__ == "__main__":
    main()
