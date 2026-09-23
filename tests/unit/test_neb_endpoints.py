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
    ENDPOINT_OPTIMIZED,
    ENDPOINT_PLACEHOLDER,
    ENDPOINT_PROVIDED,
    ENDPOINT_RESULT_KEY,
    CP_ENDPOINT_IDENTITY_KEY,
    ensure_neb_endpoint_results,
    freeze_current_results,
    mark_endpoint_result,
)
from atst_tools.calculators.constant_potential import publish_constant_potential_facts


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


class EnergyForceOnlyCalc(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self):
        super().__init__()
        self.stress_calls = 0

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = 4.0
        self.results["forces"] = np.ones((len(atoms), 3)) * 0.5

    def get_stress(self, atoms=None):
        self.stress_calls += 1
        raise RuntimeError("stress should not be requested")


def _atoms(energy=0.0, x=0.0, with_calc=True):
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    if with_calc:
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


def _placeholder_atoms(x=0.0):
    atoms = _atoms(0.0, x=x)
    mark_endpoint_result(atoms, ENDPOINT_PLACEHOLDER)
    return atoms


def _complete_cp_results(atoms, identity, energy):
    """Build a complete durable CP result for endpoint persistence tests."""
    target = float(identity["target_mu_ev"])
    reference_electrons = float(identity["reference_electrons"])
    return {
        "energy": float(energy),
        "free_energy": float(energy),
        "raw_energy": float(energy),
        "raw_free_energy": float(energy),
        "efermi": target,
        "vacuum_level": None,
        "fermishift": None,
        "energy_boundary": "compensated_gate",
        "boundary_parameters": {},
        "compensation": {
            "boundary": "compensated_gate",
            "gate_derivative_ev": 0.0,
            "dipole_derivative_ev": 0.0,
            "compensation_derivative_ev": 0.0,
            "integrated_electrons": reference_electrons,
            "density_electron_error": 0.0,
            "ionic_valence_electrons": reference_electrons,
            "total_dipole_ry_au": 0.0,
            "density_precision": 12,
            "density_electron_tolerance": 1e-8,
        },
        "mu_calc": target,
        "mu_target": target,
        "potential_calc": None,
        "potential_target": None,
        "residual_mu": 0.0,
        "residual_v": 0.0,
        "omega_correction": 0.0,
        "nelec": reference_electrons,
        "reference_electrons": reference_electrons,
        "delta_nelec": 0.0,
        "forces": atoms.get_forces(),
        "scf_converged": True,
        "cp_converged": True,
        "cp_iterations": 1,
        "cp_history": [{"converged": True}],
    }


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


def test_freeze_current_results_does_not_request_missing_stress():
    atoms = _atoms(with_calc=False)
    calc = EnergyForceOnlyCalc()
    atoms.calc = calc

    freeze_current_results(atoms)

    assert atoms.get_potential_energy() == pytest.approx(4.0)
    np.testing.assert_allclose(atoms.get_forces(), np.ones((1, 3)) * 0.5)
    assert calc.stress_calls == 0


@pytest.mark.parametrize("status", [ENDPOINT_COMPUTED, ENDPOINT_PROVIDED, ENDPOINT_OPTIMIZED])
def test_auto_keeps_atst_marked_endpoint(status):
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]
    mark_endpoint_result(chain[0], status)
    mark_endpoint_result(chain[-1], status)
    calls = []

    def get_calculator(directory):
        calls.append(directory)
        return DummyCalc(energy=9.0)

    ensure_neb_endpoint_results(chain, get_calculator, policy="auto")

    assert calls == []
    assert chain[0].get_potential_energy() == 1.0
    assert chain[-1].get_potential_energy() == 3.0


def test_auto_recomputes_unmarked_readable_endpoint():
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]
    calls = []

    def get_calculator(directory):
        calls.append(directory)
        return DummyCalc(energy=9.0)

    ensure_neb_endpoint_results(chain, get_calculator, policy="auto")

    assert calls == ["endpoint_initial", "endpoint_final"]
    assert chain[0].get_potential_energy() == 9.0
    assert chain[-1].get_potential_energy() == 9.0
    assert chain[0].info[ENDPOINT_RESULT_KEY] == ENDPOINT_COMPUTED
    assert chain[-1].info[ENDPOINT_RESULT_KEY] == ENDPOINT_COMPUTED


def test_never_preserves_unmarked_readable_endpoint():
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]
    calls = []

    def get_calculator(directory):
        calls.append(directory)
        return DummyCalc(energy=9.0)

    ensure_neb_endpoint_results(chain, get_calculator, policy="never")

    # "never" preserves user-provided readable endpoints: no recompute and no raise.
    assert calls == []
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


def test_cp_identity_mismatch_recomputes_auto_and_never_rejects():
    identity = {
        "energy_boundary": "compensated_gate",
        "potential_v": None,
        "target_mu_ev": -15.0,
        "reference_electrode": "custom",
        "work_ref": None,
        "work_ref_source": None,
        "reference_pH": None,
        "temperature_K": None,
        "reference_electrons": 216.0,
        "boundary_parameters": {},
        "energy_definition": "omega_compensated_gate",
        "calculator": "constant_potential",
    }
    chain = [_atoms(1.0), _atoms(2.0), _atoms(3.0)]
    for endpoint in (chain[0], chain[-1]):
        mark_endpoint_result(endpoint, ENDPOINT_COMPUTED)
        publish_constant_potential_facts(
            endpoint,
            _complete_cp_results(endpoint, identity, endpoint.get_potential_energy()),
            identity,
        )
    chain[-1].info[CP_ENDPOINT_IDENTITY_KEY]["target_mu_ev"] = -14.0
    chain[-1].info["atst_constant_potential_facts"]["identity"]["target_mu_ev"] = -14.0

    with pytest.raises(ValueError, match="lacks meaningful"):
        ensure_neb_endpoint_results(
            chain,
            lambda directory: DummyCalc(energy=9.0),
            policy="never",
            constant_potential_identity=identity,
        )

    calls = []

    def get_calculator(directory):
        calls.append(directory)
        return DummyCalc(energy=9.0)

    ensure_neb_endpoint_results(
        chain,
        get_calculator,
        policy="auto",
        constant_potential_identity=identity,
    )
    assert calls == ["endpoint_final"]
    assert chain[0].info[CP_ENDPOINT_IDENTITY_KEY] == identity
    assert CP_ENDPOINT_IDENTITY_KEY not in chain[-1].info


def test_cp_facts_round_trip_and_geometry_staleness_are_endpoint_gated(tmp_path):
    identity = {
        "energy_boundary": "compensated_gate",
        "potential_v": None,
        "target_mu_ev": -15.0,
        "reference_electrode": "custom",
        "work_ref": None,
        "work_ref_source": None,
        "reference_pH": None,
        "temperature_K": None,
        "reference_electrons": 216.0,
        "boundary_parameters": {},
        "energy_definition": "omega_compensated_gate",
        "calculator": "constant_potential",
        "fixed_hamiltonian": {
            "boundary_parameters": {"zgate": 0.7},
            "assets": {"pseudopotentials": [{"sha256": "pp-v1"}]},
        },
    }
    endpoint = _atoms(1.0)
    mark_endpoint_result(endpoint, ENDPOINT_COMPUTED)
    publish_constant_potential_facts(
        endpoint,
        _complete_cp_results(endpoint, identity, 1.0),
        identity,
    )
    path = tmp_path / "endpoint.traj"
    write(path, endpoint)
    loaded = read(path)
    final = _atoms(3.0)
    mark_endpoint_result(final, ENDPOINT_COMPUTED)
    publish_constant_potential_facts(
        final,
        _complete_cp_results(final, identity, 3.0),
        identity,
    )
    chain = [loaded, _atoms(2.0), final]

    calls = []
    ensure_neb_endpoint_results(
        chain,
        lambda directory: calls.append(directory) or DummyCalc(),
        policy="never",
        constant_potential_identity=identity,
    )
    assert calls == []

    loaded.positions[0, 0] += 0.2
    with pytest.raises(ValueError, match="lacks meaningful"):
        ensure_neb_endpoint_results(
            [loaded, _atoms(2.0), final],
            lambda directory: DummyCalc(),
            policy="never",
            constant_potential_identity=identity,
        )

    changed_identity = {
        **identity,
        "fixed_hamiltonian": {
            **identity["fixed_hamiltonian"],
            "boundary_parameters": {"zgate": 0.8},
        },
    }
    loaded_again = read(path)
    final_again = final.copy()
    calls = []
    ensure_neb_endpoint_results(
        [loaded_again, _atoms(2.0), final_again],
        lambda directory: calls.append(directory) or DummyCalc(),
        policy="auto",
        constant_potential_identity=changed_identity,
    )
    assert calls == ["endpoint_initial", "endpoint_final"]


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


def test_zero_endpoint_regression_changes_barrier():
    band = [
        _atoms(energy=-10.0, x=0.0),
        _atoms(energy=-9.6, x=1.0),
        _atoms(energy=-9.2, x=2.0),
        _atoms(energy=-9.5, x=3.0),
        _atoms(energy=-9.8, x=4.0),
    ]
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

    assert real_barrier == pytest.approx(0.8)
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
