"""ATST consumes structure-specific SCF results through ASE's calculator API.

Parser and matching edge cases belong to the independent abacuslite suite.
These recorded-output checks protect the result handoff used by ATST callers.
"""

from pathlib import Path
import shutil

import numpy as np
import pytest
from ase import Atoms

from atst_tools.calculators.abacuslite_backend import Abacus, ATSTAbacusProfile


GOLD = (
    Path(__file__).resolve().parents[2]
    / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
    / "multiframe_scf_trial_last"
)


class _RecordedOutputProfile(ATSTAbacusProfile):
    """Replay engine output while retaining real input writing and ASE handoff."""

    def __init__(self, calculation):
        super().__init__("unused-engine")
        self.calculation = calculation

    def version(self):
        return "v3.10.1"

    def run(self, directory, inputfile, outputfile, errorfile=None, append=False):
        output = Path(directory) / "OUT.ABACUS"
        output.mkdir(exist_ok=True)
        shutil.copy2(GOLD / "running_scf.log", output / f"running_{self.calculation}.log")


def _atoms_with_calculator(directory, positions, calculation="scf"):
    atoms = Atoms("HAuH", positions=positions, cell=[10, 10, 10], pbc=True)
    atoms.calc = Abacus(
        profile=_RecordedOutputProfile(calculation),
        directory=directory,
        pseudopotentials={"H": "H.upf", "Au": "Au.upf"},
        inp={"calculation": calculation, "basis_type": "pw", "gamma_only": True},
    )
    return atoms


def test_scf_consumer_receives_current_structure_forces_fermi_and_atom_order(tmp_path):
    atoms = _atoms_with_calculator(tmp_path, [[4, 5, 5], [5, 5, 1], [6, 5, 5]])

    np.testing.assert_allclose(
        atoms.get_forces(),
        [[-0.5, -0.01, 0], [0, 0, 0], [0.5, 0.01, 0]],
        atol=1e-12,
    )
    assert atoms.calc.results["efermi"] == pytest.approx(-2.04)
    assert atoms.calc.results["fermi_level"] == pytest.approx(-2.04)


def test_scf_consumer_rejects_output_from_another_structure(tmp_path):
    atoms = _atoms_with_calculator(tmp_path, [[1, 1, 1], [2, 2, 2], [3, 3, 3]])

    with pytest.raises(RuntimeError):
        atoms.get_forces()


def test_native_relaxation_consumer_receives_final_frame_forces(tmp_path):
    atoms = _atoms_with_calculator(
        tmp_path, [[4, 5, 5], [5, 5, 1], [6, 5, 5]], calculation="relax"
    )

    np.testing.assert_allclose(
        atoms.get_forces(),
        [[-0.45, -0.014, 0], [0, 0, 0], [0.45, 0.014, 0]],
        atol=1e-12,
    )
