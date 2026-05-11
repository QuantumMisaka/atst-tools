import numpy as np
import pytest
import sys
import types
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator


def _atoms(energy=0.0):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


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
