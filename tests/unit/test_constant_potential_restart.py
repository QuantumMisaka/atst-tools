"""Restart contracts for durable constant-potential electronic facts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator

import atst_tools.calculators.constant_potential as cp_module
from atst_tools.calculators.constant_potential import (
    ConstantPotentialError,
    constant_potential_identity_for_config,
    publish_constant_potential_facts,
)


def _config(tmp_path: Path, *, target: float = -15.0, zgate: float = 0.7) -> dict:
    """Return a small compensated-gate relax/NEB configuration."""
    return {
        "calculation": {"type": "relax"},
        "calculator": {
            "name": "abacus",
            "abacus": {
                "directory": str(tmp_path / "abacus"),
                "parameters": {"zgate": zgate, "nelec": 8.0},
            },
            "constant_potential": {
                "energy_boundary": "compensated_gate",
                "target_mu_ev": target,
                "reference_electrons": 10.0,
                "reference_electrode": "custom",
                "potential_tolerance_v": 1.0e-6,
                "capacitance_initial": 1.0,
                "capacitance_unit": "e/V",
            },
        },
    }


def _cp_results(atoms: Atoms, *, target: float, nelec: float) -> dict:
    """Build a self-consistent compensated-gate fact mapping."""
    reference = 10.0
    delta = nelec - reference
    correction = -target * delta
    energy = 1.25 + correction
    return {
        "energy": energy,
        "free_energy": energy,
        "raw_energy": 1.25,
        "raw_free_energy": 1.25,
        "efermi": target,
        "vacuum_level": None,
        "fermishift": None,
        "energy_boundary": "compensated_gate",
        "boundary_parameters": {"zgate": 0.7},
        "compensation": {
            "boundary": "compensated_gate",
            "gate_derivative_ev": 0.0,
            "dipole_derivative_ev": 0.0,
            "compensation_derivative_ev": 0.0,
            "integrated_electrons": nelec,
            "density_electron_error": 0.0,
            "ionic_valence_electrons": reference,
            "total_dipole_ry_au": 0.0,
            "density_precision": 12,
            "density_electron_tolerance": 1.0e-8,
        },
        "mu_calc": target,
        "mu_target": target,
        "potential_calc": None,
        "potential_target": None,
        "residual_mu": 0.0,
        "residual_v": 0.0,
        "omega_correction": correction,
        "nelec": nelec,
        "reference_electrons": reference,
        "delta_nelec": delta,
        "forces": np.zeros((len(atoms), 3)),
        "scf_converged": True,
        "cp_converged": True,
        "cp_iterations": 2,
        "cp_history": [{"nelec": nelec, "converged": True}],
    }


def _publish_checkpoint(atoms: Atoms, config: dict, *, nelec: float = 12.5) -> dict:
    """Publish a valid CP envelope and return its identity."""
    cp = config["calculator"]["constant_potential"]
    identity = constant_potential_identity_for_config(
        config, target=float(cp["target_mu_ev"])
    )
    assert identity is not None
    publish_constant_potential_facts(
        atoms,
        _cp_results(atoms, target=float(cp["target_mu_ev"]), nelec=nelec),
        identity,
    )
    return identity


def test_restart_checkpoint_returns_evaluated_electrons_and_rejects_stale_state(tmp_path):
    """Only a complete, matching facts envelope can provide a warm-start count."""
    config = _config(tmp_path)
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    identity = _publish_checkpoint(atoms, config)

    assert cp_module.constant_potential_restart_initial_electrons(
        atoms,
        identity,
        potential_tolerance_v=1.0e-6,
    ) == pytest.approx(12.5)

    payload = json.loads(json.dumps(atoms.info["atst_constant_potential_facts"]))
    payload["facts"]["efermi"] += 1.0e-3
    payload["facts"]["mu_calc"] += 1.0e-3
    payload["facts"]["residual_mu"] = 1.0e-3
    payload["facts"]["residual_v"] = 1.0e-3
    atoms.info["atst_constant_potential_facts"] = payload
    with pytest.raises(ConstantPotentialError, match="tolerance"):
        cp_module.constant_potential_restart_initial_electrons(
            atoms, identity, potential_tolerance_v=1.0e-6
        )
    assert cp_module.constant_potential_restart_initial_electrons(
        atoms, identity, potential_tolerance_v=1.0e-6, allow_recompute=True
    ) is None
    _publish_checkpoint(atoms, config)

    changed_target_identity = constant_potential_identity_for_config(
        config, target=-14.0
    )
    assert changed_target_identity is not None
    with pytest.raises(ConstantPotentialError, match="identity"):
        cp_module.constant_potential_restart_initial_electrons(
            atoms, changed_target_identity, potential_tolerance_v=1.0e-6
        )

    changed = dict(config)
    changed["calculator"] = dict(config["calculator"])
    changed["calculator"]["constant_potential"] = dict(
        config["calculator"]["constant_potential"]
    )
    changed["calculator"]["abacus"] = dict(config["calculator"]["abacus"])
    changed["calculator"]["abacus"]["parameters"] = {"zgate": 0.8, "nelec": 8.0}
    changed_identity = constant_potential_identity_for_config(
        changed, target=-15.0
    )
    assert changed_identity is not None
    with pytest.raises(ConstantPotentialError, match="identity"):
        cp_module.constant_potential_restart_initial_electrons(
            atoms, changed_identity, potential_tolerance_v=1.0e-6
        )

    atoms.positions[0, 0] += 0.1
    with pytest.raises(ConstantPotentialError, match="geometry"):
        cp_module.constant_potential_restart_initial_electrons(
            atoms, identity, potential_tolerance_v=1.0e-6
        )


def test_relax_restart_passes_last_evaluated_nelec_to_new_calculator(monkeypatch, tmp_path):
    """A nuclear restart rebuilds the calculator with that frame's CP count."""
    from atst_tools.workflows import relax

    config = _config(tmp_path)
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    _publish_checkpoint(atoms, config, nelec=12.5)
    captured: dict[str, object] = {}

    class FakeOptimizer:
        nsteps = 0

        def __init__(self, atoms, trajectory=None, logfile=None):
            pass

        def run(self, fmax=None, steps=None):
            return True

    def fake_factory(*args, **kwargs):
        captured.update(kwargs)
        return SinglePointCalculator(atoms, energy=1.0, forces=np.zeros((1, 3)))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(relax, "get_last_frame", lambda path: atoms)
    monkeypatch.setattr(relax, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(relax, "write_artifact_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(relax.CalculatorFactory, "get_calculator", fake_factory)
    monkeypatch.setattr(relax, "FIRE", FakeOptimizer)

    calc_config = {
        "type": "relax",
        "init_structure": "initial.traj",
        "restart": True,
        "optimizer": "FIRE",
        "fmax": 0.1,
        "max_steps": 1,
        "trajectory": "relax.traj",
        "logfile": "relax.log",
        "directory": str(tmp_path / "relax-run"),
    }
    RelaxWorkflow = relax.RelaxWorkflow
    RelaxWorkflow(config, "abacus", calc_config).run()

    assert captured["constant_potential_initial"] == pytest.approx(12.5)


def test_non_cp_relax_restart_keeps_legacy_factory_arguments(monkeypatch, tmp_path):
    """Ordinary ASE restart does not acquire CP-only checkpoint behavior."""
    from atst_tools.workflows import relax

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {"directory": str(tmp_path / "abacus"), "parameters": {}},
        },
        "calculation": {"type": "relax"},
    }
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    captured: dict[str, object] = {}

    class FakeOptimizer:
        nsteps = 0

        def __init__(self, atoms, trajectory=None, logfile=None):
            pass

        def run(self, fmax=None, steps=None):
            return True

    def fake_factory(*args, **kwargs):
        captured.update(kwargs)
        return SinglePointCalculator(atoms, energy=1.0, forces=np.zeros((1, 3)))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(relax, "get_last_frame", lambda path: atoms)
    monkeypatch.setattr(relax, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(relax, "write_artifact_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(relax.CalculatorFactory, "get_calculator", fake_factory)
    monkeypatch.setattr(relax, "FIRE", FakeOptimizer)

    RelaxWorkflow = relax.RelaxWorkflow
    RelaxWorkflow(
        config,
        "abacus",
        {
            "type": "relax",
            "init_structure": "initial.traj",
            "restart": True,
            "optimizer": "FIRE",
            "fmax": 0.1,
            "max_steps": 1,
            "trajectory": "relax.traj",
            "logfile": "relax.log",
            "directory": str(tmp_path / "relax-run"),
        },
    ).run()

    assert "constant_potential_initial" not in captured


@pytest.mark.parametrize("parallel,rank,expected", [(False, 0, [11.25, 12.75]), (True, 0, [11.25]), (True, 1, [12.75])])
def test_neb_restart_warm_starts_each_image_from_its_own_facts(monkeypatch, tmp_path, parallel, rank, expected):
    """NEB restart never shares one image's electronic state with another."""
    from atst_tools.scripts import main
    from helpers import FakeWorld

    config = _config(tmp_path)
    config["calculation"] = {"type": "neb"}
    chain = [Atoms("H", positions=[[float(index), 0.0, 0.0]]) for index in range(4)]
    _publish_checkpoint(chain[1], config, nelec=11.25)
    _publish_checkpoint(chain[2], config, nelec=12.75)
    captured: list[dict[str, object]] = []

    world = FakeWorld(size=2 if parallel else 1, rank=rank)

    class FakeNEB:
        def __init__(self, images, **kwargs):
            self.images = images

    class FakeOptimizer:
        nsteps = 0

        def __init__(self, neb, trajectory=None, **kwargs):
            pass

        def run(self, fmax=None, steps=None):
            return True

    def fake_factory(*args, **kwargs):
        captured.append(dict(kwargs))
        return SinglePointCalculator(chain[1], energy=1.0, forces=np.zeros((1, 3)))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "get_ase_world", lambda: world)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "get_last_neb_band", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    # Endpoint collective synchronization has separate MPI tests; this probe
    # exercises CP calculator attachment and rank-owned electronic state.
    monkeypatch.setattr(main, "_sync_parallel_endpoint_results", lambda images, *args: images)
    monkeypatch.setattr(main, "write_artifact_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.CalculatorFactory, "get_calculator", fake_factory)
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)

    calc_config = {
        "type": "neb",
        "init_chain": "chain.traj",
        "restart": True,
        "parallel": parallel,
        "max_steps": 1,
    }
    main.run_neb(config, "abacus", calc_config, world=world)

    assert [item["constant_potential_initial"] for item in captured] == pytest.approx(expected)
    if parallel:
        assert len(captured) == 1
        assert Path(captured[0]["directory"]).name == f"image_{rank + 1:03d}"
        assert chain[rank + 1].calc is not None
        assert chain[2 - rank].calc is None


def test_neb_restart_rejects_changed_electronic_identity_before_calculation(
    monkeypatch, tmp_path
):
    """A stale CP image is rejected instead of silently using a fresh guess."""
    from atst_tools.scripts import main

    stored_config = _config(tmp_path, zgate=0.7)
    run_config = _config(tmp_path, zgate=0.8)
    run_config["calculation"] = {"type": "neb"}
    chain = [Atoms("H", positions=[[float(index), 0.0, 0.0]]) for index in range(3)]
    _publish_checkpoint(chain[1], stored_config, nelec=12.0)
    calls = []

    class World:
        size = 1
        rank = 0

    class FakeNEB:
        def __init__(self, images, **kwargs):
            pass

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None, **kwargs):
            pass

        def run(self, fmax=None, steps=None):
            return True

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "read", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "get_last_neb_band", lambda *args, **kwargs: chain)
    monkeypatch.setattr(main, "get_ase_world", lambda: World())
    monkeypatch.setattr(main, "ensure_neb_endpoint_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "write_artifact_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(main, "get_optimizer", lambda name: FakeOptimizer)
    monkeypatch.setattr(
        main.CalculatorFactory,
        "get_calculator",
        lambda *args, **kwargs: calls.append(kwargs) or SinglePointCalculator(
            chain[1], energy=1.0, forces=np.zeros((1, 3))
        ),
    )

    with pytest.raises(ConstantPotentialError, match="identity"):
        main.run_neb(run_config, "abacus", {"type": "neb", "init_chain": "chain.traj", "restart": True}, world=World())
    assert calls == []


