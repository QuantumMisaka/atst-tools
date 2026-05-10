"""Helpers for restartable workflows and ASE cache validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from ase.io import read


def get_last_frame(traj_file: str | Path):
    """Return the last frame from an ASE-readable trajectory."""
    path = Path(traj_file)
    if not path.exists():
        raise FileNotFoundError(f"Restart trajectory does not exist: {path}")
    try:
        return read(str(path), index=-1)
    except Exception as exc:
        raise ValueError(f"Could not read last frame from restart trajectory: {path}") from exc


def get_last_neb_band(traj_file: str | Path, expected_n_images: int):
    """Return the last complete NEB band from a trajectory."""
    if expected_n_images <= 0:
        raise ValueError("expected_n_images must be positive")

    path = Path(traj_file)
    if not path.exists():
        raise FileNotFoundError(f"Restart NEB trajectory does not exist: {path}")
    try:
        images = read(str(path), index=":")
    except Exception as exc:
        raise ValueError(f"Could not read restart NEB trajectory: {path}") from exc

    if len(images) < expected_n_images:
        raise ValueError(
            f"Restart NEB trajectory {path} contains {len(images)} frame(s), "
            f"fewer than expected band size {expected_n_images}."
        )
    if len(images) % expected_n_images != 0:
        raise ValueError(
            f"Restart NEB trajectory {path} contains {len(images)} frame(s), "
            f"not a whole number of bands with {expected_n_images} images."
        )
    return images[-expected_n_images:]


def check_cache_files(vib_dir: str | Path) -> dict[str, list[Path]]:
    """Classify ASE vibration cache JSON files as valid or invalid."""
    path = Path(vib_dir)
    valid: list[Path] = []
    invalid: list[Path] = []
    if not path.exists():
        return {"valid": valid, "invalid": invalid}

    for cache_file in sorted(path.glob("cache*.json")):
        if cache_file.stat().st_size == 0:
            invalid.append(cache_file)
            continue
        try:
            with cache_file.open(encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, json.JSONDecodeError):
            invalid.append(cache_file)
        else:
            valid.append(cache_file)
    return {"valid": valid, "invalid": invalid}


def clean_cache_files(vib_dir: str | Path, keep_good: bool = True) -> dict[str, list[Path]]:
    """Clean ASE vibration cache files and return the pre-clean classification."""
    path = Path(vib_dir)
    status = check_cache_files(path)
    if not path.exists():
        return status

    if keep_good:
        targets: Iterable[Path] = status["invalid"]
        for cache_file in targets:
            cache_file.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)
    return status
