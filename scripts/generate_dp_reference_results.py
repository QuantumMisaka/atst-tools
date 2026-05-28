"""Generate curated DP calculator reference results for examples."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from ase.io import read, write


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "validation_runs" / "dpa3_examples_20260528_current"
AUTO = (
    ROOT
    / "validation_runs"
    / "dpa3_examples_20260528_current_fix_autoneb_freeze"
    / "03_autoneb_Cy-Pt"
)
OUT_STRUCT = ROOT / "examples" / "dp_reference_structures"
MODEL_MANIFEST = ROOT / "examples" / "dp_model_manifest.json"
MODEL_NAME = "DPA-3.1-3M"


def load_json(path: Path) -> dict:
    """Load a JSON document from disk."""
    return json.loads(path.read_text())


def latest_band(path: Path, n_images: int) -> list:
    """Return the latest complete NEB band from a trajectory."""
    frames = read(path, ":")
    return frames[-n_images:]


def latest(path: Path):
    """Return the final structure from a trajectory."""
    return read(path, index=-1)


def rmsd(atoms, reference) -> float:
    """Compute Cartesian RMSD for same-order structures."""
    if len(atoms) != len(reference):
        raise ValueError(f"atom count mismatch: {len(atoms)} != {len(reference)}")
    return float(np.sqrt(np.mean((atoms.positions - reference.positions) ** 2)))


def ensure_finite(obj):
    """Fail if a nested result object contains non-finite floats."""
    if isinstance(obj, dict):
        for value in obj.values():
            ensure_finite(value)
    elif isinstance(obj, list):
        for value in obj:
            ensure_finite(value)
    elif isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("non-finite float in DP reference results")


def write_structure(case: str, atoms, filename: str, reference: str | None = None) -> dict:
    """Write a curated DP structure and optionally compare with ABACUS."""
    target = OUT_STRUCT / filename
    write(target, atoms, format="extxyz")
    entry = {"path": f"dp_reference_structures/{filename}"}
    if reference:
        ref_path = ROOT / "examples" / "reference_structures" / reference
        entry["abacus_reference"] = f"reference_structures/{reference}"
        entry["rmsd_to_abacus_ang"] = rmsd(atoms, read(ref_path))
    return entry


def load_model_metadata() -> dict:
    """Load the pinned model metadata used by DP examples."""
    return load_json(MODEL_MANIFEST)["models"][MODEL_NAME]


def main() -> None:
    """Build examples/dp_reference_results.json from validation outputs."""
    OUT_STRUCT.mkdir(parents=True, exist_ok=True)
    abacus = load_json(ROOT / "examples" / "reference_results.json")["cases"]
    model_metadata = load_model_metadata()
    model_path = ROOT / model_metadata["local_path"]
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if model_sha256 != model_metadata["sha256"]:
        raise ValueError(f"model checksum does not match manifest: {model_path}")

    neb01 = load_json(BASE / "01_neb_Li-Si" / "neb_summary.json")
    neb02 = load_json(BASE / "02_neb_H2-Au" / "neb_summary.json")
    auto03 = load_json(AUTO / "autoneb_summary.json")
    dimer04 = load_json(BASE / "04_dimer_CO-Pt" / "dimer_summary.json")
    sella05 = load_json(BASE / "05_sella_H2-Au" / "sella_summary.json")
    relax06 = load_json(BASE / "06_relax_H2-Au" / "relax_summary.json")
    vib07 = load_json(BASE / "07_vibration_H2-Au" / "vibration_summary.json")
    d2s08 = load_json(BASE / "08_d2s_Cy-Pt" / "d2s_summary.json")
    irc10 = load_json(BASE / "10_irc_H2" / "irc_traj_summary.json")
    vib11 = load_json(BASE / "11_vibration_ideal_gas_H2" / "vibration_summary.json")
    neb01_status, neb01_latest = neb01["status"], neb01["latest"]
    neb02_status, neb02_latest = neb02["status"], neb02["latest"]
    auto03_status, auto03_latest = auto03["status"], auto03["latest"]
    rough_stage = d2s08["stages"]["rough_neb"]
    rough_status, rough_latest = rough_stage["summary_status"], rough_stage["latest"]

    structures = {
        "01_neb_Li-Si": write_structure(
            "01_neb_Li-Si",
            latest_band(BASE / "01_neb_Li-Si" / "neb.traj", neb01_status["n_images"])[
                neb01_latest["ts_image"]
            ],
            "01_neb_Li-Si_dp_ts.extxyz",
            "01_neb_Li-Si_ts.extxyz",
        ),
        "02_neb_H2-Au": write_structure(
            "02_neb_H2-Au",
            latest_band(BASE / "02_neb_H2-Au" / "neb.traj", neb02_status["n_images"])[
                neb02_latest["ts_image"]
            ],
            "02_neb_H2-Au_dp_ts.extxyz",
            "02_neb_H2-Au_ts.extxyz",
        ),
        "03_autoneb_Cy-Pt": write_structure(
            "03_autoneb_Cy-Pt",
            read(AUTO / f"run_autoneb{auto03_latest['ts_image']:03d}.traj", index=-1),
            "03_autoneb_Cy-Pt_dp_ts.extxyz",
            "03_autoneb_Cy-Pt_ts.extxyz",
        ),
        "04_dimer_CO-Pt": write_structure(
            "04_dimer_CO-Pt",
            latest(BASE / "04_dimer_CO-Pt" / "dimer.traj"),
            "04_dimer_CO-Pt_dp_final_ts.extxyz",
            "04_dimer_CO-Pt_final_ts.extxyz",
        ),
        "05_sella_H2-Au": write_structure(
            "05_sella_H2-Au",
            latest(BASE / "05_sella_H2-Au" / "sella.traj"),
            "05_sella_H2-Au_dp_final_ts.extxyz",
            "05_sella_H2-Au_final_ts.extxyz",
        ),
        "06_relax_H2-Au": write_structure(
            "06_relax_H2-Au",
            latest(BASE / "06_relax_H2-Au" / "relax.traj"),
            "06_relax_H2-Au_dp_relaxed.extxyz",
        ),
    }
    rough_band = latest_band(
        BASE / "08_d2s_Cy-Pt" / "neb_rough.traj", rough_status["n_images"]
    )
    structures["08_d2s_Cy-Pt.rough_neb"] = write_structure(
        "08_d2s_Cy-Pt.rough_neb",
        rough_band[rough_latest["ts_image"]],
        "08_d2s_Cy-Pt_dp_rough_ts.extxyz",
        "08_d2s_Cy-Pt_rough_ts.extxyz",
    )
    structures["08_d2s_Cy-Pt.dimer"] = write_structure(
        "08_d2s_Cy-Pt.dimer",
        latest(BASE / "08_d2s_Cy-Pt" / "dimer.traj"),
        "08_d2s_Cy-Pt_dp_dimer_ts.extxyz",
    )

    def barrier_diff(case: str, barrier: float) -> dict:
        ref = abacus[case]["forward_barrier_eV"]
        return {
            "abacus_barrier_eV": ref,
            "delta_vs_abacus_eV": float(barrier - ref),
        }

    results = {
        "schema_version": 1,
        "generated_at": "2026-05-28T00:00:00+08:00",
        "validation_run": {
            "platform": "SAI Slurm GPU nodes",
            "partition": "4V100PX",
            "qos": "flood-1o2gpu",
            "source": "current checkout via PYTHONPATH=src",
            "model_path": model_metadata["local_path"],
            "model_sha256": model_sha256,
            "model_url": model_metadata["url"],
            "dp_head": model_metadata["dp_head"],
            "deepmd_kit": "3.1.2",
            "atst": "2.0.0+current-source",
            "job_ids": [
                "461555",
                "461556",
                "461558",
                "461559",
                "461560",
                "461561",
                "461562",
                "461563",
                "461564",
                "461654",
            ],
        },
        "model_recommendation": {
            "decision": "keep_as_external_validation_asset",
            "git_policy": (
                "Do not add the 45 MiB checkpoint directly to normal git; use Git LFS "
                "or an artifact store if it must be versioned."
            ),
            "rationale": (
                "The model executes every DP-backed example and gives reasonable "
                "workflow-level references, but several transition-state searches "
                "remain not strictly converged or differ materially from ABACUS."
            ),
        },
        "cases": {},
    }
    cases = results["cases"]
    cases["01_neb_Li-Si"] = {
        "status": "green",
        "workflow": "neb",
        "slurm_job_id": "461555",
        "metrics": {
            "barrier_eV": neb01_latest["barrier_eV"],
            "ts_image": neb01_latest["ts_image"],
            "projected_neb_fmax_eV_per_ang": neb01_latest[
                "projected_neb_fmax_eV_per_A"
            ],
            "max_force_eV_per_ang": neb01_latest["max_force_eV_per_A"],
            "n_images": neb01_status["n_images"],
            "complete_steps": neb01_status["complete_steps"],
        },
        "comparison": barrier_diff("01_neb_Li-Si", neb01_latest["barrier_eV"])
        | {"ts_rmsd_to_abacus_ang": structures["01_neb_Li-Si"]["rmsd_to_abacus_ang"]},
        "structure": structures["01_neb_Li-Si"],
        "notes": (
            "Converged by projected NEB fmax; endpoints were recomputed with DP via "
            "endpoint_singlepoint: always."
        ),
    }
    cases["02_neb_H2-Au"] = {
        "status": "yellow",
        "workflow": "neb",
        "slurm_job_id": "461556",
        "metrics": {
            "barrier_eV": neb02_latest["barrier_eV"],
            "ts_image": neb02_latest["ts_image"],
            "projected_neb_fmax_eV_per_ang": neb02_latest[
                "projected_neb_fmax_eV_per_A"
            ],
            "max_force_eV_per_ang": neb02_latest["max_force_eV_per_A"],
            "n_images": neb02_status["n_images"],
            "complete_steps": neb02_status["complete_steps"],
        },
        "comparison": barrier_diff("02_neb_H2-Au", neb02_latest["barrier_eV"])
        | {"ts_rmsd_to_abacus_ang": structures["02_neb_H2-Au"]["rmsd_to_abacus_ang"]},
        "structure": structures["02_neb_H2-Au"],
        "notes": (
            "Barrier is within the pragmatic 0.5 eV envelope, but the max-step run "
            "stopped slightly above the 0.05 eV/Ang projected fmax target."
        ),
    }
    cases["03_autoneb_Cy-Pt"] = {
        "status": "yellow",
        "workflow": "autoneb",
        "slurm_job_id": "461654",
        "metrics": {
            "barrier_eV": auto03_latest["barrier_eV"],
            "ts_image": auto03_latest["ts_image"],
            "projected_neb_fmax_eV_per_ang": auto03_latest[
                "projected_neb_fmax_eV_per_A"
            ],
            "max_force_eV_per_ang": auto03_latest["max_force_eV_per_A"],
            "n_images": auto03_status["n_images"],
        },
        "comparison": barrier_diff("03_autoneb_Cy-Pt", auto03_latest["barrier_eV"])
        | {"ts_rmsd_to_abacus_ang": structures["03_autoneb_Cy-Pt"]["rmsd_to_abacus_ang"]},
        "structure": structures["03_autoneb_Cy-Pt"],
        "notes": (
            "Barrier matches ABACUS closely, while final image forces show this AutoNEB "
            "run is not a strict converged TS search."
        ),
    }
    cases["04_dimer_CO-Pt"] = {
        "status": "green",
        "workflow": "dimer",
        "slurm_job_id": "461558",
        "metrics": {
            "latest_energy_eV": dimer04["latest"]["energy_eV"],
            "max_force_eV_per_ang": dimer04["latest"]["max_force_eV_per_A"],
            "n_frames": dimer04["status"]["n_frames"],
        },
        "comparison": {
            "ts_rmsd_to_abacus_ang": structures["04_dimer_CO-Pt"][
                "rmsd_to_abacus_ang"
            ]
        },
        "structure": structures["04_dimer_CO-Pt"],
    }
    cases["05_sella_H2-Au"] = {
        "status": "green",
        "workflow": "sella",
        "slurm_job_id": "461559",
        "metrics": {
            "latest_energy_eV": sella05["latest"]["energy_eV"],
            "max_force_eV_per_ang": sella05["latest"]["max_force_eV_per_A"],
            "n_frames": sella05["status"]["n_frames"],
        },
        "comparison": {
            "ts_rmsd_to_abacus_ang": structures["05_sella_H2-Au"][
                "rmsd_to_abacus_ang"
            ]
        },
        "structure": structures["05_sella_H2-Au"],
    }
    cases["06_relax_H2-Au"] = {
        "status": "green",
        "workflow": "relax",
        "slurm_job_id": "461560",
        "metrics": {
            "latest_energy_eV": relax06["latest"]["energy_eV"],
            "max_force_eV_per_ang": relax06["latest"]["max_force_eV_per_A"],
            "n_frames": relax06["status"]["n_frames"],
        },
        "structure": structures["06_relax_H2-Au"],
    }
    cases["07_vibration_H2-Au"] = {
        "status": "green",
        "workflow": "vibration",
        "slurm_job_id": "461561",
        "metrics": {
            "valid_cache_files": len(vib07["status"]["valid_cache_files"]),
            "invalid_cache_files": len(vib07["status"]["invalid_cache_files"]),
            "n_frequencies": vib07["latest"]["n_frequencies"],
            "n_imaginary_modes": vib07["latest"]["n_imaginary_modes"],
            "zpe_eV": vib07["latest"]["thermo"]["zpe"],
            "helmholtz_free_energy_eV": vib07["latest"]["thermo"][
                "helmholtz_free_energy"
            ],
        },
    }
    cases["08_d2s_Cy-Pt"] = {
        "status": "yellow",
        "workflow": "d2s",
        "slurm_job_id": "461562",
        "metrics": {
            "complete": d2s08["status"]["complete"],
            "method": d2s08["status"]["method"],
            "rough_barrier_eV": rough_latest["barrier_eV"],
            "rough_ts_image": rough_latest["ts_image"],
            "rough_projected_neb_fmax_eV_per_ang": rough_latest[
                "projected_neb_fmax_eV_per_A"
            ],
            "dimer_energy_eV": d2s08["latest"]["energy_eV"],
            "dimer_max_force_eV_per_ang": d2s08["latest"]["max_force_eV_per_A"],
        },
        "comparison": {
            "abacus_rough_barrier_eV": abacus["08_d2s_Cy-Pt"][
                "forward_barrier_eV"
            ],
            "rough_delta_vs_abacus_eV": float(
                rough_latest["barrier_eV"]
                - abacus["08_d2s_Cy-Pt"]["forward_barrier_eV"]
            ),
            "rough_ts_rmsd_to_abacus_ang": structures[
                "08_d2s_Cy-Pt.rough_neb"
            ]["rmsd_to_abacus_ang"],
        },
        "structures": {
            "rough_neb": structures["08_d2s_Cy-Pt.rough_neb"],
            "dimer": structures["08_d2s_Cy-Pt.dimer"],
        },
        "notes": (
            "Workflow completed, but rough NEB differs from ABACUS by more than the "
            "tighter barrier envelope and the final dimer force is slightly above "
            "0.05 eV/Ang."
        ),
    }
    cases["10_irc_H2"] = {
        "status": "green",
        "workflow": "irc",
        "slurm_job_id": "461563",
        "metrics": {
            "n_frames": irc10["status"]["n_frames"],
            "latest_energy_eV": irc10["latest"]["energy_eV"],
            "latest_max_force_eV_per_ang": irc10["latest"]["max_force_eV_per_A"],
        },
    }
    cases["11_vibration_ideal_gas_H2"] = {
        "status": "yellow",
        "workflow": "vibration_ideal_gas",
        "slurm_job_id": "461564",
        "metrics": {
            "n_frequencies": vib11["latest"]["n_frequencies"],
            "n_imaginary_modes": vib11["latest"]["n_imaginary_modes"],
            "zpe_eV": vib11["latest"]["thermo"]["zpe"],
            "enthalpy_eV": vib11["latest"]["thermo"]["enthalpy"],
            "gibbs_free_energy_eV": vib11["latest"]["thermo"]["gibbs_free_energy"],
            "n_valid_modes": vib11["latest"]["thermo"]["n_valid_modes"],
            "n_filtered_modes": vib11["latest"]["thermo"]["n_filtered_modes"],
        },
        "notes": (
            "Exercises the IdealGasThermo post-processing path; most modes are filtered "
            "because this is a minimal H2 fixture."
        ),
    }

    ensure_finite(results)
    target = ROOT / "examples" / "dp_reference_results.json"
    target.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"wrote {target.relative_to(ROOT)}")
    for path in sorted(OUT_STRUCT.glob("*.extxyz")):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
