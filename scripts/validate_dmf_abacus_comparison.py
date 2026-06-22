#!/usr/bin/env python
"""Run or summarize ABACUS single-point comparisons for DMF-D2S candidates."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write
from ruamel.yaml import YAML

from atst_tools.utils.abacus_io import collect_abacus_output, prepare_abacus_input
from atst_tools.utils.dmf_validation import summarize_abacus_candidate_comparison

_FINAL_ENERGY_RE = re.compile(r"!FINAL_ETOT_IS\s+([-+0-9.eE]+)\s+eV")
_FORCE_ROW_RE = re.compile(r"^\s*[A-Za-z]+\d*\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*$")


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a YAML or JSON ABACUS comparison manifest."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


def resolve(path: str | Path, root: Path) -> Path:
    """Resolve a manifest path relative to the repository root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def run_command(command: str, cwd: Path) -> None:
    """Run an ABACUS command in a prepared input directory."""
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
    )
    (cwd / "abacus.stdout").write_text(proc.stdout, encoding="utf-8")
    (cwd / "abacus.stderr").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(
            "ABACUS single-point failed\n"
            f"cwd={cwd}\n"
            f"command={command}\n"
            f"returncode={proc.returncode}\n"
            f"stdout tail:\n{proc.stdout[-4000:]}\n"
            f"stderr tail:\n{proc.stderr[-4000:]}"
        )


def parse_lts_running_log(log: Path) -> dict[str, Any]:
    """Parse final energy and max force from an ABACUS LTS running log."""
    text = log.read_text(encoding="utf-8", errors="replace")
    energy_matches = _FINAL_ENERGY_RE.findall(text)
    if not energy_matches:
        raise ValueError(f"missing !FINAL_ETOT_IS in {log}")
    force_vectors: list[list[float]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "TOTAL-FORCE (eV/Angstrom)" not in line:
            continue
        for row in lines[index + 1 :]:
            if row.strip().startswith("-"):
                if force_vectors:
                    break
                continue
            match = _FORCE_ROW_RE.match(row)
            if match:
                fx, fy, fz = (float(value) for value in match.groups())
                force_vectors.append([fx, fy, fz])
            elif force_vectors and not row.strip():
                break
        break
    if not force_vectors:
        raise ValueError(f"missing TOTAL-FORCE rows in {log}")
    forces = [math.sqrt(fx * fx + fy * fy + fz * fz) for fx, fy, fz in force_vectors]
    return {
        "parsed": True,
        "energy_eV": float(energy_matches[-1]),
        "max_force_eV_per_ang": max(forces),
        "forces_eV_per_ang": force_vectors,
        "parser": "abacus_lts_running_log",
    }


def collect_with_lts_fallback(
    run_dir: Path,
    summary_path: Path,
    collected_structure: Path,
    source_structure: Path,
) -> dict[str, Any]:
    """Collect ABACUS output, falling back to direct LTS log parsing."""
    summary = collect_abacus_output(str(run_dir), str(summary_path), structure=str(collected_structure))
    if summary.get("parsed"):
        return summary
    logs = summary.get("logs", [])
    if not logs:
        return summary
    fallback = parse_lts_running_log(run_dir / logs[-1])
    atoms = read(source_structure)
    forces = fallback["forces_eV_per_ang"]
    if len(atoms) != len(forces):
        raise ValueError(f"force count mismatch for {run_dir}: {len(forces)} != {len(atoms)}")
    atoms.calc = SinglePointCalculator(atoms, energy=fallback["energy_eV"], forces=forces)
    write(collected_structure, atoms)
    summary.update(fallback)
    summary.pop("forces_eV_per_ang", None)
    summary["parse_error"] = None
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def prepare_and_run_structure(
    *,
    config: Path,
    structure: Path,
    run_dir: Path,
    command: str,
) -> dict[str, Any]:
    """Prepare, run, and collect one ABACUS single-point calculation."""
    run_dir.mkdir(parents=True, exist_ok=True)
    prepare_abacus_input(str(config), str(structure), str(run_dir), force=True)
    run_command(command, cwd=run_dir)
    summary_path = run_dir / "abacus_summary.json"
    collected_structure = run_dir / "abacus_final.extxyz"
    summary = collect_with_lts_fallback(run_dir, summary_path, collected_structure, structure)
    if not summary.get("parsed"):
        raise RuntimeError(f"ABACUS output was not parsed for {run_dir}: {summary.get('parse_error')}")
    return {
        "run_dir": str(run_dir),
        "summary": str(summary_path),
        "structure": str(collected_structure),
        "energy_eV": summary["energy_eV"],
        "fmax_eV_per_A": summary["max_force_eV_per_ang"],
    }


def run_case(case: dict[str, Any], *, root: Path, command: str) -> dict[str, Any]:
    """Run initial and candidate ABACUS single-points for one case."""
    config = resolve(case["config"], root)
    output_dir = resolve(case["output_dir"], root)
    structures = {
        "initial": resolve(case["initial_structure"], root),
        "candidate": resolve(case["candidate_structure"], root),
    }
    singlepoints = {}
    for role, structure in structures.items():
        singlepoints[role] = prepare_and_run_structure(
            config=config,
            structure=structure,
            run_dir=output_dir / role,
            command=command,
        )
    summary = {
        "schema_version": "atst-dmf-abacus-singlepoints-v1",
        "case": case["name"],
        "config": str(config),
        "structures": {role: str(path) for role, path in structures.items()},
        "singlepoints": singlepoints,
    }
    summary_path = output_dir / "abacus_singlepoints.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"case": case, "summary_path": summary_path}


def summarize_manifest(
    manifest: dict[str, Any],
    *,
    root: Path,
    output: Path,
    run: bool,
    command: str,
) -> dict[str, Any]:
    """Run and summarize all ABACUS comparison cases."""
    reference_results = resolve(manifest["reference_results"], root)
    barrier_tolerance = float(manifest.get("barrier_tolerance_eV", 0.5))
    rmsd_threshold = float(manifest.get("rmsd_threshold_A", 0.2))
    fmax_threshold = float(manifest.get("fmax_threshold_eV_per_A", 0.1))
    cases = []
    for case in manifest.get("cases", []):
        if run:
            run_result = run_case(case, root=root, command=command)
            singlepoint_summary = run_result["summary_path"]
        else:
            singlepoint_summary = resolve(case["singlepoint_summary"], root)
        cases.append(
            summarize_abacus_candidate_comparison(
                case_name=case["reference_case"],
                singlepoint_summary=singlepoint_summary,
                reference_results=reference_results,
                root_dir=root,
                barrier_tolerance_eV=barrier_tolerance,
                rmsd_threshold_A=rmsd_threshold,
                fmax_threshold_eV_per_A=fmax_threshold,
            )
        )
    passed = bool(cases) and all(case["validated_abacus_comparison"] for case in cases)
    report = {
        "schema_version": "atst-dmf-abacus-comparison-suite-v1",
        "workflow": "dmf_abacus_candidate_comparison_suite",
        "experimental": True,
        "validated_abacus_comparison": passed,
        "status": "pass" if passed else "fail",
        "case_count": len(cases),
        "thresholds": {
            "barrier_tolerance_eV": barrier_tolerance,
            "rmsd_threshold_A": rmsd_threshold,
            "fmax_threshold_eV_per_A": fmax_threshold,
        },
        "cases": cases,
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="YAML/JSON manifest declaring ABACUS comparison cases")
    parser.add_argument("--root", type=Path, default=None, help="Repository root; defaults to manifest parent/../..")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON report path")
    parser.add_argument("--run", action="store_true", help="Prepare and run ABACUS before summarizing")
    parser.add_argument(
        "--command",
        default=" ".join(shlex.quote(part) for part in ["abacus"]),
        help="Shell command used to run ABACUS in each prepared input directory",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    root = args.root.resolve() if args.root else args.manifest.resolve().parents[2]
    output = args.output or args.manifest.with_name("dmf_abacus_comparison_report.json")
    report = summarize_manifest(manifest, root=root, output=output, run=args.run, command=args.command)
    print(json.dumps({"status": report["status"], "case_count": report["case_count"]}, indent=2))


if __name__ == "__main__":
    main()
