"""Compare the decorator with a trace executed by the pinned upstream FCP v2."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes

from atst_tools.calculators.constant_potential import ConstantPotentialCalculator

REFERENCE = Path(__file__).parents[1] / "data/constant_potential_reference.json"


class AnalyticAbacus(Calculator):
    """Expose the same analytic response through an ABACUS-style log."""

    implemented_properties = ["energy", "free_energy", "forces"]

    def __init__(self, nelec, directory, trace):
        super().__init__(directory=directory)
        self.nelec = nelec
        self.trace = trace

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        x = self.nelec - 10
        energy = 100 + 5*x + .2*x*x + .005*x**4
        ef = 5 + .4*x + .02*x**3
        self.results.update(energy=energy, free_energy=energy,
                            forces=np.zeros((len(atoms), 3)), efermi=ef,
                            scf_converged=True)
        output = Path(self.directory) / "OUT.ABACUS"
        output.mkdir(parents=True, exist_ok=True)
        (output / "running_scf.log").write_text(
            " charge density convergence is achieved\n"
            f" EFERMI = {ef:.14g} eV\nThe vacuum level is 10.0 eV\n"
        )
        self.trace.append(self.nelec)


def test_fcp_v2_reference_trajectory_and_evaluated_state(tmp_path):
    reference = json.loads(REFERENCE.read_text())
    trace = []

    def factory(nelec, directory):
        return AnalyticAbacus(nelec, directory, trace)

    calculator = ConstantPotentialCalculator(
        factory, directory=tmp_path, work_ref_source="pinned FCP v2 comparison",
        **reference["parameters"],
    )
    atoms = Atoms("H", positions=[[0, 0, 0]], cell=reference["cell"], pbc=True)
    atoms.calc = calculator
    energy = atoms.get_potential_energy()
    normal, adjusted = reference["runs"]
    expected = [row["nelec"] for row in normal["trace"]]
    # Upstream fits six-decimal text samples; the port retains full precision.
    # This bound covers that declared representation change, not a new solver.
    assert len(trace) == len(expected)
    np.testing.assert_allclose(trace, expected, atol=2e-5, rtol=0)
    assert calculator.results["nelec"] == pytest.approx(trace[-1], abs=1e-12)
    assert energy == pytest.approx(normal["published_energy"], abs=1e-7)
    assert adjusted["last_evaluated_nelec"] == normal["last_evaluated_nelec"]
    assert adjusted["next_guess_nelec"] != adjusted["last_evaluated_nelec"]
    count = len(trace)
    np.testing.assert_allclose(atoms.get_forces(), 0)
    assert len(trace) == count
