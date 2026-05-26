import numpy as np
import pytest
from ase import Atoms

from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry


def test_harmonic_thermochemistry_reports_helmholtz_free_energy():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    result = compute_vibration_thermochemistry(
        atoms,
        np.array([0.1, 0.2]),
        {"thermochemistry": {"model": "harmonic", "temperature": 300.0}},
        zpe=0.15,
    )

    assert result["model"] == "harmonic"
    assert result["zpe"] == 0.15
    assert "helmholtz_free_energy" in result


def test_harmonic_thermochemistry_filters_low_energy_noise_by_default():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    result = compute_vibration_thermochemistry(
        atoms,
        np.array([0.0, 1.0e-12, 1.0e-7, 2.0e-6, 0.1]),
        {"thermochemistry": {"model": "harmonic", "temperature": 300.0}},
        zpe=0.05,
    )

    assert result["energy_threshold"] == 1.0e-6
    assert result["n_modes"] == 5
    assert result["n_valid_modes"] == 2
    assert result["n_filtered_modes"] == 3


def test_harmonic_thermochemistry_allows_threshold_override():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    result = compute_vibration_thermochemistry(
        atoms,
        np.array([1.0e-12, 1.0e-7, 2.0e-6]),
        {
            "thermochemistry": {
                "model": "harmonic",
                "temperature": 300.0,
                "energy_threshold": 0.0,
            }
        },
        zpe=0.0,
    )

    assert result["energy_threshold"] == 0.0
    assert result["n_valid_modes"] == 3


def test_harmonic_thermochemistry_rejects_imaginary_modes_when_strict():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    with pytest.raises(ValueError, match="Imaginary vibrational energies"):
        compute_vibration_thermochemistry(
            atoms,
            np.array([0.1 + 0.0j, 0.2j]),
            {
                "thermochemistry": {
                    "model": "harmonic",
                    "temperature": 300.0,
                    "ignore_imag_modes": False,
                }
            },
            zpe=0.05,
        )


def test_ideal_gas_thermochemistry_reports_gibbs_free_energy():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    result = compute_vibration_thermochemistry(
        atoms,
        np.array([0.1]),
        {
            "thermochemistry": {
                "model": "ideal_gas",
                "temperature": 298.15,
                "pressure": 101325.0,
                "geometry": "linear",
                "symmetrynumber": 2,
                "spin": 0,
            }
        },
        zpe=0.05,
    )

    assert result["model"] == "ideal_gas"
    assert result["geometry"] == "linear"
    assert "gibbs_free_energy" in result


def test_ideal_gas_thermochemistry_filters_low_energy_noise():
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]])

    result = compute_vibration_thermochemistry(
        atoms,
        np.array([1.0e-8, 0.1, 0.2]),
        {
            "thermochemistry": {
                "model": "ideal_gas",
                "temperature": 298.15,
                "pressure": 101325.0,
                "geometry": "linear",
                "symmetrynumber": 2,
                "spin": 0,
            }
        },
        zpe=0.15,
    )

    assert result["n_modes"] == 3
    assert result["n_valid_modes"] == 2
