"""Lightweight shared fixtures for unit tests."""

from __future__ import annotations

import numpy as np
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.singlepoint import SinglePointCalculator


def make_atoms(symbols: str = "H", energy: float = 0.0, positions=None) -> Atoms:
    """Return an ``Atoms`` object with single-point energy and zero forces."""
    if positions is None:
        positions = [[0.0, 0.0, 0.0]]
    atoms = Atoms(symbols, positions=positions)
    atoms.calc = SinglePointCalculator(
        atoms,
        energy=energy,
        forces=np.zeros((len(atoms), 3)),
    )
    return atoms


class DummyCalc(Calculator):
    """Small deterministic calculator for unit tests."""

    implemented_properties = ["energy", "forces", "stress"]

    def __init__(self, energy: float = 3.0):
        super().__init__()
        self.energy = energy

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = self.energy
        self.results["forces"] = np.zeros((len(atoms), 3))
        self.results["stress"] = np.zeros(6)


class FakeWorld:
    """Minimal ASE/MPI world stand-in."""

    def __init__(self, size: int = 1, rank: int = 0):
        self.size = size
        self.rank = rank
        self.barriers = 0

    def barrier(self):
        self.barriers += 1


class FakeReducingWorld(FakeWorld):
    """Fake world that supports reductions and rejects broadcasts."""

    def __init__(self, size: int = 2, rank: int = 0):
        super().__init__(size=size, rank=rank)
        self.sums = 0

    def sum(self, value, root=-1):
        self.sums += 1
        return value if isinstance(value, float) else None

    def broadcast(self, value, root):
        raise AssertionError("parallel execution should use reductions, not broadcasts")
