"""Thermochemistry helpers for vibration workflows."""

from __future__ import annotations

from typing import Any

import numpy as np
from ase.thermochemistry import HarmonicThermo, IdealGasThermo

from atst_tools.utils.config_schema import ThermochemistryConfig


def _real_positive_energies(vib_energies, ignore_imag_modes: bool) -> np.ndarray:
    energies = np.asarray(vib_energies)
    if ignore_imag_modes:
        return np.array([energy.real for energy in energies if energy.real > 0], dtype=float)
    return np.array(
        [energy.real for energy in energies if getattr(energy, "imag", 0.0) == 0 and energy.real > 0],
        dtype=float,
    )


def compute_vibration_thermochemistry(
    atoms,
    vib_energies,
    calc_config: dict[str, Any],
    zpe: float,
) -> dict[str, Any]:
    """Compute harmonic or ideal-gas thermochemistry from vibration energies."""
    thermo_config = ThermochemistryConfig.model_validate(calc_config.get("thermochemistry", {})).model_dump()
    model = thermo_config["model"]
    temperature = float(thermo_config["temperature"])
    ignore_imag_modes = bool(thermo_config["ignore_imag_modes"])
    energies = _real_positive_energies(vib_energies, ignore_imag_modes)

    result: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "ignore_imag_modes": ignore_imag_modes,
        "n_modes": int(len(np.asarray(vib_energies))),
        "n_valid_modes": int(len(energies)),
        "zpe": float(zpe),
    }
    if len(energies) == 0:
        result.update(
            {
                "entropy": 0.0,
                "internal_energy": 0.0,
                "helmholtz_free_energy": 0.0,
                "free_energy": 0.0,
            }
        )
        return result

    if model == "harmonic":
        thermo = HarmonicThermo(energies, ignore_imag_modes=ignore_imag_modes)
        internal_energy = thermo.get_internal_energy(temperature, verbose=False)
        helmholtz = thermo.get_helmholtz_energy(temperature, verbose=False)
        result.update(
            {
                "entropy": float(thermo.get_entropy(temperature, verbose=False)),
                "internal_energy": float(internal_energy),
                "helmholtz_free_energy": float(helmholtz),
                "free_energy": float(helmholtz),
            }
        )
        return result

    if model == "ideal_gas":
        pressure = float(thermo_config["pressure"])
        geometry = thermo_config["geometry"]
        symmetrynumber = int(thermo_config["symmetrynumber"])
        spin = float(thermo_config["spin"])
        potentialenergy = float(thermo_config["potentialenergy"])
        thermo = IdealGasThermo(
            energies,
            geometry=geometry,
            potentialenergy=potentialenergy,
            atoms=atoms,
            symmetrynumber=symmetrynumber,
            spin=spin,
            ignore_imag_modes=ignore_imag_modes,
        )
        enthalpy = thermo.get_enthalpy(temperature, verbose=False)
        gibbs = thermo.get_gibbs_energy(temperature, pressure, verbose=False)
        result.update(
            {
                "pressure": pressure,
                "geometry": geometry,
                "symmetrynumber": symmetrynumber,
                "spin": spin,
                "potentialenergy": potentialenergy,
                "entropy": float(thermo.get_entropy(temperature, pressure, verbose=False)),
                "enthalpy": float(enthalpy),
                "gibbs_free_energy": float(gibbs),
                "free_energy": float(gibbs),
            }
        )
        return result

    raise ValueError("vibration thermochemistry.model must be 'harmonic' or 'ideal_gas'")
