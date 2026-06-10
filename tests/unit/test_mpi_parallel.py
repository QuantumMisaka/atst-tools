"""Tests for MPI image-level NEB orchestration."""

from __future__ import annotations

import importlib

import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator

from helpers import DummyCalc, FakeReducingWorld, FakeWorld


def _atoms(x: float) -> Atoms:
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=x, forces=[[0.0, 0.0, 0.0]])
    return atoms


def test_bootstrap_requires_mpi4py_under_mpi_launcher(monkeypatch):
    from atst_tools.utils import mpi

    monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", "4")

    def fake_import(name):
        if name == "mpi4py":
            raise ImportError("missing mpi4py")
        return importlib.import_module(name)

    monkeypatch.setattr(mpi.importlib, "import_module", fake_import)

    with pytest.raises(RuntimeError, match="mpi4py"):
        mpi.bootstrap_mpi_for_ase()


def test_run_neb_parallel_requires_rank_count_equal_interior_images(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.4)]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_ase_world", lambda: FakeWorld(size=2, rank=0))

    with pytest.raises(ValueError, match="MPI ranks.*interior images"):
        main.run_neb(
            {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
            "abacus",
            {"type": "neb", "init_chain": "chain.traj", "parallel": True},
        )


def test_run_neb_parallel_make_generates_chain_only_on_rank_zero(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.4)]
    fake_world = FakeWorld(size=3, rank=1)
    generated = []
    read_calls = []

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None, **kwargs):
            return None

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "generate", lambda **kwargs: generated.append(kwargs))
    monkeypatch.setattr(main, "read", lambda path, *args, **kwargs: read_calls.append(path) or chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    main.run_neb(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "neb",
            "make": {
                "init_structure": "init.traj",
                "final_structure": "final.traj",
                "n_images": 3,
                "method": "IDPP",
                "output": "made.traj",
                "no_align": True,
            },
            "trajectory": "neb.traj",
            "parallel": True,
            "restart": False,
        },
    )

    assert generated == []
    assert read_calls[0] == "made.traj"
    assert fake_world.barriers >= 1


def test_run_neb_parallel_uses_image_index_directory(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.4)]
    for image in chain[1:-1]:
        image.calc = None
    directories = []

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None, **kwargs):
            return None

        def run(self, fmax=None, steps=None):
            return None

    def fake_get_calculator(calc_name, config, **kwargs):
        directories.append(kwargs["directory"])
        return DummyCalc()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_ase_world", lambda: FakeWorld(size=3, rank=1))
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", fake_get_calculator)
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    main.run_neb(
        {"calculator": {"name": "abacus", "abacus": {"directory": "run_neb", "parameters": {}}}},
        "abacus",
        {"type": "neb", "init_chain": "chain.traj", "parallel": True},
    )

    assert directories == ["run_neb/image_002"]
    assert chain[1].calc is None
    assert chain[2].calc is not None
    assert chain[3].calc is None


def test_run_neb_parallel_logs_world_size(monkeypatch, tmp_path, caplog):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3)]

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None, **kwargs):
            return None

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_ase_world", lambda: FakeWorld(size=2, rank=0))
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    with caplog.at_level("INFO", logger=main.LOGGER.name):
        main.run_neb(
            {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
            "abacus",
            {"type": "neb", "init_chain": "chain.traj", "parallel": True},
        )

    assert "world.size=2" in caplog.text


def test_autoneb_parallel_requires_world_size_equal_n_simul(monkeypatch):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.0)]

    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: FakeWorld(size=2, rank=0))

    with pytest.raises(ValueError, match="MPI ranks.*n_simul"):
        autoneb.AutoNEBRunner(
            {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
            "abacus",
            {
                "type": "autoneb",
                "init_chain": "chain.traj",
                "parallel": True,
                "n_simul": 4,
            },
        )


def test_autoneb_parallel_initial_files_written_only_by_rank_zero(monkeypatch, tmp_path):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.0)]
    writes = []
    fake_world = FakeWorld(size=3, rank=1)

    class FakeAutoNEB:
        def __init__(self, **kwargs):
            self.all_images = chain
            return None

        def run(self):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "write", lambda *args, **kwargs: writes.append(args[0]))
    monkeypatch.setattr(autoneb, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", FakeAutoNEB)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 3,
        },
    )
    runner.run()

    assert writes == []
    assert fake_world.barriers >= 1


def test_autoneb_parallel_logs_world_size(monkeypatch, tmp_path, capsys):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3)]
    fake_world = FakeWorld(size=2, rank=0)

    class FakeAutoNEB:
        def __init__(self, **kwargs):
            self.all_images = chain
            return None

        def run(self):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(autoneb, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", FakeAutoNEB)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 2,
        },
    )
    runner.run()

    assert "world.size=2" in capsys.readouterr().out


def test_autoneb_parallel_cleanup_only_on_rank_zero(monkeypatch, tmp_path):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.0)]
    fake_world = FakeWorld(size=3, rank=1)

    class FakeAutoNEB:
        def __init__(self, **kwargs):
            return None

        def run(self):
            return None

    monkeypatch.chdir(tmp_path)
    (tmp_path / "neb000.traj").write_text("old trajectory")
    (tmp_path / "AutoNEB_iter").mkdir()
    (tmp_path / "AutoNEB_iter" / "old.log").write_text("old log")
    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(autoneb, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", FakeAutoNEB)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 3,
        },
    )
    runner.run()

    assert (tmp_path / "neb000.traj").exists()
    assert (tmp_path / "AutoNEB_iter").exists()
    assert fake_world.barriers >= 1


def test_autoneb_parallel_endpoint_preparation_only_on_rank_zero(monkeypatch, tmp_path):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.0)]
    calls = []
    fake_world = FakeWorld(size=3, rank=2)

    class FakeAutoNEB:
        def __init__(self, **kwargs):
            return None

        def run(self):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "write", lambda *args, **kwargs: calls.append(("write", args[0])))
    monkeypatch.setattr(autoneb, "ensure_neb_endpoint_results", lambda *args, **kwargs: calls.append(("ensure", kwargs.get("context"))))
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(autoneb, "AbacusAutoNEB", FakeAutoNEB)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 3,
        },
    )
    runner.run()

    assert ("ensure", "AutoNEB") not in calls
    assert fake_world.barriers >= 1


def test_autoneb_parallel_attaches_only_rank_owned_image(monkeypatch):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3), _atoms(0.0)]
    fake_world = FakeWorld(size=3, rank=1)
    directories = []

    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)
    monkeypatch.setattr(
        autoneb.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: directories.append(kwargs["directory"]) or DummyCalc(),
    )

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"directory": "autoneb_run", "parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 3,
        },
    )

    active_images = chain[1:4]
    for image in active_images:
        image.calc = None
    for image_index, image in enumerate(active_images, start=1):
        image.info["_atst_autoneb_index"] = image_index
    runner.attach_calculators(active_images)

    assert directories == ["autoneb_run/image_002"]
    assert active_images[0].calc is None
    assert active_images[1].calc is not None
    assert active_images[2].calc is None


def test_autoneb_serial_attach_uses_active_autoneb_indices(monkeypatch):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3)]
    directories = []

    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: FakeWorld(size=1, rank=0))
    monkeypatch.setattr(
        autoneb.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: directories.append(kwargs["directory"]) or DummyCalc(),
    )

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"directory": "autoneb_run", "parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": False,
            "n_simul": 2,
            "optimizer_kwargs": {"maxstep": 0.05},
        },
    )
    runner._active_autoneb = type("FakeAutoNEBState", (), {"all_images": chain})()
    runner.attach_calculators([chain[2]])
    optimizer = runner._get_optimizer()

    assert directories == ["autoneb_run/image_002"]
    assert getattr(optimizer, "keywords", {}) == {"maxstep": 0.05}


def test_run_neb_parallel_endpoint_preparation_only_on_rank_zero(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2), _atoms(0.3)]
    calls = []

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None, **kwargs):
            return None

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "write", lambda *args, **kwargs: calls.append(("write", args[0])))
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: calls.append(("ensure", kwargs.get("context"))))
    monkeypatch.setattr(main, "get_ase_world", lambda: FakeWorld(size=2, rank=1))
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    main.run_neb(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {"type": "neb", "init_chain": "chain.traj", "parallel": True},
    )

    assert ("ensure", "NEB") not in calls


def test_run_neb_parallel_endpoint_sync_reads_without_ase_parallel(monkeypatch, tmp_path):
    from atst_tools.scripts import main

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2)]
    read_kwargs = []
    deleted = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main,
        "read",
        lambda *args, **kwargs: read_kwargs.append(kwargs) or chain,
    )
    monkeypatch.setattr(main.os, "remove", lambda path: deleted.append(path))

    synced = main._sync_parallel_endpoint_results(
        chain,
        FakeWorld(size=2, rank=0),
        lambda images: None,
    )

    assert synced == chain
    assert read_kwargs == [{"index": ":", "parallel": False}]
    assert deleted == [".atst_neb_endpoint_synced.traj"]


def test_image_parallel_rank_owns_matching_local_image():
    from atst_tools.utils.mpi import rank_owns_local_image

    world = FakeWorld(size=3, rank=1)

    assert not rank_owns_local_image(world, 0)
    assert rank_owns_local_image(world, 1)
    assert not rank_owns_local_image(world, 2)


def test_autoneb_parallel_endpoint_sync_reads_without_ase_parallel(monkeypatch, tmp_path):
    from atst_tools.mep import autoneb

    chain = [_atoms(0.0), _atoms(0.1), _atoms(0.2)]
    read_kwargs = []
    fake_world = FakeWorld(size=2, rank=1)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb, "read", lambda *args, **kwargs: read_kwargs.append(kwargs) or chain)
    monkeypatch.setattr(autoneb, "get_ase_world", lambda: fake_world)

    runner = autoneb.AutoNEBRunner(
        {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}},
        "abacus",
        {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "parallel": True,
            "n_simul": 2,
        },
    )
    runner._prepare_endpoint_results()

    assert read_kwargs[-1] == {"index": ":", "parallel": False}


def test_abacus_autoneb_parallel_rejects_grouped_rank_execution(monkeypatch, tmp_path):
    from atst_tools.mep.autoneb import AbacusAutoNEB

    class FakeStack:
        def enter_context(self, obj):
            return obj

    monkeypatch.chdir(tmp_path)
    auto = AbacusAutoNEB(
        attach_calculators=lambda images: None,
        prefix="run_autoneb",
        n_simul=2,
        n_max=4,
        parallel=True,
        world=FakeWorld(size=4, rank=0),
    )
    auto.iteration = 0
    auto.all_images = [_atoms(float(index)) for index in range(4)]
    auto.k = [0.1, 0.1, 0.1]

    with pytest.raises(ValueError, match="MPI ranks.*active AutoNEB"):
        auto._execute_one_neb(FakeStack(), n_cur=4, to_run=[0, 1, 2, 3])


def test_abacus_neb_parallel_synchronizes_with_reductions_not_broadcasts():
    from atst_tools.mep.neb import AbacusNEB

    images = [_atoms(float(index)) for index in range(4)]
    world = FakeReducingWorld(size=2, rank=0)

    neb = AbacusNEB(images, parallel=True, world=world, climb=False)
    forces = neb.get_forces()

    assert forces.shape == (2, 3)
    assert world.sums >= 4


def test_abacus_autoneb_initialize_reads_image_files_without_ase_parallel(monkeypatch, tmp_path):
    from atst_tools.mep import autoneb

    read_kwargs = []

    def fake_isfile(path):
        text = str(path)
        return text.endswith("run000.traj") or text.endswith("run001.traj")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(autoneb.os.path, "isfile", fake_isfile)
    monkeypatch.setattr(
        autoneb,
        "read",
        lambda filename, **kwargs: read_kwargs.append(kwargs) or _atoms(0.0),
    )

    auto = autoneb.AbacusAutoNEB(
        attach_calculators=lambda images: None,
        prefix="run",
        n_simul=1,
        n_max=2,
        parallel=True,
        world=FakeWorld(size=2, rank=1),
    )
    n_cur = auto.__initialize__()

    assert n_cur == 2
    assert read_kwargs == [{"parallel": False}, {"parallel": False}]


def test_autoneb_store_results_uses_reductions_not_broadcasts():
    from ase.calculators.singlepoint import SinglePointCalculator
    from atst_tools.mep.autoneb import _store_E_and_F_in_spc_reduced
    from atst_tools.mep.neb import AbacusNEB

    images = [_atoms(float(index)) for index in range(4)]
    world = FakeReducingWorld(size=2, rank=0)
    neb = AbacusNEB(images, parallel=True, world=world, climb=False)
    neb.get_forces()

    _store_E_and_F_in_spc_reduced(neb)

    assert isinstance(images[1].calc, SinglePointCalculator)
    assert isinstance(images[2].calc, SinglePointCalculator)
