"""Structure I/O helpers for ATST-Tools."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixCartesian
from ase.io import read
from ase.units import Bohr

from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru


def read_structure(filename: str | Path, format: str | None = None, *, parallel: bool = True) -> Atoms:
    """Read a structure file, including ABACUS STRU files."""
    path = Path(filename)
    if format == "abacus" or path.name == "STRU" or path.suffix.lower() == ".stru":
        return read_abacus_stru(path)
    return read(str(path), format=format, parallel=parallel)


def read_abacus_stru(filename: str | Path) -> Atoms:
    """Convert an ABACUS STRU file into an ASE Atoms object."""
    data = read_stru(str(filename))
    scale = float(data["lat"].get("const", 1.0)) * Bohr
    cell = np.array(data["lat"]["vec"], dtype=float) * scale
    coord_type = data.get("coord_type", "Cartesian").lower()

    symbols = []
    coords = []
    fixed_indices = []
    cartesian_constraints = []
    magmoms = []

    for species in data["species"]:
        symbol = species["symbol"]
        for atom in species.get("atom", []):
            symbols.append(symbol)
            coords.append(atom["coord"])
            mobility = atom.get("m")
            if mobility is not None:
                mobility = [int(value) for value in mobility]
                if not any(mobility):
                    fixed_indices.append(len(symbols) - 1)
                elif not all(mobility):
                    mask = [not bool(value) for value in mobility]
                    cartesian_constraints.append(FixCartesian(len(symbols) - 1, mask))
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

    constraints = []
    if fixed_indices:
        constraints.append(FixAtoms(indices=fixed_indices))
    constraints.extend(cartesian_constraints)
    if constraints:
        atoms.set_constraint(constraints)
    if magmoms:
        atoms.set_initial_magnetic_moments(magmoms)
    return atoms
