"""Focused constant-potential calculator and workflow contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import read, write

from atst_tools.calculators.constant_potential import (
    CP_FACTS_INFO_KEY,
    CP_IDENTITY_INFO_KEY,
    ConstantPotentialCalculator,
    ConstantPotentialConvergenceError,
    ConstantPotentialEvaluationError,
    constant_potential_identity_for_config,
    fixed_hamiltonian_identity_for_config,
    publish_constant_potential_facts,
    read_constant_potential_facts,
)
from atst_tools.api import RunOptions, run_workflow
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.electrochemistry import (
    ElectrochemistryError,
    analyze_potential_scan,
    chebyshev_derivative,
)
from atst_tools.utils.neb_endpoints import constant_potential_identity_matches
from atst_tools.workflows.constant_potential import ConstantPotentialWorkflow


class QuadraticPotentialCalculator(Calculator):
    """Deterministic fixed-electron backend with analytic Fermi response."""

    implemented_properties = ["energy", "free_energy", "forces"]

    def __init__(self, nelec: float, vacuum: float = 10.0):
        super().__init__()
        self.nelec = float(nelec)
        self.vacuum = float(vacuum)

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        efermi = 3.2 + 0.12 * self.nelec
        self.results.update(
            {
                "energy": 0.5 * self.nelec**2,
                "free_energy": 0.5 * self.nelec**2,
                "forces": np.zeros((len(atoms), 3)),
                "efermi": efermi,
                "vacuum_level": self.vacuum,
                "scf_converged": True,
            }
        )


def _factory(nelec: float, directory: str):
    return QuadraticPotentialCalculator(nelec)


def test_chebyshev_derivative_rejects_rank_deficient_degree_escalation():
    with pytest.raises(ElectrochemistryError, match="rank deficient"):
        chebyshev_derivative(
            [10.0, 10.0, 11.0, 11.0],
            [0.0, 1.0, 2.0, 3.0],
            10.0,
        )


def test_newton_history_records_fit_fallback_for_rank_deficiency(tmp_path):
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=0.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        directory=tmp_path,
    )
    _, fit_info = calculator._next_candidate(
        {"nelec": 10.0, "residual_mu": 0.5},
        [
            {"valid": True, "nelec": 10.0, "mu_calc": 0.0},
            {"valid": True, "nelec": 10.0, "mu_calc": 1.0},
            {"valid": True, "nelec": 11.0, "mu_calc": 2.0},
            {"valid": True, "nelec": 11.0, "mu_calc": 3.0},
        ],
        capacitance=1.0,
    )
    assert fit_info["fit_status"] == "fallback"
    assert fit_info["derivative_source"] == "fallback_previous_capacitance"
    assert "rank deficient" in fit_info["fit_error"]


def test_constant_potential_newton_uses_measured_residual_and_publishes_omega(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=8.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_initial=1.0 / 0.12,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        directory=tmp_path,
    )
    atoms.calc = calculator

    assert atoms.get_potential_energy() == pytest.approx(50.0)
    assert calculator.results["nelec"] == pytest.approx(10.0)
    assert calculator.results["potential_calc"] == pytest.approx(1.0)
    assert calculator.results["energy"] == pytest.approx(calculator.results["raw_energy"])
    assert calculator.results["cp_converged"] is True
    assert len(calculator.evaluation_history) == 2


def test_constant_potential_requires_an_explicit_initial_electron_guess(tmp_path):
    with pytest.raises(ValueError, match="initial_electrons is required"):
        ConstantPotentialCalculator(
            _factory,
            potential_v=1.0,
            reference_electrons=10.0,
            work_ref=4.6,
            work_ref_source="test",
            capacitance_unit="e/V",
            directory=tmp_path,
        )


def test_constant_potential_facts_survive_trajectory_and_stale_geometry_is_rejected(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=8.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_initial=1.0 / 0.12,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        directory=tmp_path / "success",
    )
    atoms.calc = calculator
    atoms.get_potential_energy()

    facts = read_constant_potential_facts(atoms)
    assert facts is not None
    assert facts["cp_converged"] is True
    assert facts["facts"]["energy"] == pytest.approx(calculator.results["energy"])

    trajectory = tmp_path / "cp.traj"
    write(trajectory, atoms)
    loaded = read(trajectory)
    assert read_constant_potential_facts(loaded) is not None
    loaded.positions[0, 0] += 0.1
    assert read_constant_potential_facts(loaded) is None

    # A failed follow-up evaluation clears the old envelope before doing any
    # backend work, so a failed geometry cannot masquerade as a prior result.
    calculator.set(max_iterations=1, potential_v=2.0)
    with pytest.raises(ConstantPotentialConvergenceError):
        atoms.get_potential_energy()
    assert CP_FACTS_INFO_KEY not in atoms.info


def test_constant_potential_facts_require_complete_consistent_state(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=8.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_initial=1.0 / 0.12,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        directory=tmp_path,
    )
    atoms.calc = calculator
    atoms.get_potential_energy()
    original = json.loads(json.dumps(atoms.info[CP_FACTS_INFO_KEY]))
    original_identity = json.loads(json.dumps(atoms.info[CP_IDENTITY_INFO_KEY]))

    for missing in ("energy", "scf_converged", "mu_calc", "mu_target", "residual_mu", "nelec", "forces", "cp_history"):
        payload = json.loads(json.dumps(original))
        payload["facts"].pop(missing)
        atoms.info[CP_FACTS_INFO_KEY] = payload
        assert read_constant_potential_facts(atoms) is None, missing

    payload = json.loads(json.dumps(original))
    payload["identity"].pop("energy_boundary")
    atoms.info[CP_FACTS_INFO_KEY] = payload
    assert read_constant_potential_facts(atoms) is None

    for field, offset in (("mu_target", 1.0), ("residual_mu", 1.0), ("nelec", 1.0), ("energy", 1.0), ("efermi", 1.0)):
        payload = json.loads(json.dumps(original))
        payload["facts"][field] += offset
        atoms.info[CP_FACTS_INFO_KEY] = payload
        assert read_constant_potential_facts(atoms) is None, field

    atoms.info[CP_FACTS_INFO_KEY] = original
    atoms.info[CP_IDENTITY_INFO_KEY] = original_identity
    assert read_constant_potential_facts(atoms) is not None


def test_constant_potential_facts_reject_corrupt_compensation_evidence():
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    identity = {
        "energy_boundary": "compensated_gate",
        "potential_v": None,
        "target_mu_ev": -15.0,
        "reference_electrode": "custom",
        "work_ref": None,
        "work_ref_source": None,
        "reference_pH": None,
        "temperature_K": None,
        "reference_electrons": 10.0,
        "boundary_parameters": {},
        "energy_definition": "omega_compensated_gate",
        "calculator": "constant_potential",
    }
    publish_constant_potential_facts(
        atoms,
        {
            "energy": 1.0,
            "free_energy": 1.0,
            "raw_energy": 1.0,
            "raw_free_energy": 1.0,
            "efermi": -15.8,
            "vacuum_level": None,
            "fermishift": None,
            "energy_boundary": "compensated_gate",
            "boundary_parameters": {},
            "compensation": {
                "boundary": "compensated_gate",
                "gate_derivative_ev": 0.4,
                "dipole_derivative_ev": 0.4,
                "compensation_derivative_ev": 0.8,
                "integrated_electrons": 10.0,
                "density_electron_error": 0.0,
                "ionic_valence_electrons": 10.0,
                "total_dipole_ry_au": 0.0,
                "density_precision": 12,
                "density_electron_tolerance": 1e-8,
            },
            "mu_calc": -15.0,
            "mu_target": -15.0,
            "potential_calc": None,
            "potential_target": None,
            "residual_mu": 0.0,
            "residual_v": 0.0,
            "omega_correction": 0.0,
            "nelec": 10.0,
            "reference_electrons": 10.0,
            "delta_nelec": 0.0,
            "forces": [[0.0, 0.0, 0.0]],
            "scf_converged": True,
            "cp_converged": True,
            "cp_iterations": 1,
            "cp_history": [{"converged": True}],
        },
        identity,
    )
    original = json.loads(json.dumps(atoms.info[CP_FACTS_INFO_KEY]))
    for mutation in ("boundary", "density_precision", "compensation_derivative_ev", "efermi", "omega_correction", "ionic_valence_electrons"):
        payload = json.loads(json.dumps(original))
        if mutation == "boundary":
            payload["facts"]["compensation"][mutation] = "reference_fcp"
        elif mutation == "density_precision":
            payload["facts"]["compensation"].pop(mutation)
        elif mutation == "efermi":
            payload["facts"][mutation] += 1.0
        elif mutation == "omega_correction":
            for key in ("omega_correction", "energy", "free_energy"):
                payload["facts"][key] += 1.0
        elif mutation == "ionic_valence_electrons":
            payload["facts"]["compensation"][mutation] += 1.0
        else:
            payload["facts"]["compensation"][mutation] = float("nan")
        atoms.info[CP_FACTS_INFO_KEY] = payload
        assert read_constant_potential_facts(atoms) is None, mutation
    atoms.info[CP_FACTS_INFO_KEY] = original
    assert read_constant_potential_facts(atoms) is not None


def test_constant_potential_applies_constraint_energy_and_force_once(tmp_path):
    class AdditiveConstraint:
        def adjust_potential_energy(self, atoms):
            return 2.0

        def adjust_forces(self, atoms, forces):
            forces[:, 0] += 0.5

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    atoms.set_constraint(AdditiveConstraint())
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=8.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_initial=1.0 / 0.12,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        directory=tmp_path,
    )
    atoms.calc = calculator

    assert atoms.get_potential_energy() == pytest.approx(52.0)
    np.testing.assert_allclose(atoms.get_forces(), [[0.5, 0.0, 0.0]])
    assert calculator.results["energy"] == pytest.approx(calculator.results["raw_energy"])


def test_constant_potential_does_not_publish_last_unconverged_state(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=2.0,
        reference_electrons=10.0,
        initial_electrons=8.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_initial=1.0,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        max_iterations=1,
        directory=tmp_path,
    )
    atoms.calc = calculator
    with pytest.raises(ConstantPotentialConvergenceError):
        atoms.get_potential_energy()
    assert "energy" not in calculator.results
    assert calculator.diagnostics["status"] == "failed"
    assert calculator.last_evaluation is not None


def test_constant_potential_rejects_missing_scf_convergence_evidence(tmp_path):
    class MissingStatus(QuadraticPotentialCalculator):
        def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
            super().calculate(atoms, properties, system_changes)
            self.results.pop("scf_converged", None)

    def factory(nelec, directory):
        return MissingStatus(nelec)

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_unit="e/V",
        capacitance_initial=1.0,
        directory=tmp_path,
    )
    atoms.calc = calculator
    with pytest.raises(ConstantPotentialEvaluationError, match="convergence evidence"):
        atoms.get_potential_energy()
    assert "energy" not in calculator.results
    assert calculator.diagnostics["status"] == "failed"


def test_constant_potential_accepts_the_lts_scf_success_marker(tmp_path):
    class LogStatus(QuadraticPotentialCalculator):
        def __init__(self, nelec, directory):
            super().__init__(nelec)
            self.directory = directory

        def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
            super().calculate(atoms, properties, system_changes)
            self.results.pop("scf_converged", None)
            output = Path(self.directory) / "OUT.ABACUS"
            output.mkdir(parents=True, exist_ok=True)
            (output / "running_scf.log").write_text(
                "charge density convergence is achieved\n", encoding="utf-8"
            )

    def factory(nelec, directory):
        return LogStatus(nelec, directory)

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_unit="e/V",
        directory=tmp_path,
    )
    atoms.calc = calculator
    atoms.get_potential_energy()
    assert calculator.results["cp_converged"] is True


def test_constant_potential_rejects_negative_candidate_electrons(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=-1.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_unit="e/V",
        capacitance_initial=1.0,
        directory=tmp_path,
    )
    atoms.calc = calculator
    with pytest.raises(ConstantPotentialConvergenceError, match="non-negative"):
        atoms.get_potential_energy()


def test_constant_potential_nspin_two_uses_total_band_capacity(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        directory=tmp_path,
    )
    assert calculator._validate_candidate(6.0, {"nbands": 5, "nspin": 2}) == pytest.approx(6.0)
    assert calculator._validate_candidate(100.0, {"nbands": 0, "nspin": 2}) == pytest.approx(100.0)
    with pytest.raises(ConstantPotentialConvergenceError, match="nbands capacity"):
        calculator._validate_candidate(11.0, {"nbands": 5, "nspin": 2})


def test_constant_potential_per_area_requires_a_real_cell(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=1.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        capacitance_unit="e/(V Angstrom^2)",
        directory=tmp_path,
    )
    atoms.calc = calculator
    with pytest.raises(ConstantPotentialEvaluationError, match="surface area"):
        atoms.get_potential_energy()
    assert calculator.diagnostics["status"] == "failed"


def test_constant_potential_batches_are_unique_across_instances(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    kwargs = {
        "potential_v": -0.2,
        "reference_electrons": 10.0,
        "initial_electrons": 10.0,
        "work_ref": 4.6,
        "work_ref_source": "test",
        "directory": tmp_path,
        "capacitance_unit": "e/V",
    }
    first = ConstantPotentialCalculator(_factory, **kwargs)
    atoms.calc = first
    atoms.get_potential_energy()
    first_directory = first.results["cp_history"][0]["directory"]

    second = ConstantPotentialCalculator(_factory, **kwargs)
    atoms.calc = second
    atoms.get_potential_energy()
    second_directory = second.results["cp_history"][0]["directory"]

    assert "/batch_0001/" in first_directory
    assert "/batch_0002/" in second_directory
    assert first_directory != second_directory


def test_constant_potential_rhe_conversion_is_recomputed_by_set(tmp_path):
    calculator = ConstantPotentialCalculator(
        _factory,
        potential_v=0.0,
        reference_electrons=10.0,
        initial_electrons=10.0,
        work_ref=4.6,
        work_ref_source="test",
        reference_electrode="RHE",
        reference_pH=7.0,
        temperature_K=298.15,
        capacitance_unit="e/V",
        directory=tmp_path,
    )
    correction = 8.617333262145e-5 * 298.15 * np.log(10.0) * 7.0
    assert calculator.work_ref == pytest.approx(4.6 - correction)
    calculator.set(work_ref=4.7)
    assert calculator.work_ref == pytest.approx(4.7 - correction)
    calculator.set(reference_electrode="SHE", reference_pH=None, temperature_K=None)
    assert calculator.work_ref == pytest.approx(4.7)


def test_constant_potential_factory_keeps_prepared_nelec_separate_from_n0(tmp_path):
    from atst_tools.calculators.factory import CalculatorFactory

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 8.5}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 1.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10.0,
            },
        }
    }

    calculator = CalculatorFactory.get_calculator("abacus", config, directory=tmp_path)

    assert calculator.reference_electrons == pytest.approx(10.0)
    assert calculator.initial_electrons == pytest.approx(8.5)
    assert calculator.constant_potential_identity["fixed_hamiltonian"]["parameters"]["out_pot"] == 2


@pytest.mark.parametrize(
    ("workflow", "boundary"),
    [
        ("autoneb", "reference_fcp"),
        ("autoneb", "compensated_gate"),
        ("d2s", "reference_fcp"),
        ("d2s", "compensated_gate"),
    ],
)
def test_constant_potential_factory_rejects_unsupported_workflows(tmp_path, workflow, boundary):
    from atst_tools.calculators.factory import CalculatorFactory

    constant_potential = {
        "energy_boundary": boundary,
        "reference_electrons": 10.0,
    }
    if boundary == "reference_fcp":
        constant_potential.update(
            {"potential_v": 1.0, "work_ref": 4.6, "work_ref_source": "fixture"}
        )
    else:
        constant_potential.update(
            {"target_mu_ev": -15.0, "reference_electrode": "custom"}
        )
    config = {
        "calculation": {"type": workflow},
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 8.5}},
            "constant_potential": constant_potential,
        },
    }
    with pytest.raises(ValueError, match="supported only"):
        CalculatorFactory.get_calculator("abacus", config, directory=tmp_path)


def test_compensated_gate_uses_density_conjugate_mu_and_raw_forces(tmp_path, monkeypatch):
    class GateCalculator(Calculator):
        implemented_properties = ["energy", "free_energy", "forces"]

        def __init__(self, nelec):
            super().__init__()
            self.nelec = float(nelec)

        def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
            super().calculate(atoms, properties, system_changes)
            self.results.update(
                {
                    "energy": 0.5 * self.nelec**2,
                    "free_energy": 0.5 * self.nelec**2,
                    "forces": np.ones((len(atoms), 3)) * 0.37,
                    "efermi": 2.0 + 0.1 * self.nelec,
                    "scf_converged": True,
                }
            )

    calls = []

    def compensation(directory, nelec, reference_electrons):
        calls.append((Path(directory), nelec, reference_electrons))
        return {
            "boundary": "compensated_gate",
            "compensation_derivative_ev": 0.8,
            "gate_derivative_ev": 0.4,
            "dipole_derivative_ev": 0.4,
            "integrated_electrons": float(nelec),
            "density_electron_error": 0.0,
            "ionic_valence_electrons": float(reference_electrons),
            "total_dipole_ry_au": 0.0,
            "density_precision": 12,
            "density_electron_tolerance": 1e-8,
        }

    monkeypatch.setattr(
        "atst_tools.utils.gate_compensation.read_gate_compensation",
        compensation,
    )
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    calculator = ConstantPotentialCalculator(
        lambda nelec, directory: GateCalculator(nelec),
        potential_v=None,
        reference_electrons=10.0,
        initial_electrons=8.0,
        energy_boundary="compensated_gate",
        target_mu_ev=3.8,
        reference_electrode="custom",
        capacitance_initial=10.0,
        capacitance_unit="e/V",
        potential_tolerance_v=1e-12,
        directory=tmp_path,
    )
    atoms.calc = calculator

    assert atoms.get_potential_energy() == pytest.approx(50.0)
    np.testing.assert_allclose(calculator.results["forces"], np.ones((1, 3)) * 0.37)
    assert calculator.results["energy_boundary"] == "compensated_gate"
    assert calculator.results["mu_calc"] == pytest.approx(3.8)
    assert calculator.results["vacuum_level"] is None
    assert calculator.results["potential_calc"] is None
    assert calculator.results["energy"] == pytest.approx(calculator.results["raw_energy"])
    assert len(calls) == 2


def test_compensated_gate_factory_requests_high_precision_density_without_overwriting_geometry(tmp_path, monkeypatch):
    from atst_tools.calculators import factory

    captured = {}

    def fake_backend(config, **kwargs):
        captured["config"] = config
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(factory.AbacusFactory, "get_calculator", fake_backend)
    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {
                "parameters": {
                    "nelec": 8.5,
                    "gate_flag": 1,
                    "zgate": 0.7,
                    "efield_flag": 1,
                    "dip_cor_flag": 1,
                    "efield_pos_max": 0.8,
                    "efield_pos_dec": 0.1,
                }
            },
            "constant_potential": {
                "energy_boundary": "compensated_gate",
                "target_mu_ev": -15.0,
                "reference_electrode": "custom",
                "reference_electrons": 10.0,
            },
        }
    }
    calculator = factory.CalculatorFactory.get_calculator("abacus", config, directory=tmp_path)
    calculator.inner_factory(8.5, str(tmp_path / "evaluation"))

    parameters = captured["config"]["calculator"]["abacus"]["parameters"]
    assert parameters["out_chg"] == "1 12"
    assert parameters["zgate"] == pytest.approx(0.7)
    assert parameters["efield_pos_max"] == pytest.approx(0.8)
    assert parameters["efield_pos_dec"] == pytest.approx(0.1)
    assert "constant_potential" not in captured["config"]["calculator"]
    assert "out_chg" not in config["calculator"]["abacus"]["parameters"]


def test_constant_potential_schema_is_strict_and_requires_explicit_calibration():
    base = {
        "calculation": {"type": "constant_potential", "init_structure": "input.xyz"},
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 10}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 1.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
            },
        },
    }
    normalized = ConfigLoader.normalize(base)
    assert normalized["calculator"]["constant_potential"]["reference_electrons"] == 10.0
    missing_boundary = {
        **base,
        "calculator": {
            **base["calculator"],
            "constant_potential": {
                key: value
                for key, value in base["calculator"]["constant_potential"].items()
                if key != "energy_boundary"
            },
        },
    }
    with pytest.raises(ValueError, match="energy_boundary"):
        ConfigLoader.validate(missing_boundary)
    with pytest.raises(ValueError, match="exactly one"):
        ConfigLoader.validate(
            {**base, "calculator": {**base["calculator"], "constant_potential": {**base["calculator"]["constant_potential"], "potentials_v": [1.0]}}}
        )
    with pytest.raises(ValueError, match="work_ref_source"):
        ConfigLoader.validate(
            {**base, "calculator": {**base["calculator"], "constant_potential": {"energy_boundary": "reference_fcp", "potential_v": 1.0, "work_ref": 4.6, "reference_electrons": 10}}}
        )
    with pytest.raises(ValueError, match="unknown"):
        ConfigLoader.validate(
            {**base, "calculator": {**base["calculator"], "constant_potential": {**base["calculator"]["constant_potential"], "unknown": 1}}}
        )
    missing_n0 = {
        **base,
        "calculator": {
            **base["calculator"],
            "constant_potential": {
                key: value
                for key, value in base["calculator"]["constant_potential"].items()
                if key != "reference_electrons"
            },
        },
    }
    with pytest.raises(ValueError, match="reference_electrons"):
        ConfigLoader.validate(missing_n0)
    with pytest.raises(ValueError, match="finite"):
        ConfigLoader.validate(
            {
                **base,
                "calculator": {
                    **base["calculator"],
                    "constant_potential": {
                        **base["calculator"]["constant_potential"],
                        "potential_v": float("nan"),
                    },
                },
            }
        )
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        ConfigLoader.validate(
            {
                **base,
                "calculator": {
                    **base["calculator"],
                    "constant_potential": {
                        **base["calculator"]["constant_potential"],
                        "reference_electrons": -1,
                    },
                },
            }
        )
    with pytest.raises(ValueError, match="blank"):
        ConfigLoader.validate(
            {
                **base,
                "calculator": {
                    **base["calculator"],
                    "constant_potential": {
                        **base["calculator"]["constant_potential"],
                        "work_ref_source": " ",
                    },
                },
            }
        )


def test_constant_potential_rejects_explicit_nupdown_even_when_zero(tmp_path):
    from atst_tools.calculators.factory import CalculatorFactory
    from atst_tools.utils.abacus_io import prepare_abacus_input_from_config

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 8.5, "nupdown": 0}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 1.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10.0,
            },
        }
    }
    with pytest.raises(ValueError, match="nupdown"):
        ConfigLoader.validate({**config, "calculation": {"type": "constant_potential", "init_structure": "input.xyz"}})
    with pytest.raises(ValueError, match="nupdown"):
        CalculatorFactory.get_calculator("abacus", config, directory=tmp_path)
    with pytest.raises(ValueError, match="nupdown"):
        prepare_abacus_input_from_config(
            config,
            str(tmp_path / "missing.stru"),
            str(tmp_path / "preflight"),
        )


def test_constant_potential_checkpoint_hashes_fixed_assets_and_validates_points(tmp_path):
    structure = tmp_path / "input.xyz"
    structure.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")
    pseudo = tmp_path / "H.upf"
    orbital = tmp_path / "H.orb"
    pseudo.write_text("pseudo-v1\n", encoding="utf-8")
    orbital.write_text("orbital-v1\n", encoding="utf-8")
    config = {
        "calculation": {
            "type": "constant_potential",
            "init_structure": str(structure),
            "restart": False,
            "checkpoint_file": str(tmp_path / "checkpoint.json"),
        },
        "calculator": {
            "name": "abacus",
            "abacus": {
                "pseudo_dir": str(tmp_path),
                "orbital_dir": str(tmp_path),
                "pseudopotentials": {"H": "H.upf"},
                "basissets": {"H": "H.orb"},
                "kpts": [1, 1, 1],
                "parameters": {"nelec": 10},
            },
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 0.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
            },
        },
    }
    normalized = ConfigLoader.normalize(config)
    workflow = ConstantPotentialWorkflow(normalized, "abacus", normalized["calculation"])
    identity_v1 = constant_potential_identity_for_config(normalized, target=0.0)
    assert identity_v1 is not None
    assert identity_v1["fixed_hamiltonian"]["assets"]["pseudopotentials"][0]["sha256"]
    config_zgate = json.loads(json.dumps(normalized))
    config_zgate["calculator"]["abacus"]["parameters"]["zgate"] = 0.8
    identity_zgate = constant_potential_identity_for_config(config_zgate, target=0.0)
    assert identity_zgate != identity_v1
    workflow._write_checkpoint([], None)
    assert workflow._checkpoint_identity()["fixed_assets"]["pseudopotentials"][0]["sha256"]
    pseudo.write_text("pseudo-v2\n", encoding="utf-8")
    restarted = ConstantPotentialWorkflow(
        {**normalized, "calculation": {**normalized["calculation"], "restart": True}},
        "abacus",
        {**normalized["calculation"], "restart": True},
    )
    with pytest.raises(ValueError, match="identity"):
        restarted._load_checkpoint()

    valid_identity = constant_potential_identity_for_config(
        {"constant_potential": normalized["calculator"]["constant_potential"]}, target=0.0
    )
    point = {
        "index": 0,
        "potential_v": 0.0,
        "nelec": 10.0,
        "energy": 1.0,
        "raw_energy": 1.0,
        "free_energy": 1.0,
        "raw_free_energy": 1.0,
        "forces": [[0.0, 0.0, 0.0]],
        "residual_v": 0.0,
        "cp_converged": True,
        "cp_identity": valid_identity,
    }
    # Restore the asset and write a structurally valid point before testing
    # the independent finite/shape guards.
    pseudo.write_text("pseudo-v1\n", encoding="utf-8")
    workflow._write_checkpoint([point], 10.0)
    restored = ConstantPotentialWorkflow(
        {**normalized, "calculation": {**normalized["calculation"], "restart": True}},
        "abacus",
        {**normalized["calculation"], "restart": True},
    )
    assert len(restored._load_checkpoint()) == 1
    point["forces"] = [[float("nan"), 0.0, 0.0]]
    workflow._write_checkpoint([point], 10.0)
    with pytest.raises(ValueError, match="forces"):
        restored._load_checkpoint()


def test_constant_potential_asset_identity_survives_directory_move(tmp_path):
    source_assets = tmp_path / "assets-source"
    moved_assets = tmp_path / "assets-moved"
    source_assets.mkdir()
    moved_assets.mkdir()
    for name, contents in (("H.upf", "pseudo-v1\n"), ("H.orb", "orbital-v1\n")):
        (source_assets / name).write_text(contents, encoding="utf-8")
        (moved_assets / name).write_text(contents, encoding="utf-8")

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {
                "pseudo_dir": str(source_assets),
                "orbital_dir": str(source_assets),
                "pseudopotentials": {"H": "H.upf"},
                "basissets": {"H": "H.orb"},
                "parameters": {"nelec": 10},
            },
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 0.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
            },
        }
    }
    moved = json.loads(json.dumps(config))
    moved["calculator"]["abacus"]["pseudo_dir"] = str(moved_assets)
    moved["calculator"]["abacus"]["orbital_dir"] = str(moved_assets)
    identity_source = constant_potential_identity_for_config(config, target=0.0)
    identity_moved = constant_potential_identity_for_config(moved, target=0.0)
    assert identity_source is not None and identity_moved is not None
    source_asset = identity_source["fixed_hamiltonian"]["assets"]["pseudopotentials"][0]
    moved_asset = identity_moved["fixed_hamiltonian"]["assets"]["pseudopotentials"][0]
    assert source_asset["sha256"] == moved_asset["sha256"]
    assert source_asset["provenance"]["path"] != moved_asset["provenance"]["path"]

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    publish_constant_potential_facts(
        atoms,
        {
            "energy": 1.0,
            "free_energy": 1.0,
            "raw_energy": 1.0,
            "raw_free_energy": 1.0,
            "efermi": -4.6,
            "vacuum_level": 0.0,
            "fermishift": 0.0,
            "energy_boundary": "reference_fcp",
            "boundary_parameters": identity_source["boundary_parameters"],
            "compensation": None,
            "mu_calc": -4.6,
            "mu_target": -4.6,
            "potential_calc": 0.0,
            "potential_target": 0.0,
            "residual_mu": 0.0,
            "residual_v": 0.0,
            "omega_correction": 0.0,
            "nelec": 10.0,
            "reference_electrons": 10.0,
            "delta_nelec": 0.0,
            "forces": [[0.0, 0.0, 0.0]],
            "scf_converged": True,
            "cp_converged": True,
            "cp_iterations": 1,
            "cp_history": [{"converged": True}],
        },
        identity_source,
    )
    assert constant_potential_identity_matches(atoms, identity_moved)

    (moved_assets / "H.upf").write_text("pseudo-v2\n", encoding="utf-8")
    identity_changed = constant_potential_identity_for_config(moved, target=0.0)
    assert identity_changed is not None
    assert not constant_potential_identity_matches(atoms, identity_changed)

    missing = json.loads(json.dumps(config))
    missing["calculator"]["abacus"]["pseudopotentials"]["H"] = "missing.upf"
    with pytest.raises(ValueError, match="missing or unreadable"):
        fixed_hamiltonian_identity_for_config(missing)


def test_compensated_gate_schema_requires_custom_mu_targets_and_is_rejected_for_legacy_p1():
    base = {
        "calculation": {"type": "constant_potential", "init_structure": "input.xyz"},
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 10}},
            "constant_potential": {
                "energy_boundary": "compensated_gate",
                "target_mu_ev": -15.0,
                "reference_electrode": "custom",
                "reference_electrons": 10,
            },
        },
    }
    assert ConfigLoader.validate(base)
    with pytest.raises(ValueError, match="custom"):
        ConfigLoader.validate(
            {
                **base,
                "calculator": {
                    **base["calculator"],
                    "constant_potential": {
                        **base["calculator"]["constant_potential"],
                        "reference_electrode": "SHE",
                    },
                },
            }
        )
    with pytest.raises(ValueError, match="not valid"):
        ConfigLoader.validate(
            {
                **base,
                "calculator": {
                    **base["calculator"],
                    "constant_potential": {
                        **base["calculator"]["constant_potential"],
                        "potential_v": 0.0,
                    },
                },
            }
        )
    relax = {
        **base,
        "calculation": {"type": "relax", "init_structure": "input.xyz"},
    }
    assert ConfigLoader.validate(relax)
    legacy_relax = {
        **relax,
        "calculator": {
            **relax["calculator"],
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 0.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
            },
        },
    }
    with pytest.raises(ValueError, match="validated.*compensated_gate"):
        ConfigLoader.validate(legacy_relax)
    from atst_tools.calculators.factory import CalculatorFactory

    with pytest.raises(ValueError, match="requires energy_boundary=compensated_gate"):
        CalculatorFactory.get_calculator("abacus", legacy_relax)


def test_scan_analysis_requires_a_bracket_for_pzc():
    result = analyze_potential_scan(
        [{"potential_v": 0.0, "nelec": 9.0}, {"potential_v": 1.0, "nelec": 8.0}],
        reference_electrons=10.0,
        area_A2=10.0,
    )
    assert result["capacitance"] == pytest.approx(0.1)
    assert result["pzc_v"] is None
    assert result["identifiable"] is False


def test_scan_analysis_compensated_mu_reports_positive_electron_response():
    result = analyze_potential_scan(
        [
            {"target_mu_ev": 0.0, "nelec": 10.0},
            {"target_mu_ev": 1.0, "nelec": 11.0},
        ],
        reference_electrons=10.0,
        area_A2=10.0,
        coordinate="target_mu_ev",
    )
    assert result["coordinate"] == "target_mu_ev"
    assert result["capacitance"] == pytest.approx(0.1)
    assert result["capacitance_unit"] == "e^2/(eV Angstrom^2)"
    assert result["zero_charge_mu_ev"] == pytest.approx(0.0)
    assert result["pzc_v"] is None
    assert result["fit"]["slope_e2_per_ev"] == pytest.approx(1.0)


def test_constant_potential_workflow_serial_scan_writes_points_and_manifest(tmp_path, monkeypatch):
    structure = tmp_path / "input.xyz"
    structure.write_text(
        '1\nLattice="10 0 0 0 10 0 0 0 10" Properties=species:S:1:pos:R:3 pbc="T T T"\n'
        "H 0 0 0\n",
        encoding="utf-8",
    )
    config = {
        "calculation": {
            "type": "constant_potential",
            "init_structure": str(structure),
            "directory": str(tmp_path / "run"),
            "results_file": str(tmp_path / "scan.json"),
            "log_file": str(tmp_path / "scan.log"),
            "checkpoint_file": str(tmp_path / "checkpoint.json"),
            "artifact_manifest": str(tmp_path / "manifest.json"),
        },
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 10}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potentials_v": [0.0, 1.0],
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
                "potential_tolerance_v": 1e-10,
                "capacitance_initial": 1.0 / 0.12,
                "capacitance_unit": "e/V",
            },
        },
    }
    normalized = ConfigLoader.normalize(config)

    def fake_factory(name, local_config, **kwargs):
        target = float(kwargs["constant_potential_target"])
        initial = float(kwargs.get("constant_potential_initial", 10.0))
        # Make each target converge at N_e=10 with a target-dependent Fermi
        # offset, while keeping the same finite-difference response.
        class TargetCalculator(QuadraticPotentialCalculator):
            def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
                super().calculate(atoms, properties, system_changes)
                self.results["efermi"] = 5.4 - target + 0.12 * (self.nelec - 10.0)

        def backend(nelec, directory):
            return TargetCalculator(nelec)

        calculator = ConstantPotentialCalculator(
            backend,
            potential_v=target,
            reference_electrons=10.0,
            initial_electrons=initial,
            work_ref=4.6,
            work_ref_source="fixture",
            capacitance_initial=1.0 / 0.12,
            capacitance_unit="e/V",
            potential_tolerance_v=1e-10,
            directory=kwargs["directory"],
        )
        calculator.inner_factory = backend
        return calculator

    monkeypatch.setattr(
        "atst_tools.workflows.constant_potential.CalculatorFactory.get_calculator",
        fake_factory,
    )
    workflow = ConstantPotentialWorkflow(normalized, "abacus", normalized["calculation"])
    workflow.run()
    payload = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "complete"
    assert len(payload["points"]) == 2
    assert manifest["workflow"] == "constant_potential"
    assert {stage["name"] for stage in manifest["stages"]} >= {"potential_0000", "potential_0001"}
    assert any(item["role"] == "final_structure" for item in manifest["artifacts"])


def test_compensated_gate_workflow_scan_keeps_mu_targets_and_boundary_facts(tmp_path, monkeypatch):
    structure = tmp_path / "input.xyz"
    structure.write_text(
        '1\nLattice="10 0 0 0 10 0 0 0 10" Properties=species:S:1:pos:R:3 pbc="T T T"\n'
        "H 0 0 0\n",
        encoding="utf-8",
    )
    config = {
        "calculation": {
            "type": "constant_potential",
            "init_structure": str(structure),
            "directory": str(tmp_path / "run"),
            "results_file": str(tmp_path / "scan.json"),
            "log_file": str(tmp_path / "scan.log"),
            "checkpoint_file": str(tmp_path / "checkpoint.json"),
            "artifact_manifest": str(tmp_path / "manifest.json"),
        },
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 8.0}},
            "constant_potential": {
                "energy_boundary": "compensated_gate",
                "target_mu_values_ev": [3.8, 3.9],
                "reference_electrode": "custom",
                "reference_electrons": 10,
                "capacitance_initial": 10.0,
                "capacitance_unit": "e/V",
                "potential_tolerance_v": 1e-10,
            },
        },
    }
    normalized = ConfigLoader.normalize(config)

    def fake_compensation(directory, nelec, reference_electrons):
        return {
            "boundary": "compensated_gate",
            "gate_derivative_ev": 0.8,
            "dipole_derivative_ev": 0.0,
            "compensation_derivative_ev": 0.8,
            "integrated_electrons": float(nelec),
            "density_electron_error": 0.0,
            "ionic_valence_electrons": float(reference_electrons),
            "total_dipole_ry_au": 0.0,
            "density_precision": 12,
            "density_electron_tolerance": 1e-8,
        }

    monkeypatch.setattr(
        "atst_tools.utils.gate_compensation.read_gate_compensation",
        fake_compensation,
    )

    def fake_factory(name, local_config, **kwargs):
        target = float(kwargs["constant_potential_target"])
        initial = float(kwargs.get("constant_potential_initial", 8.0))

        class TargetCalculator(QuadraticPotentialCalculator):
            def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
                super().calculate(atoms, properties, system_changes)
                self.results["efermi"] = target - 0.8 + 0.1 * (self.nelec - 10.0)

        return ConstantPotentialCalculator(
            lambda nelec, directory: TargetCalculator(nelec),
            potential_v=None,
            reference_electrons=10.0,
            initial_electrons=initial,
            energy_boundary="compensated_gate",
            target_mu_ev=target,
            reference_electrode="custom",
            capacitance_initial=10.0,
            capacitance_unit="e/V",
            potential_tolerance_v=1e-10,
            directory=kwargs["directory"],
        )

    monkeypatch.setattr(
        "atst_tools.workflows.constant_potential.CalculatorFactory.get_calculator",
        fake_factory,
    )
    ConstantPotentialWorkflow(normalized, "abacus", normalized["calculation"]).run()
    payload = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    assert payload["energy_boundary"] == "compensated_gate"
    assert payload["target_mu_values_ev"] == [3.8, 3.9]
    assert [point["target_mu_ev"] for point in payload["points"]] == [3.8, 3.9]
    assert all(point["energy_boundary"] == "compensated_gate" for point in payload["points"])


def test_constant_potential_workflow_checkpoint_resume_keeps_completed_points(tmp_path, monkeypatch):
    structure = tmp_path / "input.xyz"
    structure.write_text(
        '1\nLattice="10 0 0 0 10 0 0 0 10" Properties=species:S:1:pos:R:3 pbc="T T T"\n'
        "H 0 0 0\n",
        encoding="utf-8",
    )
    config = {
        "calculation": {
            "type": "constant_potential",
            "init_structure": str(structure),
            "directory": str(tmp_path / "run"),
            "results_file": str(tmp_path / "scan.json"),
            "log_file": str(tmp_path / "scan.log"),
            "checkpoint_file": str(tmp_path / "checkpoint.json"),
            "artifact_manifest": str(tmp_path / "manifest.json"),
        },
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 10}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potentials_v": [0.0, 1.0],
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
                "potential_tolerance_v": 1e-10,
                "capacitance_initial": 1.0 / 0.12,
                "capacitance_unit": "e/V",
            },
        },
    }
    normalized = ConfigLoader.normalize(config)
    calls = []
    fail_targets = {1.0}

    def fake_factory(name, local_config, **kwargs):
        target = float(kwargs["constant_potential_target"])
        calls.append(target)
        if target in fail_targets:
            raise RuntimeError("injected backend failure")
        initial = float(kwargs.get("constant_potential_initial", 10.0))

        class TargetCalculator(QuadraticPotentialCalculator):
            def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
                super().calculate(atoms, properties, system_changes)
                self.results["efermi"] = 5.4 - target + 0.12 * (self.nelec - 10.0)

        return ConstantPotentialCalculator(
            lambda nelec, directory: TargetCalculator(nelec),
            potential_v=target,
            reference_electrons=10.0,
            initial_electrons=initial,
            work_ref=4.6,
            work_ref_source="fixture",
            capacitance_initial=1.0 / 0.12,
            capacitance_unit="e/V",
            potential_tolerance_v=1e-10,
            directory=kwargs["directory"],
        )

    monkeypatch.setattr(
        "atst_tools.workflows.constant_potential.CalculatorFactory.get_calculator",
        fake_factory,
    )
    workflow = ConstantPotentialWorkflow(normalized, "abacus", normalized["calculation"])
    with pytest.raises(RuntimeError, match="injected backend failure"):
        workflow.run()
    assert calls == [0.0, 1.0]
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert len(checkpoint["points"]) == 1

    fail_targets.clear()
    resumed_config = {**normalized, "calculation": {**normalized["calculation"], "restart": True}}
    resumed = ConstantPotentialWorkflow(resumed_config, "abacus", resumed_config["calculation"])
    resumed.run()
    assert calls == [0.0, 1.0, 1.0]
    payload = json.loads((tmp_path / "scan.json").read_text())
    assert payload["status"] == "complete"
    assert [point["index"] for point in payload["points"]] == [0, 1]

    changed = {
        **resumed_config,
        "calculator": {
            **resumed_config["calculator"],
            "constant_potential": {
                **resumed_config["calculator"]["constant_potential"],
                "potentials_v": [0.0, 0.5],
            },
        },
    }
    with pytest.raises(ValueError, match="identity"):
        ConstantPotentialWorkflow(changed, "abacus", changed["calculation"]).run()


def test_constant_potential_api_dispatch_returns_versioned_result(tmp_path, monkeypatch):
    structure = tmp_path / "input.xyz"
    structure.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")
    config = {
        "calculation": {
            "type": "constant_potential",
            "init_structure": str(structure),
            "directory": str(tmp_path / "run"),
            "results_file": str(tmp_path / "result.json"),
            "log_file": str(tmp_path / "result.log"),
            "artifact_manifest": str(tmp_path / "manifest.json"),
        },
        "calculator": {
            "name": "abacus",
            "abacus": {"parameters": {"nelec": 10}},
            "constant_potential": {
                "energy_boundary": "reference_fcp",
                "potential_v": 1.0,
                "work_ref": 4.6,
                "work_ref_source": "fixture",
                "reference_electrons": 10,
                "potential_tolerance_v": 1e-10,
                "capacitance_initial": 1.0 / 0.12,
                "capacitance_unit": "e/V",
            },
        },
    }

    def fake_factory(name, local_config, **kwargs):
        return ConstantPotentialCalculator(
            _factory,
            potential_v=float(kwargs["constant_potential_target"]),
            reference_electrons=10.0,
            initial_electrons=float(kwargs.get("constant_potential_initial", 8.0)),
            work_ref=4.6,
            work_ref_source="fixture",
            capacitance_initial=1.0 / 0.12,
            capacitance_unit="e/V",
            potential_tolerance_v=1e-10,
            directory=kwargs["directory"],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "atst_tools.workflows.constant_potential.CalculatorFactory.get_calculator",
        fake_factory,
    )
    result = run_workflow(config, RunOptions())
    document = result.to_document(tmp_path)
    assert result.workflow == "constant_potential"
    assert result.status == "complete"
    assert document["schema"] == "atst-api-result-v1"
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["workflow"] == "constant_potential"
