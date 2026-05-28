"""Reactive-mode enumeration helpers for CCQN workflows."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable

import numpy as np
from ase.data import covalent_radii
from ase.geometry import find_mic


def parse_index_set(value: Any, natoms: int | None = None) -> list[int]:
    """Parse 1-based atom-index selectors into sorted 0-based indices.

    Args:
        value: ``None``, a comma string such as ``"1-3,5"``, or a sequence of
            integer-like values.
        natoms: Optional atom count used for bounds validation.

    Returns:
        Sorted unique 0-based atom indices.
    """
    if value in (None, ""):
        return []
    raw: list[int] = []
    if isinstance(value, str):
        for token in value.split(","):
            text = token.strip()
            if not text:
                continue
            if "-" in text:
                left, right = [int(item) for item in text.split("-", 1)]
                if right < left:
                    left, right = right, left
                raw.extend(range(left - 1, right))
            else:
                raw.append(int(text) - 1)
    else:
        raw.extend(int(item) - 1 for item in value)
    indices = sorted(set(raw))
    for index in indices:
        if index < 0 or (natoms is not None and index >= natoms):
            raise ValueError(f"Atom index out of range: {index + 1}")
    return indices


def _as_index_set(value: Any, fallback: Iterable[int], natoms: int) -> list[int]:
    parsed = parse_index_set(value, natoms=natoms)
    return parsed or sorted(set(int(item) for item in fallback))


def enumerate_reactive_bond_modes(
    atoms,
    *,
    molecule_indices: Any,
    active_molecule_indices: Any = None,
    active_catalyst_indices: Any = None,
    cutoff_A: float = 3.0,
    max_modes: int = 20,
    max_bonds_per_mode: int = 1,
    bond_detect_scale: float = 1.2,
    allow_cat_cat_modes: bool = False,
) -> list[dict[str, Any]]:
    """Enumerate ranked reactive-bond modes for IC-based CCQN.

    The helper is intentionally conservative: it ranks molecule-catalyst pairs
    by minimum-image distance and optionally forms small combinations from the
    best single-bond candidates. It does not create new chemistry-specific
    templates.
    """
    natoms = len(atoms)
    if max_modes <= 0:
        return []
    molecule = set(parse_index_set(molecule_indices, natoms=natoms))
    if not molecule:
        raise ValueError("auto_reactive_bonds.molecule_indices must not be empty")
    catalyst_default = [index for index in range(natoms) if index not in molecule]
    mol_active = _as_index_set(active_molecule_indices, molecule, natoms)
    cat_active = _as_index_set(active_catalyst_indices, catalyst_default, natoms)
    candidates: list[dict[str, Any]] = []
    positions = atoms.get_positions()
    symbols = atoms.get_chemical_symbols()
    numbers = atoms.get_atomic_numbers()
    for left in mol_active:
        for right in cat_active:
            if left == right:
                continue
            if not allow_cat_cat_modes and left not in molecule and right not in molecule:
                continue
            mic, distance = find_mic(
                positions[right] - positions[left],
                atoms.get_cell(),
                atoms.get_pbc(),
            )
            distance_A = float(np.linalg.norm(mic))
            if distance_A > float(cutoff_A):
                continue
            covalent_cutoff = float(covalent_radii[numbers[left]] + covalent_radii[numbers[right]]) * float(
                bond_detect_scale
            )
            bond = tuple(sorted((left, right)))
            candidates.append(
                {
                    "reactive_bonds": [bond],
                    "reactive_bonds_1based": [[bond[0] + 1, bond[1] + 1]],
                    "distance_A": distance_A,
                    "score": distance_A,
                    "label": f"{symbols[bond[0]]}{bond[0] + 1}-{symbols[bond[1]]}{bond[1] + 1}",
                    "within_covalent_cutoff": distance_A <= covalent_cutoff,
                }
            )
    candidates.sort(key=lambda item: (item["score"], item["reactive_bonds_1based"]))
    modes = candidates[:max_modes]
    if max_bonds_per_mode > 1 and len(candidates) > 1:
        for n_bonds in range(2, int(max_bonds_per_mode) + 1):
            for combo in combinations(candidates, n_bonds):
                bonds = sorted({bond for item in combo for bond in item["reactive_bonds"]})
                if len(bonds) != n_bonds:
                    continue
                score = float(sum(item["score"] for item in combo) / n_bonds)
                modes.append(
                    {
                        "reactive_bonds": bonds,
                        "reactive_bonds_1based": [[i + 1, j + 1] for i, j in bonds],
                        "distance_A": score,
                        "score": score,
                        "label": "+".join(item["label"] for item in combo),
                    }
                )
    modes.sort(key=lambda item: (item["score"], item["reactive_bonds_1based"]))
    return modes[:max_modes]
