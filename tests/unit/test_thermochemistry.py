import numpy as np
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
