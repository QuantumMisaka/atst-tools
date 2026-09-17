"""AutoNEB iteration-convergence capture and manifest persistence tests.

One AutoNEB iteration only optimizes a window of the band, so these tests pin
both halves of the contract: each engine captures one optimizer-fact record per
executed iteration, and the owning runner persists those records as durable
stage facts without presenting the last subset as whole-band convergence.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase.io import write

from atst_tools.mep import autoneb

from helpers import DummyCalc, FakeWorld, make_atoms


BAND_SIZE = 5
ADVISORY_TAIL = "Execution completion does not imply optimizer convergence.\n"


class FakeNEB:
    """Minimal NEB double exposing only what the AutoNEB iteration boundary uses."""

    def __init__(self, images, **kwargs):
        self.images = list(images)
        self.nimages = len(self.images)
        self.natoms = len(self.images[0])
        self.world = kwargs.get("world")
        self.climb = kwargs.get("climb")
        self.parallel = bool(kwargs.get("parallel"))
        self.stresses = None
        self.energies = [float(index) for index in range(len(self.images))]
        self.real_forces = [np.zeros((len(atoms), 3)) for atoms in self.images]

    def get_forces(self):
        return np.zeros((len(self.images), len(self.images[0]), 3))

    def interpolate(self, **kwargs):
        return None


def _make_optimizer(runs, signals, nsteps=11):
    """Return a fake optimizer class that records every ``run`` call and budget."""

    class FakeOptimizer:
        def __init__(self, neb, logfile=None):
            self.neb = neb
            self.logfile = logfile
            self.nsteps = nsteps

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def attach(self, callback):
            return None

        def run(self, fmax=None, steps=None):
            runs.append({"fmax": fmax, "steps": steps})
            return signals.pop(0)

    return FakeOptimizer


def _seriel_engine(tmp_path, band=BAND_SIZE, **overrides):
    """Build one serial AutoNEB engine with a prepared image band."""
    kwargs = {
        "attach_calculators": lambda images: None,
        "prefix": tmp_path / "run_autoneb",
        "n_simul": 2,
        "n_max": band,
        "iter_folder": "AutoNEB_iter",
        "world": FakeWorld(size=1, rank=0),
        "parallel": False,
        "fmax": 0.05,
        "maxsteps": 100,
        "climb": False,
        "method": "improvedtangent",
    }
    kwargs.update(overrides)
    engine = autoneb.AbacusAutoNEB(**kwargs)
    engine.all_images = [make_atoms(energy=float(index)) for index in range(band)]
    engine.k = [0.1] * (band - 1)
    engine.iteration = 0
    return engine


def _install_engine(monkeypatch, script, signals, band=BAND_SIZE):
    """Install a scripted engine driving the real iteration capture path.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        script: Iterable of ``(to_run, climb, many_steps)`` iteration commands.
        signals: Optimizer ``run`` return values, consumed in iteration order.
        band: Number of images in the scripted band.

    Returns:
        The list recording each executed optimizer call.
    """
    runs = []

    class ScriptedAutoNEB(autoneb.AbacusAutoNEB):
        def run(self):
            self.iteration = 0
            self.all_images = [make_atoms(energy=float(index)) for index in range(band)]
            self.k = [0.1] * (band - 1)
            for to_run, climb, many_steps in script:
                self.execute_one_neb(
                    len(self.all_images),
                    to_run,
                    climb=climb,
                    many_steps=many_steps,
                )
            return self.all_images

    monkeypatch.setattr(autoneb, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", ScriptedAutoNEB)
    monkeypatch.setattr(
        autoneb.AutoNEBRunner,
        "_get_optimizer",
        lambda self: _make_optimizer(runs, signals),
    )
    return runs


def _make_runner(monkeypatch, tmp_path, *, world=None, parallel=False):
    """Create an AutoNEB runner in an isolated working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        autoneb.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: DummyCalc(energy=8.0),
    )
    write("init_chain.traj", [make_atoms(energy=float(index)) for index in range(3)])
    return autoneb.AutoNEBRunner(
        {
            "calculator": {
                "name": "abacus",
                "abacus": {"directory": "run_autoneb", "parameters": {}},
            }
        },
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "init_chain.traj",
            "prefix": "run_autoneb",
            "n_simul": 2,
            "n_max": BAND_SIZE,
            "parallel": parallel,
            "endpoint_singlepoint": "always",
        },
        world=world,
    )


def test_engine_captures_one_record_per_iteration_from_qn_run(monkeypatch, tmp_path):
    """Each executed iteration appends the optimizer facts, including its subset."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "AbacusNEB", FakeNEB)
    runs = []
    engine = _seriel_engine(tmp_path, optimizer=_make_optimizer(runs, [False, True]))

    engine.execute_one_neb(BAND_SIZE, [1, 2, 3], climb=False)
    engine.execute_one_neb(BAND_SIZE, [0, 1, 2, 3], climb=True, many_steps=True)

    assert runs == [
        {"fmax": 0.05, "steps": 100},
        {"fmax": 0.05, "steps": 100},
    ]
    first, second = engine.iteration_records
    assert first == {
        "iteration": 1,
        "subset": [1, 2, 3],
        "band_size": BAND_SIZE,
        "converged": False,
        "fmax": 0.05,
        "steps": 100,
        "actual_steps": 11,
        "climb": False,
        "many_steps": False,
    }
    assert first["subset"] != list(range(BAND_SIZE))
    assert second["iteration"] == 2
    assert second["subset"] == [0, 1, 2, 3]
    assert second["converged"] is True
    assert (second["climb"], second["many_steps"]) == (True, True)


def test_engine_records_the_executed_two_stage_budget(monkeypatch, tmp_path):
    """The recorded budget follows the configured schedule, not a default."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "AbacusNEB", FakeNEB)
    runs = []
    engine = _seriel_engine(
        tmp_path,
        fmax=[0.20, 0.05],
        maxsteps=[20, 200],
        optimizer=_make_optimizer(runs, [False, True]),
    )

    engine.execute_one_neb(BAND_SIZE, [1, 2, 3], climb=False)
    engine.execute_one_neb(BAND_SIZE, [1, 2, 3], climb=True, many_steps=True)

    assert runs == [{"fmax": 0.2, "steps": 20}, {"fmax": 0.05, "steps": 200}]
    assert [record["fmax"] for record in engine.iteration_records] == [0.2, 0.05]
    assert [record["steps"] for record in engine.iteration_records] == [20, 200]


def test_synchronized_engine_captures_iteration_records(monkeypatch, tmp_path):
    """The native ASE backend captures the same iteration facts."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "NEB", FakeNEB)
    runs = []
    engine = autoneb.SynchronizedAutoNEB(
        attach_calculators=lambda images: None,
        prefix=tmp_path / "run_autoneb",
        n_simul=2,
        n_max=BAND_SIZE,
        iter_folder="AutoNEB_iter",
        world=FakeWorld(size=1, rank=0),
        parallel=False,
        fmax=0.05,
        maxsteps=100,
        climb=False,
        method="improvedtangent",
        optimizer=_make_optimizer(runs, [None]),
    )
    engine.all_images = [make_atoms(energy=float(index)) for index in range(BAND_SIZE)]
    engine.k = [0.1] * (BAND_SIZE - 1)
    engine.iteration = 0

    engine.execute_one_neb(BAND_SIZE, [1, 2, 3])

    assert runs == [{"fmax": 0.05, "steps": 100}]
    record = engine.iteration_records[0]
    assert record["subset"] == [1, 2, 3]
    assert record["band_size"] == BAND_SIZE
    assert record["converged"] is None
    assert record["actual_steps"] == 11


def test_runner_persists_iteration_records_and_final_subset_scope(
    monkeypatch, tmp_path, capsys
):
    """The runner writes per-iteration stages plus one last-iteration final scope."""
    runs = _install_engine(
        monkeypatch,
        script=[
            ([0, 1, 2, 3], False, False),
            ([1, 2, 3], False, False),
        ],
        signals=[False, False],
    )
    runner = _make_runner(monkeypatch, tmp_path)

    runner.run()

    captured = capsys.readouterr()
    manifest = json.loads(Path("atst_artifacts.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "atst-artifacts-v1"
    assert manifest["workflow"] == "autoneb"
    assert manifest["metadata"] == {}
    assert [stage["name"] for stage in manifest["stages"]] == [
        "autoneb_iter",
        "autoneb_iter",
        "autoneb",
    ]
    first, second, final = manifest["stages"]
    assert list(first) == [
        "name",
        "status",
        "converged",
        "role",
        "criterion",
        "iteration",
        "subset",
        "fmax",
        "fmax_unit",
        "steps",
        "actual_steps",
    ]
    assert first["iteration"] == 1
    assert first["subset"] == [0, 1, 2, 3]
    assert first["converged"] is False
    assert first["role"] == "subset"
    assert first["criterion"] == "neb_fmax"
    assert first["fmax"] == 0.05
    assert first["fmax_unit"] == "eV/Angstrom"
    assert first["steps"] == 100
    assert first["actual_steps"] == 11
    assert second["iteration"] == 2
    assert second["subset"] == [1, 2, 3]
    # The final scope is the last executed iteration, which only owned a window.
    assert final["name"] == "autoneb"
    assert final["role"] == "final"
    assert final["iteration"] == 2
    assert final["subset"] == [1, 2, 3]
    assert final["subset"] != list(range(BAND_SIZE))
    assert final["converged"] is False
    assert manifest["artifacts"] == [
        {"role": "image_trajectory", "path": f"run_autoneb{index:03d}.traj"}
        for index in range(BAND_SIZE)
    ]
    for index in range(BAND_SIZE):
        assert Path(f"run_autoneb{index:03d}.traj").is_file()
    assert runs == [{"fmax": 0.05, "steps": 100}, {"fmax": 0.05, "steps": 100}]

    # Exactly one advisory, for the final scope, with the stable English tokens.
    assert captured.out.count(ADVISORY_TAIL) == 1
    for token in (
        "finished without satisfying its optimizer convergence criteria",
        "workflow=autoneb",
        "stage=autoneb",
        "iteration=2",
        "does not imply",
    ):
        assert token in captured.out


@pytest.mark.parametrize(
    ("signal", "expected_converged"),
    [(True, True), (None, None)],
)
def test_runner_advisory_stays_silent_unless_the_final_iteration_failed(
    monkeypatch, tmp_path, capsys, signal, expected_converged
):
    """``True`` and unknown final signals print nothing and stay truthful."""
    _install_engine(
        monkeypatch,
        script=[([1, 2, 3], False, False)],
        signals=[signal],
    )
    runner = _make_runner(monkeypatch, tmp_path)

    runner.run()

    captured = capsys.readouterr()
    assert "finished without satisfying" not in captured.out
    assert ADVISORY_TAIL not in captured.out
    raw_manifest = Path("atst_artifacts.json").read_text(encoding="utf-8")
    manifest = json.loads(raw_manifest)
    assert manifest["stages"][0]["converged"] is expected_converged
    assert manifest["stages"][1]["name"] == "autoneb"
    assert manifest["stages"][1]["converged"] is expected_converged
    if expected_converged is None:
        assert '"converged": null' in raw_manifest


def test_runner_records_skipped_final_scope_when_no_iteration_executed(
    monkeypatch, tmp_path, capsys
):
    """A completed band that needed no iteration keeps a truthful skipped scope."""

    class SilentAutoNEB:
        def __init__(self, **kwargs):
            self.all_images = [
                make_atoms(energy=float(index)) for index in range(BAND_SIZE)
            ]

        def run(self):
            return None

    monkeypatch.setattr(autoneb, "AbacusAutoNEB", SilentAutoNEB)
    monkeypatch.setattr(
        autoneb.AutoNEBRunner, "_freeze_final_image_results", lambda self, images: None
    )
    monkeypatch.setattr(autoneb, "write", lambda *args, **kwargs: None)
    runner = _make_runner(monkeypatch, tmp_path)

    runner.run()

    manifest = json.loads(Path("atst_artifacts.json").read_text(encoding="utf-8"))
    assert manifest["workflow"] == "autoneb"
    assert manifest["stages"] == [
        {"name": "autoneb", "status": "skipped", "converged": None, "role": "final"}
    ]
    assert [artifact["role"] for artifact in manifest["artifacts"]] == [
        "image_trajectory"
    ] * BAND_SIZE
    assert ADVISORY_TAIL not in capsys.readouterr().out


def test_runner_threads_its_communicator_into_the_advisory(monkeypatch, tmp_path):
    """The advisory receives the runner's communicator for root-only emission."""
    calls = []
    monkeypatch.setattr(
        autoneb,
        "emit_unconverged_advisory",
        lambda record, **kwargs: calls.append((record, kwargs)) or True,
    )
    _install_engine(
        monkeypatch,
        script=[([1, 2, 3], False, False)],
        signals=[False],
    )
    runner = _make_runner(monkeypatch, tmp_path)

    runner.run()

    assert len(calls) == 1
    record, kwargs = calls[0]
    assert record.name == "autoneb"
    assert record.role == "final"
    assert kwargs["workflow"] == "autoneb"
    assert kwargs["world"] is runner.world


class _RankPairWorld:
    """Two-rank fake communicator recording collective participation."""

    def __init__(self, rank):
        self.size = 2
        self.rank = int(rank)
        self.reductions = 0
        self.barriers = 0

    def barrier(self):
        self.barriers += 1

    def sum_scalar(self, value):
        self.reductions += 1
        return int(value)


@pytest.mark.parametrize("rank", [0, 1], ids=["rank0", "rank1"])
def test_parallel_ranks_share_the_collective_sequence(
    monkeypatch, tmp_path, capsys, rank
):
    """Both ranks build the same stages; only root prints and writes the manifest."""
    records = [{
        "iteration": 1,
        "subset": [1, 2],
        "band_size": BAND_SIZE,
        "converged": False,
        "fmax": 0.05,
        "steps": 100,
        "actual_steps": 100,
        "climb": False,
        "many_steps": False,
    }]

    class RecordingAutoNEB:
        def __init__(self, **kwargs):
            self.iteration_records = [dict(record) for record in records]

        def run(self):
            self.all_images = [
                make_atoms(energy=float(index)) for index in range(BAND_SIZE)
            ]
            return self.all_images

    monkeypatch.setattr(autoneb, "AbacusAutoNEB", RecordingAutoNEB)
    monkeypatch.chdir(tmp_path)
    # A sequential rank simulation cannot share rank 0's published endpoint
    # chain file, so every simulated rank reads the same chain directly.
    monkeypatch.setattr(
        autoneb,
        "read",
        lambda *args, **kwargs: [make_atoms(energy=float(index)) for index in range(3)],
    )
    world = _RankPairWorld(rank)
    runner = _make_runner(monkeypatch, tmp_path, world=world, parallel=True)

    runner.run()

    manifest_path = Path("atst_artifacts.json")
    if rank == 0:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert [stage["name"] for stage in manifest["stages"]] == [
            "autoneb_iter",
            "autoneb",
        ]
        assert manifest["stages"][1]["subset"] == [1, 2]
        assert ADVISORY_TAIL in capsys.readouterr().out
    else:
        assert not manifest_path.exists()
        follower_output = capsys.readouterr().out
        assert ADVISORY_TAIL not in follower_output
        assert "finished without satisfying" not in follower_output
    assert world.reductions > 0
    assert world.barriers > 0
