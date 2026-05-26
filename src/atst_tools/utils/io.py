"""Structure I/O helpers for ATST-Tools."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read
from ase.units import Bohr

from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru


def read_structure(filename: str | Path, format: str | None = None) -> Atoms:
    """Read a structure file, including ABACUS STRU files."""
    path = Path(filename)
    if format == "abacus" or path.name == "STRU" or path.suffix.lower() == ".stru":
        return read_abacus_stru(path)
    return read(str(path), format=format)


def read_abacus_stru(filename: str | Path) -> Atoms:
    """Convert an ABACUS STRU file into an ASE Atoms object."""
    data = read_stru(str(filename))
    scale = float(data["lat"].get("const", 1.0)) * Bohr
    cell = np.array(data["lat"]["vec"], dtype=float) * scale
    coord_type = data.get("coord_type", "Cartesian").lower()

    symbols = []
    coords = []
    fixed_indices = []
    magmoms = []

    for species in data["species"]:
        symbol = species["symbol"]
        for atom in species.get("atom", []):
            symbols.append(symbol)
            coords.append(atom["coord"])
            mobility = atom.get("m")
            if mobility is not None and not any(int(value) for value in mobility):
                fixed_indices.append(len(symbols) - 1)
            mag = atom.get("mag", species.get("mag_each", 0.0))
            if isinstance(mag, tuple):
                magmoms.append(mag[1])
            else:
                magmoms.append(float(mag))

    atoms = Atoms(symbols=symbols, cell=cell, pbc=True)
    coords_array = np.array(coords, dtype=float)
    if coord_type.startswith("direct"):
        atoms.set_scaled_positions(coords_array)
    else:
        atoms.set_positions(coords_array * scale)

    if fixed_indices:
        atoms.set_constraint(FixAtoms(indices=fixed_indices))
    if magmoms:
        atoms.set_initial_magnetic_moments(magmoms)
    return atoms
