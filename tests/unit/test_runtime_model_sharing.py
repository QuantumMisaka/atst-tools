"""Behaviour evidence for read-only DP model sharing.

Two claims are pinned here with observable facts:

* several DP calculator instances and several worker processes may consume one
  read-only model file without a writable copy of it, and
* running a workflow never writes into the directory that holds the model,
  while every attempt keeps its own writable cache directory inside the
  workflow directory.

The default tests replace ``deepmd.calculator.DP`` with a stand-in that only
reads the model file, so the assertions stay about ATST behaviour.  The opt-in
test at the end exercises the real DeepMD-kit calculator when a model file is
offered through ``ATST_DP_TEST_MODEL``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator

from atst_tools.calculators import factory as calculator_factory
from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import launch as runtime_launch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tree_snapshot(root: Path) -> dict[str, str]:
    """Return one digest map describing a whole directory tree.

    The map covers the file content, the mode and the size of every entry plus
    the directory mtime, so a created, replaced or removed entry is visible even
    when it is deleted again before the check.
    """
    snapshot = {
        ".": f"dir:{oct(root.stat().st_mode)}:{root.stat().st_mtime_ns}",
    }
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_dir():
            snapshot[relative] = f"dir:{oct(path.stat().st_mode)}:{path.stat().st_mtime_ns}"
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[relative] = f"file:{oct(path.stat().st_mode)}:{path.stat().st_size}:{digest}"
    return snapshot


@pytest.fixture
def read_only_model(tmp_path):
    """Return a model file living in a directory that refuses writes."""
    model_dir = tmp_path / "research_model"
    model_dir.mkdir()
    model_file = model_dir / "DPA-3.1-3M.pt"
    model_file.write_bytes(b"ATST read-only model placeholder\n" * 16)
    model_file.chmod(0o444)
    model_dir.chmod(0o555)
    try:
        yield model_file
    finally:
        # Restore write permission so the pytest temporary tree stays removable.
        model_dir.chmod(0o755)


def _install_recording_deepmd(monkeypatch, reads, evaluations):
    """Install a DeepMD stand-in that reads the model and evaluates analytically.

    Args:
        monkeypatch: Active pytest monkeypatch fixture.
        reads: List receiving one record per constructed calculator.
        evaluations: List receiving the positions of every evaluated geometry.

    Returns:
        The stand-in calculator class.
    """

    class _ReadingDP(Calculator):
        """Stand-in for ``deepmd.calculator.DP`` that never writes."""

        implemented_properties = ("energy", "forces")

        def __init__(self, model, **kwargs):
            super().__init__()
            self.model_path = Path(model).resolve()
            payload = self.model_path.read_bytes()
            reads.append(
                {
                    "model": str(self.model_path),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "kwargs": dict(kwargs),
                }
            )

        def calculate(self, atoms=None, properties=("energy",), system_changes=()):
            super().calculate(atoms, properties, system_changes)
            positions = np.asarray(atoms.positions, dtype=float)
            evaluations.append(positions.copy())
            self.results = {
                "energy": float(np.sum(positions)),
                "forces": np.ones_like(positions),
            }

    module = ModuleType("deepmd")
    calculator_module = ModuleType("deepmd.calculator")
    calculator_module.DP = _ReadingDP
    monkeypatch.setitem(sys.modules, "deepmd", module)
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator_module)
    return _ReadingDP


def test_shared_dp_calculator_reads_a_read_only_model_without_writing_to_it(
    monkeypatch, read_only_model
):
    """A shared calculator reads the model once and leaves its directory intact."""
    reads: list[dict] = []
    evaluations: list[np.ndarray] = []
    _install_recording_deepmd(monkeypatch, reads, evaluations)
    monkeypatch.setattr(calculator_factory.DeepPotentialFactory, "_instances", {})
    model_dir = read_only_model.parent
    before = _tree_snapshot(model_dir)

    config = {"calculator": {"name": "dp", "dp": {"model": str(read_only_model)}}}
    first = calculator_factory.CalculatorFactory.get_calculator("dp", config)
    second = calculator_factory.CalculatorFactory.get_calculator("dp", config)

    # The read-only directory is genuinely unwritable: the snapshot check below
    # therefore proves "no write was attempted", not merely "no file appeared".
    assert os.access(model_dir, os.W_OK) is False
    with pytest.raises(PermissionError):
        (model_dir / "probe.tmp").write_text("x", encoding="utf-8")

    assert first is second
    assert len(reads) == 1
    assert reads[0]["model"] == str(read_only_model.resolve())

    energies = []
    for shift in (0.0, 0.5):
        atoms = Atoms("H2", positions=[[0.0, 0.0, shift], [0.0, 0.0, shift + 0.25]])
        atoms.calc = first
        energies.append(atoms.get_potential_energy())
    assert energies == [0.25, 1.25]
    assert len(evaluations) == 2

    assert _tree_snapshot(model_dir) == before
    assert (
        hashlib.sha256(read_only_model.read_bytes()).hexdigest() == reads[0]["sha256"]
    )


def test_independent_dp_instances_share_one_read_only_model_file(
    monkeypatch, read_only_model
):
    """Without sharing every instance still reads the same read-only model file."""
    reads: list[dict] = []
    evaluations: list[np.ndarray] = []
    _install_recording_deepmd(monkeypatch, reads, evaluations)
    monkeypatch.setattr(calculator_factory.DeepPotentialFactory, "_instances", {})
    model_dir = read_only_model.parent
    before = _tree_snapshot(model_dir)
    config = {
        "calculator": {
            "name": "dp",
            "dp": {"model": str(read_only_model), "share_calculator": False},
        }
    }

    first = calculator_factory.CalculatorFactory.get_calculator("dp", config)
    second = calculator_factory.CalculatorFactory.get_calculator("dp", config)
    assert first is not second

    energies = []
    for calculator, shift in ((first, 1.0), (second, 2.0)):
        atoms = Atoms("H", positions=[[0.0, 0.0, shift]])
        atoms.calc = calculator
        energies.append(atoms.get_potential_energy())
    assert energies == [1.0, 2.0]

    assert [record["model"] for record in reads] == [
        str(read_only_model.resolve()),
        str(read_only_model.resolve()),
    ]
    assert len({record["sha256"] for record in reads}) == 1
    assert _tree_snapshot(model_dir) == before


_WORKER_SCRIPT = r'''
"""Worker-shaped child: one DP calculator, one attempt cache directory."""
import hashlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
from ase import Atoms
from ase.calculators.calculator import Calculator


class _ReadingDP(Calculator):
    """Stand-in for deepmd.calculator.DP that only reads the model file."""

    implemented_properties = ("energy", "forces")

    def __init__(self, model, **kwargs):
        super().__init__()
        self.model_path = Path(model).resolve()
        self.model_sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        self.kwargs = dict(kwargs)

    def calculate(self, atoms=None, properties=("energy",), system_changes=()):
        super().calculate(atoms, properties, system_changes)
        positions = np.asarray(atoms.positions, dtype=float)
        self.results = {
            "energy": float(np.sum(positions)),
            "forces": np.ones_like(positions),
        }


calculator_module = ModuleType("deepmd.calculator")
calculator_module.DP = _ReadingDP
sys.modules["deepmd"] = ModuleType("deepmd")
sys.modules["deepmd.calculator"] = calculator_module

from atst_tools.calculators.factory import CalculatorFactory

model = os.environ["ATST_MODEL_UNDER_TEST"]
config = {"calculator": {"name": "dp", "dp": {"model": model}}}
calculator = CalculatorFactory.get_calculator("dp", config)
atoms = Atoms(
    "H2",
    positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.25]],
    cell=[5.0, 5.0, 5.0],
    pbc=True,
)
atoms.calc = calculator

cache_dir = Path(os.environ["JAX_COMPILATION_CACHE_DIR"])
cache_dir.mkdir(parents=True, exist_ok=True)
payload = {
    "attempt": os.environ.get("ATST_ATTEMPT"),
    "cache_dir": str(cache_dir),
    "cwd": str(Path.cwd()),
    "energy": atoms.get_potential_energy(),
    "model": str(calculator.model_path),
    "model_sha256": calculator.model_sha256,
}
(cache_dir / "worker.json").write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
'''


def _worker_environment(
    workdir: Path, attempt: int, model_file: Path
) -> dict[str, str]:
    """Return the frozen isolated-worker environment of one attempt."""
    base = dict(os.environ)
    base["PYTHONPATH"] = str(REPO_ROOT / "src")
    base["ATST_MODEL_UNDER_TEST"] = str(model_file)
    base.pop(runtime_launch.ATTEMPT_ENV, None)
    resolution = runtime_devices.resolve_devices(
        None, environ={runtime_devices.CUDA_VISIBLE_DEVICES: "2,3"}
    )
    request = runtime_launch.merge_runtime_request(cli_devices="0", environ=base)
    return runtime_launch.build_child_environment(
        request,
        resolution,
        base=base,
        workflow_dir=workdir,
        attempt=attempt,
    )


def test_workers_share_one_read_only_model_with_isolated_attempt_caches(
    read_only_model,
):
    """Two processes share the read-only model and keep separate caches."""
    model_dir = read_only_model.parent
    workdir = model_dir.parent / "workflow"
    workdir.mkdir()
    before = _tree_snapshot(model_dir)

    results = []
    for attempt in (1, 2):
        environment = _worker_environment(workdir, attempt, read_only_model)
        completed = subprocess.run(
            [sys.executable, "-c", _WORKER_SCRIPT],
            cwd=workdir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert completed.returncode == 0, completed.stderr
        results.append(json.loads(completed.stdout.strip().splitlines()[-1]))

    cache_dirs = [
        runtime_launch.child_cache_dir(workdir, attempt) for attempt in (1, 2)
    ]
    assert cache_dirs[0] != cache_dirs[1]
    for index, attempt in enumerate((1, 2)):
        cache_dir = cache_dirs[index]
        assert cache_dir.is_dir()
        assert os.access(cache_dir, os.W_OK) is True
        assert cache_dir.parent == workdir / ".atst_cache"
        assert results[index]["cache_dir"] == str(cache_dir)
        assert results[index]["attempt"] == str(attempt)
        assert results[index]["cwd"] == str(workdir)
        assert results[index]["model"] == str(read_only_model.resolve())
        assert results[index]["energy"] == 0.25
        # Each attempt owns exactly its own cache entry: nothing from the other
        # attempt was inherited, and the writable cache never holds the model.
        assert sorted(path.name for path in cache_dir.iterdir()) == ["worker.json"]

    assert len({result["model_sha256"] for result in results}) == 1
    assert os.access(model_dir, os.W_OK) is False
    assert _tree_snapshot(model_dir) == before


@pytest.mark.skipif(
    not os.environ.get("ATST_DP_TEST_MODEL"),
    reason="set ATST_DP_TEST_MODEL to a DeepMD-kit model file to run the real backend",
)
def test_real_deepmd_uses_a_read_only_model_directory(tmp_path):
    """The real DeepMD-kit calculator evaluates from a read-only model directory."""
    source = Path(os.environ["ATST_DP_TEST_MODEL"]).expanduser()
    if not source.is_file():
        pytest.fail(f"ATST_DP_TEST_MODEL does not exist: {source}")
    deepmd_calculator = pytest.importorskip("deepmd.calculator")

    model_dir = tmp_path / "pinned_model"
    model_dir.mkdir()
    model_file = model_dir / source.name
    model_file.write_bytes(source.read_bytes())
    model_file.chmod(0o444)
    model_dir.chmod(0o555)
    try:
        before = _tree_snapshot(model_dir)
        assert os.access(model_dir, os.W_OK) is False

        options: dict[str, object] = {}
        head = os.environ.get("ATST_DP_TEST_HEAD")
        if head:
            options["head"] = head
        config = {
            "calculator": {"name": "dp", "dp": {"model": str(model_file), **options}}
        }
        calculator = calculator_factory.CalculatorFactory.get_calculator("dp", config)
        assert isinstance(calculator, deepmd_calculator.DP)

        atoms = Atoms(
            "H2",
            positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.75]],
            cell=[6.0, 6.0, 6.0],
            pbc=True,
        )
        atoms.calc = calculator
        energy = atoms.get_potential_energy()
        forces = atoms.get_forces()

        assert np.isfinite(energy)
        assert np.isfinite(forces).all()
        residual = float(np.abs(atoms.get_forces().sum(axis=0)).max())
        assert residual < 1.0e-4
        assert _tree_snapshot(model_dir) == before
    finally:
        model_dir.chmod(0o755)
