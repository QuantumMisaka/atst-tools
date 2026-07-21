import json

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import write


class DoubleWellCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        x, y, z = [float(v) for v in atoms.get_positions()[0]]
        energy = (x * x - 0.5) ** 2 + 0.5 * (y * y + z * z)
        d_v_dx = 4.0 * x * (x * x - 0.5)
        self.results["energy"] = energy
        self.results["forces"] = np.array([[-d_v_dx, -y, -z]], dtype=float)

    def get_hessian(self, atoms):
        x = float(atoms.get_positions()[0, 0])
        return np.diag([12.0 * x * x - 2.0, 1.0, 1.0]).astype(float)


def test_parse_reactive_bonds_accepts_1based_string_and_deduplicates():
    from atst_tools.mep.ccqn import parse_reactive_bonds

    assert parse_reactive_bonds("2-1,1-2,3-4", natoms=4) == [(0, 1), (2, 3)]


def test_parse_reactive_bonds_rejects_out_of_range():
    from atst_tools.mep.ccqn import parse_reactive_bonds

    with pytest.raises(ValueError, match="out of range"):
        parse_reactive_bonds([[1, 5]], natoms=4)


def test_ic_e_vector_follows_force_projected_reactive_bond_direction():
    from atst_tools.mep.ccqn import ccqn_ic_e_vector

    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    forces = np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]])

    e_vec = ccqn_ic_e_vector(atoms, forces, [(0, 1)], ic_mode="democratic")

    expected = np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]) / np.sqrt(2)
    np.testing.assert_allclose(e_vec.reshape(2, 3), expected)


def test_interp_e_vector_uses_mic_direction_to_product():
    from atst_tools.mep.ccqn import ccqn_interp_e_vector

    atoms = Atoms("H", positions=[[9.5, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    product = Atoms("H", positions=[[0.5, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)

    e_vec = ccqn_interp_e_vector(atoms, product)

    np.testing.assert_allclose(e_vec, [1.0, 0.0, 0.0])


def test_ccqn_convergence_requires_prfo_mode():
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms = Atoms("H", positions=[[-np.sqrt(0.5), 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    atoms.calc = DoubleWellCalculator()
    product = Atoms("H", positions=[[np.sqrt(0.5), 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    opt = CCQNOptimizer(atoms, e_vector_method="interp", product_atoms=product, hessian=True, logfile=None)
    opt.fmax = 0.05

    forces = atoms.get_forces()
    assert opt.mode == "uphill"
    assert not opt.converged(forces)
    opt.mode = "prfo"
    assert opt.converged(forces)


def test_ccqn_can_accept_initial_converged_ts_when_requested():
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    atoms.calc = DoubleWellCalculator()
    product = Atoms("H", positions=[[1.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)

    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        hessian=True,
        logfile=None,
        accept_initial_converged=True,
    )
    opt.fmax = 0.05

    assert opt.mode == "prfo"
    assert opt.converged(atoms.get_forces())


def test_d2s_ccqn_uses_local_neb_reference(monkeypatch, tmp_path):
    from atst_tools.workflows import d2s

    calls = []

    class FakeCCQN:
        def __init__(self, init_Atoms, config, calc_name, calc_config, product_atoms=None, **kwargs):
            calls.append(
                {
                    "calc_name": calc_name,
                    "positions": init_Atoms.get_positions().copy(),
                    "product": product_atoms.get_positions().copy(),
                    "trajectory": kwargs["traj_file"],
                    "method": calc_config["e_vector_method"],
                }
            )

        def run(self):
            return None

    chain = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[0.5, 0.0, 0.0]]),
        Atoms("H", positions=[[1.0, 0.0, 0.0]]),
    ]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d2s, "AbacusCCQN", FakeCCQN)

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "d2s", "method": "ccqn", "init_file": "i.traj", "final_file": "f.traj"},
    )

    result = workflow.run_single_ended(chain, 1, chain[1].copy())

    assert result == "ccqn.traj"
    assert calls[0]["calc_name"] == "abacus"
    np.testing.assert_allclose(calls[0]["positions"], [[0.5, 0.0, 0.0]])
    np.testing.assert_allclose(calls[0]["product"], [[1.0, 0.0, 0.0]])
    assert calls[0]["method"] == "interp"


def test_reactive_modes_enumerates_ranked_molecule_surface_pairs():
    from atst_tools.utils.reactive_modes import enumerate_reactive_bond_modes

    atoms = Atoms("HOPt2", positions=[[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [0.8, 0.0, 0.0], [4.5, 0.0, 0.0]])

    modes = enumerate_reactive_bond_modes(
        atoms,
        molecule_indices=[1, 2],
        active_molecule_indices=[1],
        active_catalyst_indices=[3, 4],
        cutoff_A=2.0,
    )

    assert modes[0]["reactive_bonds"] == [(0, 2)]
    assert modes[0]["reactive_bonds_1based"] == [[1, 3]]
    assert modes[0]["distance_A"] == pytest.approx(0.8)


def test_abacus_ccqn_aligns_product_and_writes_mode_outputs(monkeypatch, tmp_path):
    from atst_tools.mep import ccqn

    init = Atoms("HO", positions=[[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    product = Atoms("OH", positions=[[6.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    product_path = tmp_path / "product.traj"
    write(product_path, product)
    selected = {}

    class FakeOptimizer:
        def __init__(self, atoms, **kwargs):
            selected.update(kwargs)

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ccqn.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DoubleWellCalculator())
    monkeypatch.setattr(ccqn, "CCQNOptimizer", FakeOptimizer)

    runner = ccqn.AbacusCCQN(
        init.copy(),
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "ccqn",
            "e_vector_method": "ic",
            "product_file": str(product_path),
            "align_product_indices": True,
            "auto_reactive_bonds": {
                "enabled": True,
                "molecule_indices": [1],
                "active_catalyst_indices": [2],
                "cutoff_A": 10.0,
            },
            "mode_manifest": "ccqn_mode_manifest.json",
            "diagnostics_file": "ccqn_diagnostics.json",
            "max_steps": 1,
            "final_structure": None,
        },
    )
    runner.run()

    assert selected["reactive_bonds"] == [(0, 1)]
    np.testing.assert_allclose(selected["product_atoms"].get_positions(), [[1.0, 0.0, 0.0], [6.0, 0.0, 0.0]])
    manifest = json.loads((tmp_path / "ccqn_mode_manifest.json").read_text(encoding="utf-8"))
    assert manifest["selected_mode"]["reactive_bonds_1based"] == [[1, 2]]
    assert selected["diagnostics_file"] == "ccqn_diagnostics.json"


def test_ccqn_optimizer_writes_json_diagnostics(tmp_path):
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms = Atoms("H", positions=[[0.1, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    atoms.calc = DoubleWellCalculator()
    product = Atoms("H", positions=[[1.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    diagnostics = tmp_path / "diag.json"

    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        hessian=True,
        logfile=None,
        diagnostics_file=str(diagnostics),
    )
    opt.step()

    data = json.loads(diagnostics.read_text(encoding="utf-8"))
    assert data["schema_version"] == "atst-ccqn-diagnostics-v1"
    assert data["steps"][0]["mode"] in {"uphill", "prfo"}
    assert "min_eigenvalue" in data["steps"][0]


def test_ccqn_accepts_injected_calculator_without_factory(monkeypatch, tmp_path):
    """An embedded caller owns the calculator and the original atoms."""
    from helpers import DummyCalc
    from atst_tools.mep.ccqn import AbacusCCQN

    atoms = Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]])
    calculator = DummyCalc()
    monkeypatch.setattr(
        "atst_tools.mep.ccqn.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: pytest.fail("factory used"),
    )
    monkeypatch.setattr("atst_tools.mep.ccqn.CCQNOptimizer.run", lambda self, **kwargs: None)

    result = AbacusCCQN(
        atoms,
        {},
        "abacus",
        {
            "artifact_manifest": str(tmp_path / "manifest.json"),
            "reactive_bonds": "1-2",
        },
        calculator=calculator,
    ).run()

    assert result.calc is calculator
    assert atoms.calc is None


@pytest.fixture
def abacuslite_compatible_calculator():
    """Return a lightweight ASE calculator accepted by the abacuslite path."""
    from helpers import DummyCalc

    return DummyCalc()


def test_ccqn_uses_supplied_abacuslite_compatible_calculator(
    monkeypatch, tmp_path, abacuslite_compatible_calculator
):
    """Injection preserves calculator identity and bypasses factory construction."""
    from atst_tools.mep.ccqn import AbacusCCQN

    atoms = Atoms("H2", positions=[[0, 0, 0], [0.8, 0, 0]])
    optimizer_atoms = []

    class FakeOptimizer:
        def __init__(self, optimizer_input, **kwargs):
            optimizer_atoms.append(optimizer_input)

        def run(self, **kwargs):
            return None

    monkeypatch.setattr(
        "atst_tools.mep.ccqn.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: pytest.fail("factory used"),
    )
    monkeypatch.setattr("atst_tools.mep.ccqn.CCQNOptimizer", FakeOptimizer)

    result = AbacusCCQN(
        atoms,
        {},
        "abacus",
        {
            "artifact_manifest": str(tmp_path / "manifest.json"),
            "reactive_bonds": "1-2",
        },
        calculator=abacuslite_compatible_calculator,
    ).run()

    assert optimizer_atoms == [result]
    assert result.calc is abacuslite_compatible_calculator
