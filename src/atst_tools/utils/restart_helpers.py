"""Helpers for restartable workflows and ASE cache validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
import re
from typing import Iterable, Sequence

from ase.io import read
from ase.mep.neb import NEBTools


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

    return select_last_neb_chain(images, expected_n_images, strict=True)


def select_last_neb_chain(images: Sequence, expected_n_images: int, strict: bool = True):
    """Return the last NEB band with a known total band size.

    Args:
        images: Full trajectory frames.
        expected_n_images: Total images per NEB band, including endpoints.
        strict: Require the trajectory length to be an exact multiple of the band
            size. Restart paths should keep this enabled.

    Returns:
        list: Last selected NEB band.

    Raises:
        ValueError: If the band size is invalid or a complete band cannot be
            selected.
    """
    if expected_n_images <= 0:
        raise ValueError("expected_n_images must be positive")
    if len(images) < expected_n_images:
        raise ValueError(
            f"NEB trajectory contains {len(images)} frame(s), fewer than expected "
            f"band size {expected_n_images}."
        )
    if strict and len(images) % expected_n_images != 0:
        raise ValueError(
            f"NEB trajectory contains {len(images)} frame(s), not a whole number "
            f"of bands with {expected_n_images} images."
        )
    return list(images[-expected_n_images:])


def select_post_neb_chain(images: Sequence, n_max: int = 0, strict: bool = False):
    """Select the final NEB band for analysis or export.

    Args:
        images: Full trajectory frames.
        n_max: Number of intermediate images. A value of 0 keeps the historical
            loose post-processing behavior and returns all frames.
        strict: Require a complete number of bands when ``n_max`` is provided.

    Returns:
        list: Selected final chain.
    """
    if n_max < 0:
        raise ValueError("n_max must be a non-negative integer")
    if n_max == 0:
        try:
            n_images = NEBTools(list(images))._guess_nimages()
        except Exception:
            return list(images)
        return list(images[-n_images:])
    return select_last_neb_chain(images, n_max + 2, strict=strict)


def _autoneb_sort_key(path: Path):
    numbers = [int(match) for match in re.findall(r"\d+", path.stem)]
    return (numbers[-1] if numbers else -1, path.name)


def read_autoneb_final_chain(prefix_or_files: str | Path | Sequence[str | Path]):
    """Read an AutoNEB final chain from a prefix or explicit trajectory files.

    Explicit file lists are sorted by the final integer in each file stem, then
    by file name. Prefix input matches ``PREFIX*.traj`` and ``PREFIX*.extxyz``.
    Each file contributes its last frame, which matches AutoNEB per-image output.
    """
    if isinstance(prefix_or_files, (str, Path)):
        prefix = Path(prefix_or_files)
        parent = prefix.parent if str(prefix.parent) != "" else Path(".")
        files = sorted(
            list(parent.glob(f"{prefix.name}*.traj")) + list(parent.glob(f"{prefix.name}*.extxyz")),
            key=_autoneb_sort_key,
        )
    else:
        files = sorted((Path(path) for path in prefix_or_files), key=_autoneb_sort_key)
    if not files:
        raise FileNotFoundError("No AutoNEB trajectory files matched")
    return [read(str(path), index=-1) for path in files]


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
