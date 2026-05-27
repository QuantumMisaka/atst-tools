from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write
from ase.mep.neb import NEBTools

from atst_tools.utils.neb_endpoints import (
    ENDPOINT_COMPUTED,
    ENDPOINT_PLACEHOLDER,
    ENDPOINT_RESULT_KEY,
    ensure_neb_endpoint_results,
    mark_endpoint_result,
)


class DummyCalc(Calculator):
    implemented_properties = ["energy", "forces", "stress"]

    def __init__(self, energy=7.0):
        super().__init__()
        self.energy = energy

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = self.energy
        self.results["forces"] = np.ones((len(atoms), 3)) * 0.25
        self.results["stress"] = np.zeros(6)


def _atoms(energy=0.0, x=0.0, with_calc=True):
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    if with_calc:
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


def _placeholder_atoms(x=0.0):
    atoms = _atoms(0.0, x=x)
    mark_endpoint_result(atoms, ENDPOINT_PLACEHOLDER)
    return atoms


def test_endpoint_helper_recomputes_placeholder_endpoint(capsys):
    chain = [_placeholder_atoms(0.0), _atoms(1.0, 1.0), _placeholder_atoms(2.0)]

    ensure_neb_endpoint_results(
        chain,
        lambda directory: DummyCalc(energy=5.0 if "initial" in directory else 6.0),
        policy="auto",
        context="NEB",
    )

    assert chain[0].get_potential_energy() == 5.0
    assert chain[-1].get_potential_energy() == 6.0
    assert chain[0].info[ENDPOINT_RESULT_KEY] == ENDPOINT_COMPUTED
    assert "placeholder" in capsys.readouterr().out


def test_endpoint_helper_keeps_valid_endpoint_in_auto_mode():
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]

    ensure_neb_endpoint_results(chain, lambda directory: DummyCalc(energy=9.0), policy="auto")

    assert chain[0].get_potential_energy() == 1.0
    assert chain[-1].get_potential_energy() == 3.0


def test_endpoint_helper_never_rejects_placeholder():
    chain = [_placeholder_atoms(), _atoms(1.0), _placeholder_atoms()]

    with pytest.raises(ValueError, match="lacks meaningful"):
        ensure_neb_endpoint_results(chain, lambda directory: DummyCalc(), policy="never")


def test_endpoint_helper_always_recomputes_valid_endpoint():
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]

    ensure_neb_endpoint_results(chain, lambda directory: DummyCalc(energy=9.0), policy="always")

    assert chain[0].get_potential_energy() == 9.0
    assert chain[-1].get_potential_energy() == 9.0


def test_neb_make_marks_pure_structure_endpoints_as_placeholder(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    init = _atoms(with_calc=False)
    final = _atoms(x=1.0, with_calc=False)
    write("init.xyz", init)
    write("final.xyz", final)

    cli.main(["neb", "make", "init.xyz", "final.xyz", "1", "-o", "chain.traj", "--method", "linear", "--no-align"])

    chain = read("chain.traj", index=":")
    assert [atoms.info.get(ENDPOINT_RESULT_KEY) for atoms in (chain[0], chain[-1])] == [
        ENDPOINT_PLACEHOLDER,
        ENDPOINT_PLACEHOLDER,
    ]
    assert [chain[0].get_potential_energy(), chain[-1].get_potential_energy()] == [0.0, 0.0]


def test_li_si_zero_endpoint_regression_changes_barrier():
    endpoint_reference_energies = [-1.0, -0.4, -0.1, -0.3, -1.1]
    band = [_atoms(energy=energy, x=float(index)) for index, energy in enumerate(endpoint_reference_energies)]
    real = [atoms.copy() for atoms in band]
    zero = [atoms.copy() for atoms in band]
    for index, atoms in enumerate(real):
        source = band[index]
        atoms.calc = SinglePointCalculator(atoms, energy=source.get_potential_energy(), forces=source.get_forces())
    for index, atoms in enumerate(zero):
        if index in {0, len(zero) - 1}:
            atoms.calc = SinglePointCalculator(atoms, energy=0.0, forces=np.zeros((len(atoms), 3)))
        else:
            source = band[index]
            atoms.calc = SinglePointCalculator(atoms, energy=source.get_potential_energy(), forces=source.get_forces())

    real_barrier = NEBTools(real).get_barrier(fit=False)[0]
    zero_barrier = NEBTools(zero).get_barrier(fit=False)[0]

    assert real_barrier > 0.7
    assert zero_barrier == 0.0


def test_autoneb_runner_repairs_endpoints_before_writing_initial_files(tmp_path, monkeypatch):
    from atst_tools.mep import autoneb

    monkeypatch.chdir(tmp_path)
    chain = [_placeholder_atoms(0.0), _atoms(1.0, 1.0), _placeholder_atoms(2.0)]
    write("init_chain.traj", chain)

    class FakeAutoNEB:
        def __init__(self, **kwargs):
            return None

        def run(self):
            return None

    monkeypatch.setattr(autoneb.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc(energy=8.0))
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", FakeAutoNEB)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"directory": "run_autoneb", "parameters": {}}}},
        "abacus",
        {"type": "autoneb", "init_chain": "init_chain.traj", "prefix": "run_autoneb", "parallel": False},
    )
    runner.run()

    first = read("run_autoneb000.traj")
    last = read("run_autoneb002.traj")
    assert first.get_potential_energy() == 8.0
    assert last.get_potential_energy() == 8.0
    assert first.info[ENDPOINT_RESULT_KEY] == ENDPOINT_COMPUTED
