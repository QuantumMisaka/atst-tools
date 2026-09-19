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


def ccqn_interp_test_system():
    """Return a fixed five-atom, cell-bearing system with a rotating H2O group."""
    cell = [8.0, 8.0, 8.0]
    atoms = Atoms(
        "Au2OH2",
        positions=[
            [0.00, 0.00, 0.00],
            [2.88, 0.00, 0.00],
            [0.30, 0.10, 2.10],
            [1.05, 0.35, 2.45],
            [-0.35, 0.55, 2.55],
        ],
        cell=cell,
        pbc=True,
    )
    product = Atoms(
        "Au2OH2",
        positions=[
            [0.00, 0.00, 0.00],
            [2.88, 0.00, 0.00],
            [0.85, 0.25, 2.30],
            [0.10, 0.60, 2.70],
            [1.45, 0.95, 2.20],
        ],
        cell=cell,
        pbc=True,
    )
    return atoms, product


# Frozen 2.2.6 behaviour: normalize(MIC(product - current)) for the geometry
# above, captured before interp_direction was introduced.
CCQN_INTERP_PRODUCT_REFERENCE = np.array(
    [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.248085241150915,
        0.067659611222977,
        0.090212814963969,
        -0.428510871078852,
        0.112766018704961,
        0.112766018704961,
        0.81191533467572,
        0.180425629927938,
        -0.157872426186945,
    ]
)


def test_interp_direction_product_keeps_legacy_mic_displacement():
    from atst_tools.mep.ccqn import CCQNOptimizer, ccqn_interp_e_vector

    atoms, product = ccqn_interp_test_system()
    forces = np.zeros((len(atoms), 3))

    default_vec = ccqn_interp_e_vector(atoms, product)
    explicit_vec = ccqn_interp_e_vector(atoms, product, direction="product")
    np.testing.assert_allclose(default_vec, CCQN_INTERP_PRODUCT_REFERENCE, rtol=0, atol=1e-12)
    np.testing.assert_allclose(explicit_vec, CCQN_INTERP_PRODUCT_REFERENCE, rtol=0, atol=1e-12)

    opt = CCQNOptimizer(atoms, e_vector_method="interp", product_atoms=product, logfile=None)
    assert opt.interp_direction == "product"
    np.testing.assert_allclose(opt._calculate_e_vector(forces), CCQN_INTERP_PRODUCT_REFERENCE, rtol=0, atol=1e-12)


def test_interp_direction_midpoint_uses_idpp_path_midpoint():
    from atst_tools.mep.ccqn import CCQNOptimizer, ccqn_interp_e_vector

    atoms, product = ccqn_interp_test_system()
    positions_before = atoms.get_positions().copy()

    product_vec = ccqn_interp_e_vector(atoms, product)
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        logfile=None,
    )
    midpoint_vec = opt._calculate_e_vector(np.zeros((len(atoms), 3)))

    assert np.isclose(np.linalg.norm(product_vec), 1.0)
    assert np.isclose(np.linalg.norm(midpoint_vec), 1.0)
    angle_deg = np.degrees(np.arccos(np.clip(float(product_vec @ midpoint_vec), -1.0, 1.0)))
    assert angle_deg > 30.0
    # Path generation reads the current geometry but must never move it.
    np.testing.assert_allclose(atoms.get_positions(), positions_before)


def test_midpoint_direction_reads_centre_frame_of_endpoint_inclusive_path(monkeypatch):
    from atst_tools.mep import ccqn

    atoms, product = ccqn_interp_test_system()
    calls = []

    def fake_interpolate_path(start, end, n_images, method="IDPP", tol=0.05, quiet=False, *, path_status=None):
        calls.append({"n_images": n_images, "method": method, "tol": tol, "quiet": quiet, "frames": n_images + 2})
        frames = []
        for index in range(n_images + 2):
            frame = start.copy()
            frame.set_positions(start.get_positions() + np.array([0.1 * index, 0.0, 0.0]))
            frames.append(frame)
        frames[0].set_positions(start.get_positions())
        frames[-1].set_positions(end.get_positions())
        if path_status is not None:
            path_status.update(
                method="IDPP",
                status="Converged",
                iterations=1,
                maxiter=2000,
                final_S_IDPP=0.0,
                max_force=0.0,
            )
        return frames

    monkeypatch.setattr(ccqn, "interpolate_path", fake_interpolate_path)

    e_vec = ccqn.ccqn_interp_e_vector(atoms, product, direction="midpoint")

    assert calls == [{"n_images": 7, "method": "IDPP", "tol": 0.05, "quiet": True, "frames": 9}]
    # Frame 4 of the nine-frame path is the midpoint; frame 3 would give 0.3.
    expected = np.tile([0.4, 0.0, 0.0], (len(atoms), 1)).flatten()
    np.testing.assert_allclose(e_vec, expected / np.linalg.norm(expected), rtol=0, atol=1e-12)


def test_interpolate_path_returns_endpoint_inclusive_frames():
    from atst_tools.utils.idpp import interpolate_path

    atoms, product = ccqn_interp_test_system()

    linear_path = interpolate_path(atoms, product, 7, method="linear")
    idpp_path = interpolate_path(atoms, product, 7, method="IDPP", quiet=True)

    for path in (linear_path, idpp_path):
        assert len(path) == 9
        assert len(path) // 2 == 4
        np.testing.assert_allclose(path[0].get_positions(), atoms.get_positions())
        np.testing.assert_allclose(path[-1].get_positions(), product.get_positions())


def test_interpolate_path_status_reports_solver_budget_and_outcome():
    from atst_tools.utils.idpp import interpolate_path

    atoms, product = ccqn_interp_test_system()
    idpp_status = {}
    linear_status = {}

    interpolate_path(atoms, product, 7, method="IDPP", quiet=True, path_status=idpp_status)
    interpolate_path(atoms, product, 7, method="linear", path_status=linear_status)

    # Fixed 2000-iteration budget: these geometries exhaust it, so x_mid is the
    # centre frame of a truncated path. The state stays observable.
    assert idpp_status["method"] == "IDPP"
    assert idpp_status["status"] == "Failed"
    assert idpp_status["iterations"] == 2000
    assert idpp_status["maxiter"] == 2000
    assert isinstance(idpp_status["final_S_IDPP"], float)
    assert idpp_status["final_S_IDPP"] > 0.0
    assert isinstance(idpp_status["max_force"], float)
    assert idpp_status["max_force"] >= 0.0
    assert linear_status == {
        "method": "linear",
        "status": None,
        "iterations": None,
        "maxiter": None,
        "final_S_IDPP": None,
        "max_force": None,
    }


def test_midpoint_direction_is_rejected_without_interp_e_vector_method():
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms, product = ccqn_interp_test_system()

    with pytest.raises(ValueError, match="interp_direction='midpoint' requires e_vector_method='interp'"):
        CCQNOptimizer(
            atoms,
            e_vector_method="ic",
            reactive_bonds=[(0, 1)],
            product_atoms=product,
            interp_direction="midpoint",
            logfile=None,
        )
    with pytest.raises(ValueError, match="interp_direction must be 'product' or 'midpoint'"):
        CCQNOptimizer(
            atoms,
            e_vector_method="interp",
            product_atoms=product,
            interp_direction="centre",
            logfile=None,
        )


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


def test_abacus_ccqn_forwards_interp_direction_and_defaults_to_product(monkeypatch, tmp_path):
    from atst_tools.mep import ccqn

    selected = {}

    class FakeOptimizer:
        def __init__(self, atoms, **kwargs):
            selected.update(kwargs)

        def run(self, fmax=None, steps=None):
            return None

    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    product = Atoms("H", positions=[[1.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    base_config = {
        "type": "ccqn",
        "e_vector_method": "interp",
        "artifact_manifest": None,
        "final_structure": None,
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ccqn.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DoubleWellCalculator())
    monkeypatch.setattr(ccqn, "CCQNOptimizer", FakeOptimizer)

    ccqn.AbacusCCQN(
        atoms.copy(),
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {**base_config, "interp_direction": "midpoint"},
        product_atoms=product,
    ).run()
    assert selected["interp_direction"] == "midpoint"

    ccqn.AbacusCCQN(
        atoms.copy(),
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        base_config,
        product_atoms=product,
    ).run()
    assert selected["interp_direction"] == "product"


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
def vendored_abacuslite_calculator(monkeypatch, tmp_path):
    """Construct a real vendored abacuslite calculator without launching ABACUS."""
    from atst_tools.external.ASE_interface.abacuslite import Abacus, AbacusProfile

    monkeypatch.setattr(AbacusProfile, "version", lambda self: "v3.10.1")
    profile = AbacusProfile("abacus")
    return Abacus(profile=profile, directory=tmp_path / "abacuslite")


def test_ccqn_uses_supplied_abacuslite_compatible_calculator(
    monkeypatch, tmp_path, vendored_abacuslite_calculator
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
        calculator=vendored_abacuslite_calculator,
    ).run()

    assert optimizer_atoms == [result]
    assert result.calc is vendored_abacuslite_calculator
    assert result.calc.profile.command == "abacus"
    assert type(result.calc.profile).__module__.endswith("abacuslite.core")


class HarmonicCalculator(Calculator):
    """Cheap analytic PES used to drive optimizer steps without external codes."""

    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        positions = atoms.get_positions()
        self.results["energy"] = float(
            np.sum(0.5 * positions[:, 0] ** 2 + 0.25 * positions[:, 1] ** 2 + 0.1 * positions[:, 2] ** 2)
        )
        self.results["forces"] = -np.stack(
            [positions[:, 0], 0.5 * positions[:, 1], 0.2 * positions[:, 2]], axis=1
        )


class CountingCalculator(HarmonicCalculator):
    """Harmonic PES that counts how often energy/forces were evaluated."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        self.calls += 1
        super().calculate(atoms, properties, system_changes)


def stub_interpolate_path(status, calls=None):
    """Return an ``interpolate_path`` stand-in reporting ``status`` for the path."""

    def stub(start, end, n_images, method="IDPP", tol=0.05, quiet=False, *, path_status=None):
        if calls is not None:
            calls.append({"n_images": n_images, "method": method, "tol": tol, "quiet": quiet})
        offset = (end.get_positions() - start.get_positions()) * 0.5
        frames = []
        for _ in range(n_images + 2):
            frame = start.copy()
            frame.set_positions(start.get_positions() + offset)
            frames.append(frame)
        frames[0].set_positions(start.get_positions())
        frames[-1].set_positions(end.get_positions())
        if path_status is not None:
            path_status.update(
                method="IDPP",
                status=status,
                iterations=2000,
                maxiter=2000,
                final_S_IDPP=1.5,
                max_force=0.75,
            )
        return frames

    return stub


def test_midpoint_solve_performs_no_energy_or_force_evaluation():
    from atst_tools.mep.ccqn import ccqn_interp_e_vector

    atoms, product = ccqn_interp_test_system()
    calculator = CountingCalculator()
    atoms.calc = calculator

    e_vec = ccqn_interp_e_vector(atoms, product, direction="midpoint")

    assert calculator.calls == 0
    assert np.isclose(np.linalg.norm(e_vec), 1.0)


def test_midpoint_diagnostics_records_idpp_path_status(tmp_path, capsys):
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms, product = ccqn_interp_test_system()
    atoms.calc = HarmonicCalculator()
    diagnostics = tmp_path / "diag.json"
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        hessian=False,
        logfile=None,
        diagnostics_file=str(diagnostics),
    )

    opt.step()

    data = json.loads(diagnostics.read_text(encoding="utf-8"))
    first_step = data["steps"][0]
    assert first_step["mode"] == "uphill"
    assert first_step["idpp_path_status"] == "Failed"
    assert first_step["idpp_iterations"] == 2000
    assert isinstance(first_step["idpp_final_S_IDPP"], float)
    assert isinstance(first_step["idpp_max_force"], float)
    advisory = capsys.readouterr().out
    assert advisory.count("Warning: CCQN finished") == 1
    assert "stage=ccqn_interp_path" in advisory
    assert "nsteps=2000" in advisory


def test_unconverged_path_advisory_is_emitted_once_and_only_for_failures(monkeypatch, capsys):
    from atst_tools.mep import ccqn
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms, product = ccqn_interp_test_system()
    atoms.calc = HarmonicCalculator()
    calls = []
    monkeypatch.setattr(ccqn, "interpolate_path", stub_interpolate_path("Failed", calls))
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        hessian=False,
        logfile=None,
    )

    opt.step()
    opt.step()
    opt.step()

    assert len(calls) == 3
    assert capsys.readouterr().out.count("Warning: CCQN finished") == 1
    assert opt.interp_path_status["status"] == "Failed"

    monkeypatch.setattr(ccqn, "interpolate_path", stub_interpolate_path("Converged"))
    converged = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        hessian=False,
        logfile=None,
    )
    converged.step()

    assert capsys.readouterr().out == ""
    assert converged.interp_path_status["status"] == "Converged"


def test_midpoint_path_is_recomputed_on_every_uphill_step(monkeypatch):
    from atst_tools.mep import ccqn
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms, product = ccqn_interp_test_system()
    atoms.calc = HarmonicCalculator()
    calls = []
    monkeypatch.setattr(ccqn, "interpolate_path", stub_interpolate_path("Failed", calls))
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        hessian=False,
        logfile=None,
    )

    for _ in range(3):
        assert opt.mode == "uphill"
        opt.step()

    assert len(calls) == 3
    assert {call["n_images"] for call in calls} == {7}
    assert {call["tol"] for call in calls} == {0.05}
    assert {call["quiet"] for call in calls} == {True}


def test_product_mode_diagnostics_do_not_carry_idpp_fields(tmp_path):
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms = Atoms("H", positions=[[0.3, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    atoms.calc = HarmonicCalculator()
    product = Atoms("H", positions=[[1.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
    diagnostics = tmp_path / "diag.json"
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        hessian=False,
        logfile=None,
        diagnostics_file=str(diagnostics),
    )

    opt.step()
    opt.step()

    data = json.loads(diagnostics.read_text(encoding="utf-8"))
    assert data["steps"]
    assert opt.interp_path_status is None
    for recorded in data["steps"]:
        assert not [key for key in recorded if key.startswith("idpp_")]


def test_run_ccqn_rejects_midpoint_with_ic_before_calculator_construction(monkeypatch, tmp_path):
    """The embedded API fails fast without touching the calculator or optimizers."""
    from helpers import DummyCalc
    from atst_tools.api import CCQNOptions, run_ccqn
    from atst_tools.api.models import WorkflowExecutionError
    from atst_tools.mep import ccqn

    events = []
    monkeypatch.setattr(ccqn.AbacusCCQN, "set_calculator", lambda self: events.append("set_calculator"))
    monkeypatch.setattr(ccqn.CCQNOptimizer, "run", lambda self, **kwargs: events.append("optimizer_run"))

    with pytest.raises(ValueError, match="interp_direction='midpoint' requires e_vector_method='interp'") as caught:
        run_ccqn(
            Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]]),
            DummyCalc(),
            CCQNOptions(
                e_vector_method="ic",
                reactive_bonds="1-2",
                interp_direction="midpoint",
                artifact_manifest=str(tmp_path / "manifest.json"),
            ),
        )

    assert not isinstance(caught.value, WorkflowExecutionError)
    assert events == []

    # Control: with a coherent direction family the guard stays silent and the
    # calculator hook is reached, so the empty event list above is meaningful.
    result = run_ccqn(
        Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]]),
        DummyCalc(),
        CCQNOptions(
            e_vector_method="interp",
            interp_direction="midpoint",
            product_atoms=Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.6, 0.0, 0.0]]),
            artifact_manifest=str(tmp_path / "manifest.json"),
        ),
    )

    assert events == ["set_calculator", "optimizer_run"]
    assert result.status == "complete"


def test_abacus_ccqn_run_rejects_midpoint_with_ic_before_calculator(monkeypatch, tmp_path):
    from atst_tools.mep import ccqn

    events = []
    monkeypatch.setattr(ccqn.AbacusCCQN, "set_calculator", lambda self: events.append("set_calculator"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="interp_direction='midpoint' requires e_vector_method='interp'"):
        ccqn.AbacusCCQN(
            Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[10, 10, 10], pbc=True),
            {},
            "abacus",
            {
                "type": "ccqn",
                "e_vector_method": "ic",
                "reactive_bonds": "1-2",
                "interp_direction": "midpoint",
                "artifact_manifest": None,
            },
        ).run()

    assert events == []


def test_prfo_steps_do_not_report_a_stale_idpp_path_status(monkeypatch, tmp_path):
    """Only uphill steps solve a path, so only they carry IDPP provenance."""
    from atst_tools.mep import ccqn
    from atst_tools.mep.ccqn import CCQNOptimizer

    atoms, product = ccqn_interp_test_system()
    atoms.calc = HarmonicCalculator()
    monkeypatch.setattr(ccqn, "interpolate_path", stub_interpolate_path("Failed"))
    diagnostics = tmp_path / "diag.json"
    opt = CCQNOptimizer(
        atoms,
        e_vector_method="interp",
        product_atoms=product,
        interp_direction="midpoint",
        hessian=False,
        logfile=None,
        diagnostics_file=str(diagnostics),
    )

    opt.step()
    assert opt.interp_path_status["status"] == "Failed"
    opt.hessian_matrix = np.diag([-1.0] + [1.0] * (3 * len(atoms) - 1))
    opt.step()

    steps = json.loads(diagnostics.read_text(encoding="utf-8"))["steps"]
    assert [record["mode"] for record in steps] == ["uphill", "prfo"]
    assert steps[0]["idpp_path_status"] == "Failed"
    assert not [key for key in steps[1] if key.startswith("idpp_")]
