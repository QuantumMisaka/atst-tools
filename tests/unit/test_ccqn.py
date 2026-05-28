import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes


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
