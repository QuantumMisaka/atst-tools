"""Reactive-mode enumeration helpers for CCQN workflows."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable

import numpy as np
from ase import Atoms
from ase.data import chemical_symbols, covalent_radii
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


def detect_bond_changes(
    init_atoms: Atoms,
    final_atoms: Atoms,
    *,
    molecule_indices: Any = None,
    bond_detect_scale: float = 1.2,
    change_tol_A: float = 0.1,
    include_catalyst_catalyst: bool = False,
) -> dict[str, Any]:
    """Detect formed, broken and significantly changed bonds between two frames.

    This is a *reaction description proposal*, not a universal reaction
    definition.  Bonds are inferred from the sum of Cordero covalent radii
    scaled by ``bond_detect_scale``; the ASE table is used directly and is
    recorded in the result.  A bond is only reported when its minimum-image
    length changes by more than ``change_tol_A``, so a bond that merely
    crosses the cutoff because of print or relaxation noise is ignored.

    Args:
        init_atoms: Initial-state frame.
        final_atoms: Final-state frame with the same atom order and symbols.
        molecule_indices: Optional 1-based active molecule/adsorbate indices.
            When given, only bonds with at least one atom in this set are
            considered unless ``include_catalyst_catalyst`` is true.
        bond_detect_scale: Multiplier on the sum of covalent radii (default 1.2).
        change_tol_A: Minimum absolute bond-length change in Angstrom.
        include_catalyst_catalyst: Keep catalyst-catalyst bonds even when a
            molecule filter is supplied.

    Returns:
        A JSON-compatible dict with ``bonds``, ``reactive_atoms_1based`` and
        the radii provenance.  ``bonds`` entries carry the 1-based pair,
        ``kind`` (``formed``/``broken``/``changed``), and the minimum-image
        distances in both frames.
    """
    if len(init_atoms) != len(final_atoms):
        raise ValueError("init_atoms and final_atoms must contain the same number of atoms")
    init_symbols = init_atoms.get_chemical_symbols()
    final_symbols = final_atoms.get_chemical_symbols()
    if init_symbols != final_symbols:
        raise ValueError("init_atoms and final_atoms must preserve atom order and symbols")

    natoms = len(init_atoms)
    molecule = (
        set(parse_index_set(molecule_indices, natoms=natoms))
        if molecule_indices not in (None, "")
        else set()
    )
    numbers = init_atoms.get_atomic_numbers()
    radii = np.asarray([covalent_radii[int(number)] for number in numbers], dtype=float)
    cutoffs = (radii[:, None] + radii[None, :]) * float(bond_detect_scale)
    init_distances = np.asarray(init_atoms.get_all_distances(mic=True), dtype=float)
    final_distances = np.asarray(final_atoms.get_all_distances(mic=True), dtype=float)

    bonds: list[dict[str, Any]] = []
    for left in range(natoms):
        for right in range(left + 1, natoms):
            if molecule and not include_catalyst_catalyst:
                if left not in molecule and right not in molecule:
                    continue
            cutoff = float(cutoffs[left, right])
            d_init = float(init_distances[left, right])
            d_final = float(final_distances[left, right])
            in_init = d_init <= cutoff
            in_final = d_final <= cutoff
            delta = d_final - d_init
            if in_init and not in_final and delta > float(change_tol_A):
                kind = "broken"
            elif in_final and not in_init and -delta > float(change_tol_A):
                kind = "formed"
            elif in_init and in_final and abs(delta) > float(change_tol_A):
                kind = "changed"
            else:
                continue
            bonds.append(
                {
                    "pair": [left + 1, right + 1],
                    "label": f"{init_symbols[left]}{left + 1}-{init_symbols[right]}{right + 1}",
                    "kind": kind,
                    "d_init_A": d_init,
                    "d_final_A": d_final,
                    "delta_A": delta,
                    "cutoff_A": cutoff,
                }
            )

    reactive_atoms = sorted({atom for bond in bonds for atom in bond["pair"]})
    fallback_elements = sorted(
        {
            chemical_symbols[int(number)]
            for number in numbers
            if np.isclose(float(covalent_radii[int(number)]), 2.0)
        }
    )
    return {
        "index_base": 1,
        "source": "is_fs_diff",
        "radii_source": "ase.data.covalent_radii (Cordero et al. 2008)",
        "bond_detect_scale": float(bond_detect_scale),
        "change_tol_A": float(change_tol_A),
        "radii_quality": "fallback" if fallback_elements else "cordero",
        "fallback_elements": fallback_elements,
        "bonds": bonds,
        "reactive_atoms_1based": reactive_atoms,
    }
