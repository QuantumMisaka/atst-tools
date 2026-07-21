"""Lightweight ABACUS input and output helpers."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
from ase.io import write

from atst_tools.calculators.abacuslite_backend import BACKEND_SOURCE
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.io import read_structure


_ABACUS_META_KEYS = {
    "command",
    "directory",
    "mpi",
    "omp",
    "parameters",
    "version_command",
}
_ABACUS_NON_INPUT_KEYS = {
    "basis",
    "basissets",
    "kpts",
    "pp",
    "pseudopotentials",
}


def _import_generalio():
    try:
        from abacuslite.io import generalio
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite.io import generalio
    return generalio


def _import_latestio():
    try:
        from abacuslite.io.latestio import read_abacus_out
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite.io.latestio import read_abacus_out
    return read_abacus_out


def _as_mp_kpts(kpts: Any) -> dict[str, Any]:
    if isinstance(kpts, list) and len(kpts) == 3:
        return {
            "mode": "mp-sampling",
            "nk": kpts,
            "gamma-centered": True,
            "kshift": [0, 0, 0],
        }
    if isinstance(kpts, dict):
        return dict(kpts)
    raise ValueError("ABACUS kpts must be a 3-item list or a KPT mapping")


def _merged_abacus_parameters(abacus: dict[str, Any]) -> dict[str, Any]:
    parameters = {
        key: value
        for key, value in abacus.items()
        if key not in _ABACUS_META_KEYS
    }
    parameters.update(dict(abacus.get("parameters", {})))
    if "pp" in parameters:
        parameters["pseudopotentials"] = parameters.pop("pp")
    if "basis" in parameters:
        parameters["basissets"] = parameters.pop("basis")
    if "basis_dir" in parameters:
        parameters["orbital_dir"] = parameters.pop("basis_dir")
    return parameters


def _input_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in parameters.items()
        if key not in _ABACUS_NON_INPUT_KEYS
    }


def _resolve_config_path(value: str | Path, *, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def _absolutize_abacus_path_parameters(parameters: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    updated = dict(parameters)
    for key in ("pseudo_dir", "orbital_dir", "basis_dir"):
        value = updated.get(key)
        if value:
            updated[key] = _resolve_config_path(value, base_dir=base_dir)
    return updated


def _representative_structure_paths(config: dict[str, Any], *, base_dir: Path) -> list[str]:
    calculation = dict(config.get("calculation", {}))
    paths: list[str] = []
    for key in ("init_structure", "init_chain", "init_file", "final_file", "product_file"):
        if calculation.get(key):
            paths.append(_resolve_config_path(calculation[key], base_dir=base_dir))
    make = calculation.get("make")
    if isinstance(make, dict):
        for key in ("init_structure", "final_structure", "ts_guess"):
            if make.get(key):
                paths.append(_resolve_config_path(make[key], base_dir=base_dir))
    unique: list[str] = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _tail(text: str, limit: int = 4000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return "...(truncated)...\n" + text[-limit:]


def _abacus_check_command(abacus_executable: str) -> list[str]:
    command = shlex.split(abacus_executable or "abacus")
    if not command:
        command = ["abacus"]
    return [*command, "--check-input"]


@contextmanager
def _temporary_check_root(base_dir: Path):
    try:
        manager = tempfile.TemporaryDirectory(prefix=".atst_check_input_", dir=str(base_dir))
    except OSError:
        fallback_dir = tempfile.gettempdir()
        manager = tempfile.TemporaryDirectory(prefix=".atst_check_input_", dir=fallback_dir)

    with manager as tmp:
        yield tmp


def prepare_abacus_input_from_config(
    config: dict[str, Any],
    structure_file: str,
    output_dir: str,
    *,
    config_base_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, str]:
    calculator = config.get("calculator", {})
    if calculator.get("name") != "abacus":
        raise ValueError("ABACUS helpers require calculator.name: abacus")
    abacus = dict(calculator.get("abacus", {}))
    base_dir = Path(config_base_dir or Path.cwd()).resolve()
    parameters = _absolutize_abacus_path_parameters(_merged_abacus_parameters(abacus), base_dir=base_dir)
    destination = Path(output_dir)
    targets = [destination / "INPUT", destination / "KPT", destination / "STRU"]
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing ABACUS file(s): {names}")

    destination.mkdir(parents=True, exist_ok=True)
    atoms = read_structure(structure_file)
    generalio = _import_generalio()

    kpts = _as_mp_kpts(parameters.get("kpts", abacus.get("kpts", [1, 1, 1])))
    pseudopotentials = parameters.get("pseudopotentials")
    basissets = parameters.get("basissets")

    paths = {
        "INPUT": generalio.write_input(_input_parameters(parameters), str(destination / "INPUT")),
        "KPT": generalio.write_kpt(kpts, str(destination / "KPT")),
        "STRU": generalio.write_stru(atoms, str(destination), pseudopotentials, basissets, "STRU"),
    }
    return paths


def run_abacus_check_input_dry_run(
    config: dict[str, Any],
    config_path: str | None,
    *,
    timeout_sec: int = 120,
    abacus_executable: str = "abacus",
) -> dict[str, Any]:
    base_dir = (
        Path(config_path).expanduser().resolve().parent
        if config_path is not None
        else Path.cwd().resolve()
    )
    structure_paths = _representative_structure_paths(config, base_dir=base_dir)
    if not structure_paths:
        raise ValueError("No representative structure path found for ABACUS check-input dry-run")

    checked = 0
    workdirs: list[str] = []
    for index, structure_file in enumerate(structure_paths):
        with _temporary_check_root(base_dir) as tmp:
            check_dir = Path(tmp) / str(index)
            prepare_abacus_input_from_config(
                config,
                structure_file,
                str(check_dir),
                config_base_dir=base_dir,
                force=True,
            )
            env = os.environ.copy()
            env["OMP_NUM_THREADS"] = "1"
            proc = subprocess.run(
                _abacus_check_command(abacus_executable),
                cwd=str(check_dir),
                env=env,
                text=True,
                capture_output=True,
                timeout=int(timeout_sec),
            )
            workdirs.append(str(check_dir))
            if proc.returncode != 0:
                raise RuntimeError(
                    "abacus --check-input failed\n"
                    f"structure={structure_file}\n"
                    f"workdir={check_dir}\n"
                    f"returncode={proc.returncode}\n"
                    f"stdout:\n{_tail(proc.stdout)}\n"
                    f"stderr:\n{_tail(proc.stderr)}"
                )
            checked += 1
    return {"checked": checked, "workdirs": workdirs}


def prepare_abacus_input(
    config_file: str,
    structure_file: str,
    output_dir: str,
    *,
    force: bool = False,
) -> dict[str, str]:
    """Write ABACUS INPUT, KPT, and STRU files from an ATST config.

    Args:
        config_file: Path to an ATST YAML configuration using ABACUS.
        structure_file: Structure file readable by ASE/ATST-Tools.
        output_dir: Directory where ABACUS input files will be written.
        force: Overwrite existing ABACUS input files if true.

    Returns:
        Mapping from logical file names to absolute written paths.

    Raises:
        FileExistsError: If output files exist and ``force`` is false.
        ValueError: If the configuration is not an ABACUS configuration.
    """
    config = ConfigLoader.normalize(ConfigLoader.load(config_file))
    return prepare_abacus_input_from_config(
        config,
        structure_file,
        output_dir,
        config_base_dir=Path(config_file).expanduser().resolve().parent,
        force=force,
    )


def _find_running_logs(run_dir: Path) -> list[Path]:
    patterns = ("running*.log", "OUT*/running*.log", "**/running*.log")
    logs: set[Path] = set()
    for pattern in patterns:
        logs.update(path for path in run_dir.glob(pattern) if path.is_file())
    return sorted(logs, key=lambda path: path.relative_to(run_dir).as_posix())


def _max_force(atoms: Any) -> float | None:
    try:
        forces = atoms.get_forces()
    except Exception:
        return None
    if len(forces) == 0:
        return 0.0
    return float(np.linalg.norm(forces, axis=1).max())


def _parse_last_abacus_frame(log: Path):
    if not (log.parent / "eig_occ.txt").exists():
        return None

    read_abacus_out = _import_latestio()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        copied_log = tmpdir / log.name
        shutil.copy2(log, copied_log)
        shutil.copy2(log.parent / "eig_occ.txt", tmpdir / "eig_occ.txt")
        atoms_or_frames = read_abacus_out(copied_log)
    if isinstance(atoms_or_frames, list):
        return atoms_or_frames[-1] if atoms_or_frames else None
    return atoms_or_frames


def collect_abacus_output(
    run_dir: str,
    output: str,
    *,
    structure: str | None = None,
) -> dict[str, Any]:
    """Collect a conservative JSON summary from an ABACUS run directory.

    Args:
        run_dir: ABACUS run directory to inspect.
        output: JSON summary path to write.
        structure: Optional ASE structure output path for the parsed last frame.

    Returns:
        The JSON-serializable summary that was written.
    """
    base = Path(run_dir)
    if not base.exists():
        raise FileNotFoundError(f"ABACUS run directory not found: {run_dir}")

    logs = _find_running_logs(base)
    summary: dict[str, Any] = {
        "backend": BACKEND_SOURCE,
        "run_dir": str(base.resolve()),
        "logs": [path.relative_to(base).as_posix() for path in logs],
        "files": {
            "INPUT": (base / "INPUT").exists(),
            "KPT": (base / "KPT").exists(),
            "STRU": (base / "STRU").exists(),
        },
        "parsed": False,
        "frames": 0,
        "energy_eV": None,
        "max_force_eV_per_ang": None,
        "parse_error": None,
    }

    if logs:
        try:
            atoms = _parse_last_abacus_frame(logs[-1])
            if atoms is not None:
                summary["parsed"] = True
                summary["frames"] = 1
                try:
                    summary["energy_eV"] = float(atoms.get_potential_energy())
                except Exception:
                    summary["energy_eV"] = None
                summary["max_force_eV_per_ang"] = _max_force(atoms)
                if structure:
                    write(structure, atoms)
        except Exception as exc:
            summary["parse_error"] = str(exc)

    Path(output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
