"""Reverse ABACUS run directory -> ATST transition YAML config generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_DROP_INPUT_KEYS = {"stru_file", "kpoint_file", "read_file_dir", "basis_dir"}
_PROMOTE_INPUT_KEYS = {"pseudo_dir", "orbital_dir"}
_BOHR_TO_ANGSTROM = 0.529177210903
_ANGSTROM_PER_BOHR = 1.0 / _BOHR_TO_ANGSTROM


def coerce_input_value(value: str) -> Any:
    """Coerce one ABACUS INPUT token to bool/int/float/str (toolbox-compatible)."""
    text = str(value).strip()
    if not text:
        return text
    lowered = text.lower()
    if lowered in {"true", ".true.", "yes", "on"}:
        return True
    if lowered in {"false", ".false.", "no", "off"}:
        return False
    try:
        if not any(mark in lowered for mark in (".", "e")):
            return int(text)
    except Exception:
        pass
    try:
        return float(text)
    except Exception:
        return text


def _read_input(run_dir: Path) -> dict[str, str]:
    from atst_tools.utils.abacus_io import _import_generalio

    input_path = run_dir / "INPUT"
    if not input_path.is_file():
        raise ValueError(f"ABACUS run directory 缺少 INPUT: {run_dir}")
    generalio = _import_generalio()
    return {k: str(v) for k, v in generalio.read_input(str(input_path)).items()}


def _read_stru_species(run_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    from atst_tools.utils.abacus_io import _import_generalio

    stru_path = run_dir / "STRU"
    if not stru_path.is_file():
        raise ValueError(f"ABACUS run directory 缺少 STRU: {run_dir}")
    generalio = _import_generalio()
    stru = generalio.read_stru(str(stru_path))
    pseudopotentials: dict[str, str] = {}
    basissets: dict[str, str] = {}
    for species in stru["species"]:
        symbol = species["symbol"]
        pseudopotentials[symbol] = species["pp_file"]
        if species.get("orb_file"):
            basissets[symbol] = species["orb_file"]
    return pseudopotentials, basissets


def _derive_kgrid_from_kspacing(run_dir: Path, kspacing: str) -> list[int] | None:
    """Derive a Gamma grid from kspacing (Bohr^-1) and the STRU cell (Bohr)."""
    try:
        from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru
        from atst_tools.external.ASE_interface.abacuslite.utils.ksampling import (
            convert_kspacing_to_kpts,
        )

        stru_path = run_dir / "STRU"
        stru = read_stru(str(stru_path))
        const = float(stru["lat"]["const"])
        vec = np.asarray(stru["lat"]["vec"], dtype=float) * const  # Bohr
        cell_angstrom = vec * _BOHR_TO_ANGSTROM
        tokens = str(kspacing).split()
        if len(tokens) == 1:
            ksp_ang = float(tokens[0]) * _ANGSTROM_PER_BOHR
        else:
            ksp_ang = tuple(float(t) * _ANGSTROM_PER_BOHR for t in tokens[:3])
        return list(convert_kspacing_to_kpts(cell_angstrom, ksp_ang))
    except Exception:
        return None


def _resolve_kpts(run_dir: Path, parameters: dict[str, Any]) -> Any:
    """Resolve runtime K points with the toolbox-compatible three-tier priority."""
    from atst_tools.utils.abacus_io import _import_generalio

    gamma_only = str(parameters.get("gamma_only", "")).strip().lower()
    if gamma_only in {"1", "true", ".true.", "yes", "on"}:
        return [1, 1, 1]
    kspacing = parameters.get("kspacing")
    if kspacing not in (None, ""):
        grid = _derive_kgrid_from_kspacing(run_dir, str(kspacing))
        if grid is None:
            raise ValueError(
                f"无法由 kspacing 派生 K 点网格（STRU cell 解析失败）: {run_dir}"
            )
        return grid
    kpt_path = run_dir / "KPT"
    if not kpt_path.is_file():
        raise ValueError(
            "无有效 K 点来源：需要 gamma_only=1、正 kspacing 或有效 KPT"
        )
    generalio = _import_generalio()
    parsed = generalio.read_kpt(str(kpt_path))
    mode = str(parsed.get("mode", "")).lower()
    if mode == "line":
        raise ValueError(
            "Line 模式 KPT 不适用于过渡态力计算；请改用 Gamma/MP 网格或 point 显式 K 点"
        )
    if mode == "mp-sampling":
        return list(parsed["nk"])
    if mode == "point":
        return parsed
    raise ValueError(f"不支持的 KPT 模式: {mode}")


def endpoint_has_energy_forces(run_dir: str | Path) -> bool:
    """Return whether an ABACUS run dir has parseable last-frame energy+forces.

    Uses the legacyio parser family (no eig_occ.txt requirement) so real relax
    endpoint directories are accepted (SPEC R-8; aligned with the 08-11 bridge).
    """
    from atst_tools.external.ASE_interface.abacuslite.io.legacyio import (
        find_final_info_with_iter_header,
        read_energies_from_running_log,
        read_forces_from_running_log,
        read_iter_header_from_running_log,
    )

    base = Path(run_dir)
    logs = sorted(base.glob("running*.log")) + sorted(base.glob("OUT*/running*.log"))
    if not logs:
        return False
    log = logs[-1]
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        headers = read_iter_header_from_running_log(lines)
        # read_energies_from_running_log returns (Rydberg, eV) table pairs; the
        # final-iteration energies are selected by the iteration header indices.
        energies = find_final_info_with_iter_header(
            read_energies_from_running_log(lines)[1], headers
        )
        forces = read_forces_from_running_log(lines)
        if not energies or not forces:
            return False
        f_arr = np.asarray(forces[-1], dtype=float)
        return f_arr.ndim == 2 and f_arr.shape[1] == 3
    except Exception:
        return False


def build_config_from_abacus_dir(
    abacus_run_dir: str | Path,
    *,
    workflow: str = "neb",
    init_structure: str | Path | None = None,
    final_structure: str | Path | None = None,
    n_images: int = 5,
    gate_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Reverse-generate a runnable ATST transition config from an ABACUS run dir."""
    run_dir = Path(abacus_run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"ABACUS run directory 不存在: {run_dir}")

    raw = _read_input(run_dir)
    parameters = {
        key: coerce_input_value(value)
        for key, value in raw.items()
        if key.lower() not in _DROP_INPUT_KEYS
        and key.lower() not in _PROMOTE_INPUT_KEYS
    }
    # 技术地板：calculation -> scf，cal_force -> 1
    parameters["calculation"] = "scf"
    parameters["cal_force"] = 1

    pseudo_dir = raw.get("pseudo_dir")
    orbital_dir = raw.get("orbital_dir")

    def _resolve_dir(value: str | None, default: Path) -> Path:
        if not value:
            return default
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = run_dir / candidate
        return candidate.resolve()

    pseudopotentials, basissets = _read_stru_species(run_dir)
    basis_type = str(parameters.get("basis_type", "lcao")).strip().lower()
    if basis_type != "pw":
        missing = [s for s in pseudopotentials if s not in basissets]
        if missing:
            raise ValueError(f"STRU 缺少 LCAO 轨道文件名: {', '.join(missing)}")

    kpts = _resolve_kpts(run_dir, raw)

    abacus: dict[str, Any] = {
        "command": "abacus",
        "mpi": 4,
        "omp": 1,
        "directory": "run_atst",
        "kpts": kpts,
        "pseudo_dir": str(_resolve_dir(pseudo_dir, run_dir)),
        "orbital_dir": str(_resolve_dir(orbital_dir, run_dir)),
        "pseudopotentials": pseudopotentials,
        "parameters": parameters,
    }
    if basissets:
        abacus["basissets"] = basissets

    calc: dict[str, Any]
    if workflow == "neb":
        calc = {
            "type": "neb",
            "make": {
                "init_structure": str(init_structure or run_dir / "STRU"),
                "final_structure": str(final_structure or run_dir / "STRU"),
                "n_images": int(n_images),
                "method": "IDPP",
                "output": "inputs/init_neb_chain.traj",
            },
            "fmax": 0.05,
            "k": 0.1,
            "parallel": True,
            "max_steps": 100,
            "optimizer": "FIRE",
        }
    else:
        raise ValueError(f"尚未支持的 workflow: {workflow}（P0 为 neb）")

    if gate_dirs is not None:
        for directory in gate_dirs:
            if not endpoint_has_energy_forces(directory):
                raise ValueError(
                    f"端点目录缺少可解析的 energy+forces 输出: {directory}"
                )

    return {"calculator": {"name": "abacus", "abacus": abacus}, "calculation": calc}
