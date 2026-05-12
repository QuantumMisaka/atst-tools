import numpy as np
import pytest
import sys
import types
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.singlepoint import SinglePointCalculator


def _atoms(energy=0.0):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


class DummyCalc(Calculator):
    implemented_properties = ["energy", "forces", "stress"]

    def __init__(self, energy=3.0):
        super().__init__()
        self.energy = energy

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = self.energy
        self.results["forces"] = np.zeros((len(atoms), 3))
        self.results["stress"] = np.zeros(6)


def _install_fake_sella(monkeypatch, fake_irc, failure_cls=None):
    if failure_cls is None:
        failure_cls = type("IRCInnerLoopConvergenceFailure", (RuntimeError,), {})
    sella_module = types.ModuleType("sella")
    sella_module.IRC = fake_irc
    optimize_module = types.ModuleType("sella.optimize")
    irc_module = types.ModuleType("sella.optimize.irc")
    irc_module.IRCInnerLoopConvergenceFailure = failure_cls
    monkeypatch.setitem(sys.modules, "sella", sella_module)
    monkeypatch.setitem(sys.modules, "sella.optimize", optimize_module)
    monkeypatch.setitem(sys.modules, "sella.optimize.irc", irc_module)
    return failure_cls


def test_d2s_workflow_uses_unified_constructor(monkeypatch):
    from atst_tools.workflows import d2s

    calls = []

    monkeypatch.setattr(d2s, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(d2s.D2SWorkflow, "optimize_endpoints", lambda self, a, b: (a, b))
    monkeypatch.setattr(
        d2s.D2SWorkflow,
        "run_rough_neb",
        lambda self, a, b: [_atoms(0.0), _atoms(1.0), _atoms(0.2)],
    )
    monkeypatch.setattr(
        d2s.D2SWorkflow,
        "run_single_ended",
        lambda self, chain, idx, guess: calls.append((idx, self.calc_name)),
    )

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {"type": "d2s", "method": "dimer", "init_file": "i.traj", "final_file": "f.traj"},
    )
    workflow.run()

    assert calls == [(1, "dp")]


def test_run_neb_reuses_shared_dp_calculator(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.0)]
    calls = []
    neb_kwargs = {}
    shared_calc = DummyCalc(1.0)

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images
            neb_kwargs.update(kwargs)

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None):
            self.neb = neb

        def run(self, fmax=None, steps=None):
            calls.append(("run", fmax, steps))

    def fake_get_calculator(calc_name, config, **kwargs):
        calls.append(("calc", kwargs.get("shared"), kwargs.get("directory")))
        return shared_calc if kwargs.get("shared") else DummyCalc(2.0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", fake_get_calculator)
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    main.run_neb(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}},
        "dp",
        {"type": "neb", "init_chain": "chain.traj", "parallel": False, "max_steps": 3},
    )

    assert neb_kwargs["allow_shared_calculator"] is True
    assert chain[1].calc is shared_calc
    assert chain[2].calc is shared_calc
    assert ("run", 0.05, 3) in calls


def test_run_neb_respects_dp_share_calculator_false(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.0)]
    neb_kwargs = {}

    class FakeNEB:
        def __init__(self, images, **kwargs):
            neb_kwargs.update(kwargs)

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None):
            return None

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    main.run_neb(
        {
            "calculator": {
                "name": "dp",
                "dp": {"model": "model.pt", "share_calculator": False},
            }
        },
        "dp",
        {"type": "neb", "init_chain": "chain.traj", "parallel": False},
    )

    assert neb_kwargs["allow_shared_calculator"] is False
    assert chain[1].calc is not chain[2].calc


def test_autoneb_runner_reuses_shared_dp_calculator(monkeypatch):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.0)]
    shared_calc = DummyCalc(1.0)
    calls = []

    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)

    def fake_get_calculator(calc_name, config, **kwargs):
        calls.append(kwargs)
        return shared_calc if kwargs.get("shared") else DummyCalc(2.0)

    monkeypatch.setattr(autoneb.CalculatorFactory, "get_calculator", fake_get_calculator)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}},
        "dp",
        {"type": "autoneb", "init_chain": "chain.traj", "parallel": False},
    )
    runner.attach_calculators(chain[1:-1])

    assert runner.allow_shared_calculator is True
    assert chain[1].calc is shared_calc
    assert chain[2].calc is shared_calc
    assert calls[0]["shared"] is True


def test_d2s_rough_dyneb_reuses_shared_dp_calculator(monkeypatch, tmp_path):
    from atst_tools.workflows import d2s

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.0)]
    shared_calc = DummyCalc(1.0)
    dyneb_kwargs = {}

    class FakeSolver:
        def run(self):
            return chain

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None):
            return None

        def run(self, fmax=None, steps=None):
            return None

    def fake_get_calculator(calc_name, config, **kwargs):
        return shared_calc if kwargs.get("shared") else DummyCalc(2.0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d2s.Fast_IDPPSolver, "from_endpoints", lambda *args, **kwargs: FakeSolver())
    monkeypatch.setattr(d2s, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(d2s.CalculatorFactory, "get_calculator", fake_get_calculator)
    monkeypatch.setattr(d2s, "DyNEB", lambda images, **kwargs: dyneb_kwargs.update(kwargs) or object())
    monkeypatch.setattr(d2s, "FIRE", FakeOptimizer)

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}},
        "dp",
        {"type": "d2s", "method": "dimer", "neb": {"n_images": 2}},
    )
    workflow.run_rough_neb(chain[0], chain[-1])

    assert dyneb_kwargs["allow_shared_calculator"] is True
    assert chain[1].calc is shared_calc
    assert chain[2].calc is shared_calc


def test_run_dimer_preserves_dp_calculator_selection(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    calls = []

    class FakeDimer:
        def __init__(self, init_Atoms, config, calc_name, calc_config, **kwargs):
            calls.append(
                (
                    "init",
                    calc_name,
                    config["calculator"]["dp"]["model"],
                    kwargs["dimer_separation"],
                    kwargs["max_num_rot"],
                )
            )

        def run(self, fmax=None, max_steps=None):
            calls.append(("run", fmax, max_steps))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main.os.path, "exists", lambda path: path == "init.traj")
    monkeypatch.setattr(main, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(main, "AbacusDimer", FakeDimer)

    main.run_dimer(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}},
        "dp",
        {
            "type": "dimer",
            "init_structure": "init.traj",
            "fmax": 0.2,
            "max_steps": 5,
            "dimer_separation": 0.03,
            "max_num_rot": 7,
        },
    )

    assert calls == [("init", "dp", "model.pt", 0.03, 7), ("run", 0.2, 5)]


def test_run_sella_preserves_dp_calculator_selection(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    calls = []

    class FakeSella:
        def __init__(self, init_Atoms, config, calc_name, calc_config, **kwargs):
            calls.append(("init", calc_name, config["calculator"]["dp"]["model"], kwargs["order"]))

        def run(self):
            calls.append(("run",))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main.os.path, "exists", lambda path: True)
    monkeypatch.setattr(main, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(main, "AbacusSella", FakeSella)

    main.run_sella(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}},
        "dp",
        {"type": "sella", "init_structure": "init.traj", "fmax": 0.2, "max_steps": 5, "order": 2},
    )

    assert calls == [("init", "dp", "model.pt", 2), ("run",)]


def test_d2s_vibration_is_disabled_by_default(monkeypatch):
    from atst_tools.workflows import d2s

    calls = []
    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {"type": "d2s", "method": "dimer"},
    )
    monkeypatch.setattr(d2s, "Vibrations", lambda *args, **kwargs: calls.append(args))

    workflow.run_vibration([_atoms(0.0), _atoms(1.0), _atoms(0.0)], _atoms(1.0), None)

    assert calls == []


def test_d2s_vibration_auto_indices_writes_results(monkeypatch, tmp_path):
    from atst_tools.workflows import d2s

    class FakeVibrations:
        def __init__(self, atoms, indices=None, delta=None, nfree=None, name=None):
            self.indices = indices

        def run(self):
            return None

        def summary(self):
            return None

        def get_energies(self):
            return np.array([0.1])

        def get_frequencies(self):
            return np.array([100.0])

        def get_zero_point_energy(self):
            return 0.05

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d2s.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    monkeypatch.setattr(d2s, "Vibrations", FakeVibrations)
    monkeypatch.setattr(d2s, "get_displacement_analysis", lambda chain, thr=0.10: (1, [0], np.array([1.0])))

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "d2s",
            "method": "dimer",
            "vibration": {"enabled": True, "indices": "auto", "results_file": "d2s_vib.json"},
        },
    )
    workflow.run_vibration([_atoms(0.0), _atoms(1.0), _atoms(0.0)], _atoms(1.0), None)

    assert (tmp_path / "d2s_vib.json").exists()


def test_d2s_endpoint_optimization_skips_valid_inputs(monkeypatch, tmp_path):
    from atst_tools.workflows import d2s

    calls = []

    class FakeOptimizer:
        def __init__(self, atoms, logfile=None):
            calls.append(("init", logfile))

        def run(self, fmax=None, steps=None):
            calls.append(("run", fmax, steps))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d2s, "QuasiNewton", FakeOptimizer)

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {"type": "d2s", "method": "dimer", "endpoint_optimization": {"enabled": True}},
    )
    init_atoms, final_atoms = workflow.optimize_endpoints(_atoms(1.0), _atoms(2.0))

    assert init_atoms.get_potential_energy() == 1.0
    assert final_atoms.get_potential_energy() == 2.0
    assert calls == []


def test_d2s_endpoint_optimization_runs_for_missing_results(monkeypatch, tmp_path):
    from atst_tools.workflows import d2s

    calls = []

    class FakeOptimizer:
        def __init__(self, atoms, logfile=None):
            self.atoms = atoms
            calls.append(("init", logfile))

        def run(self, fmax=None, steps=None):
            calls.append(("run", fmax, steps))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d2s, "QuasiNewton", FakeOptimizer)
    monkeypatch.setattr(d2s.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc(3.0))

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "d2s",
            "method": "dimer",
            "endpoint_optimization": {"enabled": True, "fmax": 0.2, "max_steps": 4},
        },
    )
    init_atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    final_atoms = Atoms("H", positions=[[1.0, 0.0, 0.0]])

    init_atoms, final_atoms = workflow.optimize_endpoints(init_atoms, final_atoms)

    assert init_atoms.get_potential_energy() == 3.0
    assert final_atoms.get_potential_energy() == 3.0
    assert calls == [("init", "opt_is.log"), ("run", 0.2, 4), ("init", "opt_fs.log"), ("run", 0.2, 4)]


def test_d2s_endpoint_optimization_disabled_never_rejects_missing_results(tmp_path):
    from atst_tools.workflows import d2s

    workflow = d2s.D2SWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "d2s",
            "method": "dimer",
            "endpoint_optimization": {"enabled": False},
            "endpoint_singlepoint": "never",
        },
    )

    with pytest.raises(ValueError, match="lacks meaningful"):
        workflow.optimize_endpoints(
            Atoms("H", positions=[[0.0, 0.0, 0.0]]),
            Atoms("H", positions=[[1.0, 0.0, 0.0]]),
        )


def test_relax_workflow_runs_with_mocked_io_and_optimizer(monkeypatch, tmp_path):
    from atst_tools.workflows import relax

    events = []

    class FakeOptimizer:
        def __init__(self, atoms, trajectory=None, logfile=None):
            events.append(("optimizer", trajectory, logfile))

        def run(self, fmax=None, steps=None):
            events.append(("run", fmax, steps))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(relax.os.path, "exists", lambda path: True)
    monkeypatch.setattr(relax, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(relax, "write", lambda filename, atoms: events.append(("write", filename)))
    monkeypatch.setattr(relax.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    monkeypatch.setattr(relax, "QuasiNewton", FakeOptimizer)

    workflow = relax.RelaxWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "relax",
            "init_structure": "init.traj",
            "optimizer": "QuasiNewton",
            "fmax": 0.1,
            "max_steps": 3,
        },
    )
    workflow.run()

    assert ("run", 0.1, 3) in events
    assert ("write", "final_relaxed.traj") in events


def test_vibration_workflow_writes_results(monkeypatch, tmp_path):
    from atst_tools.workflows import vibration

    class FakeVibrations:
        def __init__(self, atoms, indices=None, delta=None, nfree=None, name=None):
            self.atoms = atoms

        def run(self):
            return None

        def summary(self):
            return None

        def get_energies(self):
            return np.array([0.1, 0.2])

        def get_frequencies(self):
            return np.array([100.0, 200.0])

        def get_zero_point_energy(self):
            return 0.15

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vibration.os.path, "exists", lambda path: True)
    monkeypatch.setattr(vibration, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(vibration.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    monkeypatch.setattr(vibration, "Vibrations", FakeVibrations)

    workflow = vibration.VibrationWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "vibration", "init_structure": "ts.traj"},
    )
    workflow.run()

    assert (tmp_path / "vibration_results.json").exists()


def test_vibration_restart_removes_invalid_cache(monkeypatch, tmp_path):
    from atst_tools.workflows import vibration

    class FakeVibrations:
        def __init__(self, atoms, indices=None, delta=None, nfree=None, name=None):
            return None

        def run(self):
            return None

        def summary(self):
            return None

        def get_energies(self):
            return np.array([0.1])

        def get_frequencies(self):
            return np.array([100.0])

        def get_zero_point_energy(self):
            return 0.05

    monkeypatch.chdir(tmp_path)
    vib_dir = tmp_path / "vib"
    vib_dir.mkdir()
    good = vib_dir / "cache.eq.json"
    bad = vib_dir / "cache.0x+.json"
    good.write_text("{}", encoding="utf-8")
    bad.touch()
    monkeypatch.setattr(vibration.os.path, "exists", lambda path: True)
    monkeypatch.setattr(vibration, "read_structure", lambda filename: _atoms())
    monkeypatch.setattr(vibration.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    monkeypatch.setattr(vibration, "Vibrations", FakeVibrations)

    workflow = vibration.VibrationWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "vibration", "init_structure": "ts.traj", "restart": True, "name": "vib"},
    )
    workflow.run()

    assert good.exists()
    assert not bad.exists()


def test_irc_workflow_runs_forward_and_reverse(monkeypatch, tmp_path):
    from atst_tools.workflows import irc

    calls = []

    class FakeIRC:
        def __init__(self, atoms, trajectory=None, **kwargs):
            calls.append(("init", kwargs["dx"], kwargs["eta"]))
            self.atoms = atoms

        def run(self, fmax, steps=None, direction=None):
            calls.append(("run", fmax, steps, direction))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(irc, "read_structure", lambda filename: _atoms(1.0))
    monkeypatch.setattr(irc.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    monkeypatch.setattr(irc.IRCWorkflow, "_normalize_trajectory", lambda self: calls.append(("normalize",)))
    _install_fake_sella(monkeypatch, FakeIRC)

    workflow = irc.IRCWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "irc",
            "init_structure": "ts.traj",
            "trajectory": "irc.traj",
            "direction": "both",
            "fmax": 0.03,
            "max_steps": 7,
            "dx": 0.2,
            "eta": 0.003,
        },
    )
    workflow.run()

    assert calls == [
        ("init", 0.2, 0.003),
        ("run", 0.03, 7, "forward"),
        ("run", 0.03, 7, "reverse"),
        ("normalize",),
    ]


def test_irc_workflow_reports_sella_inner_loop_boundary(monkeypatch, tmp_path):
    from atst_tools.workflows import irc

    class FakeInnerLoopFailure(RuntimeError):
        pass

    class FakeIRC:
        def __init__(self, atoms, trajectory=None, **kwargs):
            self.atoms = atoms
            self.trajectory = trajectory

        def run(self, fmax, steps=None, direction=None):
            self.trajectory.write(self.atoms)
            raise FakeInnerLoopFailure("inner loop did not converge")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(irc, "read_structure", lambda filename: _atoms(1.0))
    monkeypatch.setattr(irc.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    _install_fake_sella(monkeypatch, FakeIRC, FakeInnerLoopFailure)

    workflow = irc.IRCWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "irc", "init_structure": "ts.traj", "trajectory": "irc.traj", "direction": "forward"},
    )

    with pytest.raises(irc.IRCBoundaryError) as excinfo:
        workflow.run()

    message = str(excinfo.value)
    assert "current supported boundary" in message
    assert "Direction: forward" in message
    assert "Trajectory: irc.traj (frames written: 1)" in message
    assert "Original error: FakeInnerLoopFailure: inner loop did not converge" in message
    assert "does not yet provide automatic endpoint recovery" in message


def test_irc_workflow_does_not_hide_unrelated_assertions(monkeypatch, tmp_path):
    from atst_tools.workflows import irc

    class FakeIRC:
        def __init__(self, atoms, trajectory=None, **kwargs):
            return None

        def run(self, fmax, steps=None, direction=None):
            raise AssertionError("programmer bug")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(irc, "read_structure", lambda filename: _atoms(1.0))
    monkeypatch.setattr(irc.CalculatorFactory, "get_calculator", lambda *args, **kwargs: _atoms().calc)
    _install_fake_sella(monkeypatch, FakeIRC)

    workflow = irc.IRCWorkflow(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "irc", "init_structure": "ts.traj", "trajectory": "irc.traj", "direction": "forward"},
    )

    with pytest.raises(AssertionError, match="programmer bug"):
        workflow.run()
