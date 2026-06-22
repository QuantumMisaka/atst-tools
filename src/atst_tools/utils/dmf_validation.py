"""Validation helpers for experimental DMF candidate reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from ase.io import read

from atst_tools.utils.summary import energy, max_force

SCHEMA_VERSION = "atst-dmf-validation-v1"


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _resolve(path: str | Path, root_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root_dir / candidate


def cartesian_rmsd(atoms, reference) -> float:
    """Return same-order Cartesian RMSD in Angstrom."""
    if len(atoms) != len(reference):
        raise ValueError(f"atom count mismatch: {len(atoms)} != {len(reference)}")
    delta = atoms.get_positions() - reference.get_positions()
    return float(np.sqrt(np.mean(delta * delta)))


def indexed_cartesian_rmsd(atoms, reference, indices: list[int] | None = None) -> float:
    """Return same-order Cartesian RMSD for a selected atom subset."""
    if len(atoms) != len(reference):
        raise ValueError(f"atom count mismatch: {len(atoms)} != {len(reference)}")
    positions = atoms.get_positions()
    reference_positions = reference.get_positions()
    if indices is not None:
        positions = positions[indices]
        reference_positions = reference_positions[indices]
    delta = positions - reference_positions
    return float(np.sqrt(np.mean(delta * delta)))


def constrained_fmax_from_atoms(atoms) -> float | None:
    """Return ASE constrained max force when force results are available."""
    try:
        forces = atoms.get_forces(apply_constraint=True)
    except Exception:
        return None
    if len(forces) == 0:
        return None
    magnitudes = np.sqrt(np.sum(forces * forces, axis=1))
    return float(np.max(magnitudes))


def summarize_irc_endpoint_connection(
    *,
    case_name: str,
    irc_trajectory: str | Path,
    init_structure: str | Path,
    final_structure: str | Path,
    indices: list[int] | None = None,
    rmsd_threshold: float = 0.25,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize whether two IRC branch endpoints connect to the input endpoints."""
    branches = read(str(irc_trajectory), index=":")
    if len(branches) < 2:
        raise ValueError("IRC endpoint validation requires at least two trajectory frames")
    init_atoms = read(str(init_structure))
    final_atoms = read(str(final_structure))
    if len(init_atoms) != len(final_atoms):
        raise ValueError(f"atom count mismatch: {len(init_atoms)} != {len(final_atoms)}")

    first, second = branches[0], branches[-1]
    direct = (
        indexed_cartesian_rmsd(first, init_atoms, indices),
        indexed_cartesian_rmsd(second, final_atoms, indices),
    )
    swapped = (
        indexed_cartesian_rmsd(second, init_atoms, indices),
        indexed_cartesian_rmsd(first, final_atoms, indices),
    )
    if sum(swapped) < sum(direct):
        assignment = "swapped"
        init_rmsd, final_rmsd = swapped
    else:
        assignment = "direct"
        init_rmsd, final_rmsd = direct
    init_pass = init_rmsd <= rmsd_threshold
    final_pass = final_rmsd <= rmsd_threshold
    report = {
        "schema_version": "atst-dmf-irc-endpoint-v1",
        "case": case_name,
        "workflow": "dmf_irc_endpoint_validation",
        "experimental": True,
        "validated_endpoint_connection": bool(init_pass and final_pass),
        "status": "pass" if init_pass and final_pass else "fail",
        "irc_trajectory": str(irc_trajectory),
        "assignment": assignment,
        "indices": indices,
        "rmsd_threshold_ang": rmsd_threshold,
        "endpoints": {
            "init": {"structure": str(init_structure), "rmsd_ang": init_rmsd, "pass": bool(init_pass)},
            "final": {"structure": str(final_structure), "rmsd_ang": final_rmsd, "pass": bool(final_pass)},
        },
    }
    if output is not None:
        _write_json(output, report)
    return report


def summarize_abacus_candidate_comparison(
    *,
    case_name: str,
    singlepoint_summary: str | Path,
    reference_results: str | Path,
    root_dir: str | Path,
    barrier_tolerance_eV: float = 0.20,
    rmsd_threshold_A: float = 0.20,
    fmax_threshold_eV_per_A: float = 0.10,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Compare a refined DMF-D2S candidate against ABACUS reference evidence."""
    root = Path(root_dir)
    summary = _load_json(singlepoint_summary)
    references = _load_json(reference_results)["cases"]
    if case_name not in references:
        raise KeyError(f"missing reference case: {case_name}")
    reference = references[case_name]
    singlepoints = summary["singlepoints"]
    initial_energy = float(singlepoints["initial"]["energy_eV"])
    candidate_energy = float(singlepoints["candidate"]["energy_eV"])
    candidate_barrier = candidate_energy - initial_energy
    reference_barrier = float(reference["forward_barrier_eV"])
    barrier_delta = candidate_barrier - reference_barrier

    structures = summary.get("structures", {})
    candidate_path = _resolve(structures["candidate"], root)
    force_candidate_path = _resolve(singlepoints["candidate"].get("structure", candidate_path), root)
    reference_ts_path = _resolve(reference["transition_state_structure"], root)
    candidate_atoms = read(candidate_path)
    force_candidate_atoms = read(force_candidate_path)
    reference_ts_atoms = read(reference_ts_path)
    rmsd_to_reference = cartesian_rmsd(candidate_atoms, reference_ts_atoms)
    fmax = singlepoints["candidate"].get("fmax_eV_per_A")
    constrained_fmax = constrained_fmax_from_atoms(force_candidate_atoms)
    fmax_value = constrained_fmax if constrained_fmax is not None else (None if fmax is None else float(fmax))

    barrier_pass = abs(barrier_delta) <= barrier_tolerance_eV
    rmsd_pass = rmsd_to_reference <= rmsd_threshold_A
    fmax_pass = fmax_value is not None and fmax_value <= fmax_threshold_eV_per_A
    passed = bool(barrier_pass and rmsd_pass and fmax_pass)
    report = {
        "schema_version": "atst-dmf-abacus-comparison-v1",
        "case": case_name,
        "workflow": "dmf_abacus_candidate_comparison",
        "experimental": True,
        "validated_abacus_comparison": passed,
        "status": "pass" if passed else "fail",
        "singlepoint_summary": str(singlepoint_summary),
        "candidate": {
            "structure": str(candidate_path),
            "energy_eV": candidate_energy,
            "initial_energy_eV": initial_energy,
            "barrier_eV": candidate_barrier,
            "reference_barrier_eV": reference_barrier,
            "barrier_delta_vs_reference_eV": barrier_delta,
            "rmsd_to_reference_ts_A": rmsd_to_reference,
            "fmax_eV_per_A": fmax_value,
        },
        "reference": {
            "transition_state_structure": str(reference_ts_path),
            "forward_barrier_eV": reference_barrier,
        },
        "checks": {
            "barrier": {
                "value_eV": barrier_delta,
                "abs_value_eV": abs(barrier_delta),
                "threshold_eV": barrier_tolerance_eV,
                "pass": bool(barrier_pass),
            },
            "rmsd": {
                "value_A": rmsd_to_reference,
                "threshold_A": rmsd_threshold_A,
                "pass": bool(rmsd_pass),
            },
            "fmax": {
                "value_eV_per_A": fmax_value,
                "threshold_eV_per_A": fmax_threshold_eV_per_A,
                "pass": bool(fmax_pass),
            },
        },
    }
    if output is not None:
        _write_json(output, report)
    return report


def _abacus_baseline(case: dict[str, Any], root_dir: Path, candidate) -> dict[str, Any]:
    baseline: dict[str, Any] = {}
    if "forward_barrier_eV" in case:
        baseline["barrier_eV"] = case["forward_barrier_eV"]
    if "transition_state_structure" in case and case["transition_state_structure"]:
        path = _resolve(case["transition_state_structure"], root_dir)
        baseline["transition_state_structure"] = str(path)
        baseline["rmsd_to_candidate_ang"] = cartesian_rmsd(candidate, read(path))
    return baseline


def _dp_structure_path(case: dict[str, Any]) -> str | None:
    if "structure" in case and "path" in case["structure"]:
        return f"examples/{case['structure']['path']}"
    structures = case.get("structures", {})
    rough = structures.get("rough_neb") or structures.get("dimer")
    if rough and "path" in rough:
        return f"examples/{rough['path']}"
    return None


def _dp_baseline(case: dict[str, Any] | None, root_dir: Path, candidate) -> dict[str, Any] | None:
    if not case:
        return None
    baseline: dict[str, Any] = {}
    metrics = case.get("metrics", {})
    if "barrier_eV" in metrics:
        baseline["barrier_eV"] = metrics["barrier_eV"]
    comparison = case.get("comparison", {})
    if "delta_vs_abacus_eV" in comparison:
        baseline["delta_vs_abacus_eV"] = comparison["delta_vs_abacus_eV"]
    structure_path = _dp_structure_path(case)
    if structure_path:
        path = _resolve(structure_path, root_dir)
        baseline["transition_state_structure"] = str(path)
        baseline["rmsd_to_candidate_ang"] = cartesian_rmsd(candidate, read(path))
    return baseline


def summarize_dmf_candidate(
    *,
    case_name: str,
    dmf_summary: str | Path,
    dmf_candidate: str | Path,
    reference_results: str | Path,
    root_dir: str | Path,
    dp_reference_results: str | Path | None = None,
) -> dict[str, Any]:
    """Compare one DMF TS candidate with existing ABACUS/DP references.

    The report is intentionally evidence-only: it records candidate comparison
    metrics but keeps ``validated_ts`` false because DMF output still requires
    downstream refinement and vibration/IRC validation.
    """
    root = Path(root_dir)
    summary = _load_json(dmf_summary)
    candidate = read(str(dmf_candidate))
    references = _load_json(reference_results)["cases"]
    if case_name not in references:
        raise KeyError(f"missing reference case: {case_name}")

    dp_case = None
    if dp_reference_results is not None:
        dp_case = _load_json(dp_reference_results).get("cases", {}).get(case_name)

    abacus = _abacus_baseline(references[case_name], root, candidate)
    dp = _dp_baseline(dp_case, root, candidate)
    candidate_metrics = {
        "path": str(dmf_candidate),
        "energy_eV": energy(candidate),
        "max_force_eV_per_A": max_force(candidate),
    }
    if "rmsd_to_candidate_ang" in abacus:
        candidate_metrics["rmsd_to_abacus_ts_ang"] = abacus["rmsd_to_candidate_ang"]
    if dp and "rmsd_to_candidate_ang" in dp:
        candidate_metrics["rmsd_to_dp_ts_ang"] = dp["rmsd_to_candidate_ang"]

    return {
        "schema_version": SCHEMA_VERSION,
        "case": case_name,
        "workflow": "dmf_validation",
        "experimental": True,
        "result_type": summary.get("result_type", "ts_candidate"),
        "validated_ts": False,
        "status": "candidate_compared",
        "dmf": {
            "summary": str(dmf_summary),
            "tmax": summary.get("tmax"),
            "n_images": summary.get("n_images"),
            "initial_path": summary.get("initial_path"),
            "pbc_mode": summary.get("pbc_mode"),
            "ipopt_status": summary.get("ipopt_status"),
        },
        "candidate": candidate_metrics,
        "baselines": {
            "abacus": {key: value for key, value in abacus.items() if key != "rmsd_to_candidate_ang"},
            "dp": None if dp is None else {key: value for key, value in dp.items() if key != "rmsd_to_candidate_ang"},
        },
    }


def summarize_manifest(
    manifest: dict[str, Any],
    *,
    root_dir: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize all DMF validation cases declared by a manifest."""
    root = Path(root_dir)
    reference_results = _resolve(manifest["reference_results"], root)
    dp_reference = manifest.get("dp_reference_results")
    dp_reference_path = _resolve(dp_reference, root) if dp_reference else None
    cases = [
        summarize_dmf_candidate(
            case_name=case["name"],
            dmf_summary=_resolve(case["dmf_summary"], root),
            dmf_candidate=_resolve(case["dmf_candidate"], root),
            reference_results=reference_results,
            dp_reference_results=dp_reference_path,
            root_dir=root,
        )
        for case in manifest.get("cases", [])
    ]
    status = "candidate_compared" if cases else "no_cases"
    report = {
        "schema_version": "atst-dmf-validation-suite-v1",
        "workflow": "dmf_validation_suite",
        "experimental": True,
        "validated_ts": False,
        "status": status,
        "case_count": len(cases),
        "cases": cases,
    }
    if output is not None:
        _write_json(output, report)
    return report
