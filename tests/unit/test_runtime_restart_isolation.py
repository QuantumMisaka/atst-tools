"""Behaviour evidence for restart recovery and ATST state isolation.

The tests here pin two claims:

* a workflow never mixes the atoms or results of a previous attempt (or of a
  previous image) into the current run: every attempt of one workflow directory
  gets its own writable cache directory, and a rerun starts from the configured
  structure unless a restart was requested, and
* a restart resumes from the facts on disk (the last trajectory frame, read
  through the existing restart helpers) and recomputes its energy and forces
  with the current calculator instead of reusing the frozen values that the
  trajectory file carries.
"""

from __future__ import annotations

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write

from atst_tools.runtime import launch as runtime_launch
from atst_tools.utils.restart_helpers import get_last_frame

K_SPRING = 2.0


class AnalyticCalculator(Calculator):
    """Stand-in calculator with an analytic energy for one moving atom.

    ``E = 0.5 * k * |r|**2`` and ``F = -k * r`` make every evaluated geometry
    identifiable from its own numbers, so a result that belongs to another
    geometry cannot pass unnoticed.
    """

    implemented_properties = ("energy", "forces")

    def __init__(self):
        super().__init__()
        self.evaluated: list[np.ndarray] = []

    def calculate(self, atoms=None, properties=("energy",), system_changes=()):
        super().calculate(atoms, properties, system_changes)
        positions = np.asarray(atoms.positions, dtype=float)
        self.evaluated.append(positions.copy())
        self.results = {
            "energy": float(0.5 * K_SPRING * np.sum(positions**2)),
            "forces": -K_SPRING * positions,
        }


def analytic_energy(position: float) -> float:
    """Return the stand-in energy of a frozen geometry."""
    return 0.5 * K_SPRING * position**2


def _frozen_frame(position: float, energy: float) -> Atoms:
    """Return one frame that carries foreign (already frozen) results."""
    atoms = Atoms("H", positions=[[position, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


def _run_relax(monkeypatch, workdir, calculator, *, restart: bool) -> None:
    """Run the relax workflow in *workdir* with the stand-in calculator."""
    from atst_tools.workflows import relax

    def get_calculator(name, config, **kwargs):
        assert name == "dp"
        return calculator

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(relax.CalculatorFactory, "get_calculator", get_calculator)
    config = {
        "type": "relax",
        "init_structure": "init.traj",
        "trajectory": "relax.traj",
        "logfile": "relax.log",
        "optimizer": "BFGS",
        "fmax": 100.0,
        "max_steps": 1,
        "restart": restart,
    }
    relax.RelaxWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pt"}}}, "dp", config
    ).run()


def _previous_run_directory(tmp_path, *, input_position, restart_position, stale_energy):
    """Create a workflow directory left behind by an earlier attempt."""
    write(tmp_path / "init.traj", _frozen_frame(input_position, -111.0))
    write(
        tmp_path / "relax.traj",
        [
            _frozen_frame(input_position, -111.0),
            _frozen_frame(restart_position, stale_energy),
        ],
    )
    return tmp_path


def test_restart_resumes_from_disk_facts_and_recomputes_its_results(
    monkeypatch, tmp_path, capsys
):
    """A restart continues from the last frame and never reuses its frozen values."""
    _previous_run_directory(
        tmp_path, input_position=0.5, restart_position=1.0, stale_energy=-999.0
    )
    calculator = AnalyticCalculator()

    _run_relax(monkeypatch, tmp_path, calculator, restart=True)
    captured = capsys.readouterr().out

    # The restart source is the recorded geometry (1.0), not the input structure
    # (0.5), and the energy is recomputed for it instead of being taken from the
    # frozen value of the trajectory frame.
    assert [positions.ravel().tolist() for positions in calculator.evaluated] == [
        [1.0, 0.0, 0.0]
    ]
    assert f"Final energy: {analytic_energy(1.0):.4f} eV" in captured
    assert "-999" not in captured
    assert "-111" not in captured

    # The previous attempt's frames are replaced by this attempt's own record.
    frames = read(tmp_path / "relax.traj", index=":")
    assert len(frames) == 1
    assert frames[0].positions.ravel().tolist() == [1.0, 0.0, 0.0]
    assert read(tmp_path / "final_relaxed.traj").positions.ravel().tolist() == [
        1.0,
        0.0,
        0.0,
    ]


def test_rerun_without_restart_ignores_the_previous_attempt_state(
    monkeypatch, tmp_path, capsys
):
    """A rerun in a used directory starts from the input structure and rewrites."""
    _previous_run_directory(
        tmp_path, input_position=0.5, restart_position=1.0, stale_energy=-999.0
    )
    calculator = AnalyticCalculator()

    _run_relax(monkeypatch, tmp_path, calculator, restart=False)
    captured = capsys.readouterr().out

    # Only the configured input geometry is evaluated: neither the geometry nor
    # the results of the earlier attempt reach this run.
    assert [positions.ravel().tolist() for positions in calculator.evaluated] == [
        [0.5, 0.0, 0.0]
    ]
    assert f"Final energy: {analytic_energy(0.5):.4f} eV" in captured
    assert "-999" not in captured
    assert "-111" not in captured

    frames = read(tmp_path / "relax.traj", index=":")
    assert len(frames) == 1
    assert frames[0].positions.ravel().tolist() == [0.5, 0.0, 0.0]
    assert read(tmp_path / "final_relaxed.traj").positions.ravel().tolist() == [
        0.5,
        0.0,
        0.0,
    ]


def test_the_restart_source_carries_results_that_must_not_be_reused(tmp_path):
    """The restart source is a geometry fact plus foreign frozen results."""
    trajectory = tmp_path / "relax.traj"
    write(trajectory, [_frozen_frame(0.25, -7.0), _frozen_frame(0.75, -8.0)])

    atoms = get_last_frame(trajectory)

    # The stored geometry is the fact the restart has to continue from ...
    assert atoms.positions.ravel().tolist() == [0.75, 0.0, 0.0]
    # ... and the frame also carries the earlier results, so a restart that
    # reported -8.0 instead of its own fresh value would be visible above.
    assert atoms.get_potential_energy() == -8.0
    assert atoms.get_potential_energy() != analytic_energy(0.75)


def test_every_attempt_of_one_workflow_directory_gets_its_own_cache(tmp_path):
    """Two attempts of one directory use separate, attributable cache paths."""
    from atst_tools.runtime import devices as runtime_devices

    workdir = tmp_path / "workflow"
    workdir.mkdir()
    resolution = runtime_devices.resolve_devices(
        None, environ={runtime_devices.CUDA_VISIBLE_DEVICES: "2,3"}
    )
    request = runtime_launch.merge_runtime_request(cli_devices="0", environ={})

    environments = {}
    for attempt in (1, 2):
        environments[attempt] = runtime_launch.build_child_environment(
            request,
            resolution,
            base={"CUDA_VISIBLE_DEVICES": "2,3", "PATH": "/usr/bin"},
            workflow_dir=workdir,
            attempt=attempt,
        )

    cache_dirs = {}
    for attempt, environment in environments.items():
        cache_dir = runtime_launch.child_cache_dir(workdir, attempt)
        cache_dirs[attempt] = cache_dir
        assert environment["JAX_COMPILATION_CACHE_DIR"] == str(cache_dir)
        assert {environment[key] for key in runtime_launch.CACHE_ENV_KEYS} == {
            str(cache_dir)
        }
        assert cache_dir.parent == workdir / ".atst_cache"
        assert cache_dir.is_dir()
        # The cache directory and the attempt the worker reports must agree, so
        # an evidence sidecar cannot attribute one attempt's cache to another.
        assert runtime_launch.attempt_index(environment) == attempt

    assert cache_dirs[1] != cache_dirs[2]

    (cache_dirs[1] / "attempt.json").write_text("first", encoding="utf-8")
    first_snapshot = sorted(path.name for path in cache_dirs[1].iterdir())
    (cache_dirs[2] / "attempt.json").write_text("second", encoding="utf-8")

    # Nothing of the earlier attempt is visible from the later one, and writing
    # the later attempt's cache does not disturb the earlier one.
    assert sorted(path.name for path in cache_dirs[2].iterdir()) == ["attempt.json"]
    assert (cache_dirs[2] / "attempt.json").read_text(encoding="utf-8") == "second"
    assert sorted(path.name for path in cache_dirs[1].iterdir()) == first_snapshot
    assert (cache_dirs[1] / "attempt.json").read_text(encoding="utf-8") == "first"


def test_shared_calculator_keeps_every_neb_image_result_separate():
    """One shared calculator still reports each NEB image's own numbers."""
    from atst_tools.mep.neb import AbacusNEB

    positions = (0.0, 0.5, 1.0, 1.5)
    shared = AnalyticCalculator()
    images = []
    for position in positions:
        image = Atoms("H", positions=[[position, 0.0, 0.0]])
        image.calc = shared
        images.append(image)

    neb = AbacusNEB(images, k=0.1, allow_shared_calculator=True)
    neb.get_forces()

    expected_energies = [analytic_energy(position) for position in positions]
    assert list(neb.energies) == pytest.approx(expected_energies)
    # Reading the images back after the whole band was evaluated returns each
    # image's own result, never the values of the image evaluated last.
    assert [image.get_potential_energy() for image in images] == pytest.approx(
        expected_energies
    )
    for position, image in zip(positions, images):
        assert image.get_forces().ravel().tolist() == pytest.approx(
            [-K_SPRING * position, 0.0, 0.0]
        )
