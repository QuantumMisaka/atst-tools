"""Read-only summaries for ATST workflow outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from ase.io import read
from ase.mep.neb import NEBTools

from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.restart_helpers import check_cache_files, read_autoneb_final_chain

SCHEMA_VERSION = "atst-summary-v1"


def max_force(atoms) -> float:
    """Return the largest atomic force norm for an ASE Atoms object."""
    try:
        forces = atoms.get_forces()
    except Exception:
        return float("nan")
    if len(forces) == 0:
        return 0.0
    return float(np.linalg.norm(forces, axis=1).max())


def energy(atoms) -> float:
    """Return potential energy, recovering from Atoms.info when possible."""
    try:
        return float(atoms.get_potential_energy())
    except Exception:
        if "energy" in atoms.info:
            return float(atoms.info["energy"])
        return float("nan")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def write_summary_json(summary: dict[str, Any], output: str | Path) -> None:
    """Write a summary dictionary as stable JSON."""
    Path(output).write_text(json.dumps(_jsonable(summary), indent=2), encoding="utf-8")


def _resolve_output_path(path: str | Path, base_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    candidates = [candidate, base_dir / candidate, base_dir.parent / candidate]
    for item in candidates:
        if item.exists():
            return item
    return candidates[1]


def _resolve_n_images(images: Sequence, n_max: int) -> int:
    if n_max < 0:
        raise ValueError("n_max must be a non-negative integer")
    if n_max > 0:
        return n_max + 2
    try:
        return int(NEBTools(list(images))._guess_nimages())
    except Exception:
        return len(images)


def _neb_step_summary(group: Sequence, step: int) -> dict[str, Any]:
    energies = [energy(atoms) for atoms in group]
    fmaxes = [max_force(atoms) for atoms in group]
    e0 = energies[0] if energies else float("nan")
    rel_energies = [value - e0 for value in energies]
    internal = fmaxes[1:-1]
    if internal and not all(np.isnan(internal)):
        max_force_image = int(np.nanargmax(internal)) + 1
    elif fmaxes:
        max_force_image = int(np.nanargmax(fmaxes))
    else:
        max_force_image = -1
    ts_image = int(np.nanargmax(energies)) if energies else -1
    barrier = float(energies[ts_image] - e0) if ts_image >= 0 else float("nan")
    delta_e = float(energies[-1] - e0) if energies else float("nan")
    return {
        "step": step,
        "max_force_image": max_force_image,
        "max_force_eV_per_A": fmaxes[max_force_image] if max_force_image >= 0 else float("nan"),
        "max_force_image_energy_eV": energies[max_force_image] if max_force_image >= 0 else float("nan"),
        "max_force_image_rel_energy_eV": rel_energies[max_force_image] if max_force_image >= 0 else float("nan"),
        "ts_image": ts_image,
        "ts_energy_eV": energies[ts_image] if ts_image >= 0 else float("nan"),
        "barrier_eV": barrier,
        "delta_e_eV": delta_e,
        "energies_eV": energies,
        "rel_energies_eV": rel_energies,
        "image_fmax_eV_per_A": fmaxes,
    }


def _projected_neb_fmax(group: Sequence) -> float | None:
    try:
        return float(NEBTools(list(group)).get_fmax(method="improvedtangent"))
    except Exception:
        return None


def summarize_neb_images(
    images: Sequence,
    *,
    n_max: int = 0,
    source: str | Path | None = None,
    strict: bool = False,
    workflow: str = "neb",
) -> dict[str, Any]:
    """Summarize ordinary NEB frames grouped into repeated bands."""
    images = list(images)
    n_images = _resolve_n_images(images, n_max)
    if n_images <= 0:
        raise ValueError("NEB band size must be positive")
    remainder = len(images) % n_images
    if strict and remainder:
        raise ValueError(f"NEB trajectory contains {len(images)} frame(s), not a whole number of bands with {n_images} images.")
    complete_steps = len(images) // n_images
    steps = [
        _neb_step_summary(images[index * n_images : (index + 1) * n_images], index)
        for index in range(complete_steps)
    ]
    latest = dict(steps[-1]) if steps else {}
    latest_chain = images[(complete_steps - 1) * n_images : complete_steps * n_images] if steps else []
    latest["projected_neb_fmax_eV_per_A"] = _projected_neb_fmax(latest_chain) if latest_chain else None
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "source": str(source) if source is not None else None,
        "status": {
            "n_frames": len(images),
            "n_images": n_images,
            "complete_steps": complete_steps,
            "remainder_frames": remainder,
            "complete": remainder == 0,
        },
        "latest": latest,
        "steps": steps,
    }


def summarize_neb_trajectory(
    traj_file: str | Path,
    *,
    n_max: int = 0,
    strict: bool = False,
) -> dict[str, Any]:
    """Read and summarize an ordinary NEB trajectory."""
    images = read(str(traj_file), index=":")
    return summarize_neb_images(images, n_max=n_max, source=traj_file, strict=strict, workflow="neb")


def summarize_autoneb(
    prefix_or_files: str | Path | Sequence[str | Path],
    *,
    n_max: int = 0,
) -> dict[str, Any]:
    """Summarize the current AutoNEB final chain from per-image files."""
    images = read_autoneb_final_chain(prefix_or_files)
    summary = summarize_neb_images(images, n_max=n_max, source=str(prefix_or_files), strict=True, workflow="autoneb")
    summary["status"]["complete_steps"] = 1
    return summary


def summarize_trajectory(traj_file: str | Path, *, workflow: str, tail: int | None = None) -> dict[str, Any]:
    """Summarize a generic optimization trajectory."""
    frames = read(str(traj_file), index=":")
    frame_summaries = [
        {
            "step": index,
            "energy_eV": energy(atoms),
            "max_force_eV_per_A": max_force(atoms),
        }
        for index, atoms in enumerate(frames)
    ]
    selected = frame_summaries[-tail:] if tail and tail > 0 else frame_summaries
    latest = dict(frame_summaries[-1]) if frame_summaries else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "source": str(traj_file),
        "status": {"n_frames": len(frames), "complete": bool(frames)},
        "latest": latest,
        "frames": selected,
    }


def summarize_vibration_config(config_file: str | Path) -> dict[str, Any]:
    """Summarize vibration cache status and existing result JSON if present."""
    config_path = Path(config_file)
    base_dir = config_path.parent
    config = ConfigLoader.normalize(ConfigLoader.load(config_file))
    calc_config = config["calculation"]
    cache_path = _resolve_output_path(calc_config["name"], base_dir)
    cache_status = check_cache_files(cache_path)
    result_path = _resolve_output_path(calc_config.get("results_file", "vibration_results.json"), base_dir)
    result_data = None
    if result_path.exists():
        try:
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result_data = {"parse_error": "invalid JSON"}
    latest = {
        "valid_cache_files": len(cache_status["valid"]),
        "invalid_cache_files": len(cache_status["invalid"]),
        "result_file": str(result_path) if result_path.exists() else None,
    }
    if isinstance(result_data, dict):
        frequencies = result_data.get("frequencies") or []
        imaginary = result_data.get("imaginary_frequencies") or []
        latest.update(
            {
                "n_frequencies": len(frequencies),
                "n_imaginary_modes": sum(1 for value in imaginary if abs(value) > 1e-12),
                "zpe": result_data.get("zpe"),
                "thermo": result_data.get("thermo"),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": "vibration",
        "source": str(config_path),
        "status": {
            "cache_name": str(cache_path),
            "valid_cache_files": [str(path) for path in cache_status["valid"]],
            "invalid_cache_files": [str(path) for path in cache_status["invalid"]],
            "complete": not cache_status["invalid"],
        },
        "latest": latest,
    }


def _stage_from_traj(path: str | Path, workflow: str, *, n_max: int | None = None, base_dir: Path | None = None) -> dict[str, Any]:
    path = Path(path)
    if base_dir is not None and not path.is_absolute():
        path = _resolve_output_path(path, base_dir)
    if not path.exists():
        return {"status": "missing", "source": str(path)}
    if n_max is not None:
        summary = summarize_neb_trajectory(path, n_max=n_max)
    else:
        summary = summarize_trajectory(path, workflow=workflow)
    summary_status = summary.pop("status", {})
    return {"status": "present", "source": str(path), "summary_status": summary_status, **summary}


def summarize_d2s_config(config_file: str | Path, *, strict: bool = False) -> dict[str, Any]:
    """Summarize available stage outputs for a D2S workflow."""
    config_path = Path(config_file)
    base_dir = config_path.parent
    config = ConfigLoader.normalize(ConfigLoader.load(config_file))
    calc = config["calculation"]
    method = calc["method"].lower()
    stages = {
        "initial_endpoint": _stage_from_traj("IS_opt.traj", "relax", base_dir=base_dir),
        "final_endpoint": _stage_from_traj("FS_opt.traj", "relax", base_dir=base_dir),
        "rough_neb": _stage_from_traj("neb_rough.traj", "neb", n_max=calc["neb"]["n_images"], base_dir=base_dir),
        "single_ended": _stage_from_traj(calc[method]["trajectory"], method, base_dir=base_dir),
    }
    vibration_config = calc.get("vibration", {})
    if vibration_config.get("enabled"):
        result_file = Path(vibration_config["results_file"])
        if not result_file.is_absolute():
            result_file = _resolve_output_path(result_file, base_dir)
        stages["vibration"] = {
            "status": "present" if result_file.exists() else "missing",
            "source": str(result_file),
        }
        if result_file.exists():
            try:
                stages["vibration"]["results"] = json.loads(result_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                stages["vibration"]["status"] = "invalid"
    if strict:
        missing = [name for name, stage in stages.items() if stage["status"] != "present"]
        if missing:
            raise FileNotFoundError("Missing D2S summary stage(s): " + ", ".join(missing))
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": "d2s",
        "source": str(config_path),
        "status": {"method": method, "complete": all(stage["status"] == "present" for stage in stages.values())},
        "latest": stages["single_ended"].get("latest", {}),
        "stages": stages,
    }
