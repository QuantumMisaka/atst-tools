"""Tests for reactive-mode enumeration helpers."""

from __future__ import annotations

import pytest
from ase import Atoms

from atst_tools.utils.reactive_modes import enumerate_reactive_bond_modes, parse_index_set


def test_parse_index_set_sorts_deduplicates_and_accepts_reverse_ranges():
    assert parse_index_set("3-1,2, 5,5", natoms=5) == [0, 1, 2, 4]
    assert parse_index_set([2, 1, 2], natoms=3) == [0, 1]


def test_parse_index_set_rejects_out_of_range_indices():
    with pytest.raises(ValueError, match="Atom index out of range: 0"):
        parse_index_set("0", natoms=3)
    with pytest.raises(ValueError, match="Atom index out of range: 4"):
        parse_index_set("4", natoms=3)


def test_reactive_modes_requires_non_empty_molecule_selection():
    atoms = Atoms("HPt", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])

    with pytest.raises(ValueError, match="molecule_indices"):
        enumerate_reactive_bond_modes(atoms, molecule_indices="")


def test_reactive_modes_applies_cutoff_and_active_filters():
    atoms = Atoms(
        "HOPt2",
        positions=[
            [0.0, 0.0, 0.0],
            [5.0, 0.0, 0.0],
            [0.8, 0.0, 0.0],
            [5.4, 0.0, 0.0],
        ],
    )

    modes = enumerate_reactive_bond_modes(
        atoms,
        molecule_indices="1-2",
        active_molecule_indices="2",
        active_catalyst_indices="3-4",
        cutoff_A=1.0,
    )

    assert [mode["reactive_bonds_1based"] for mode in modes] == [[[2, 4]]]


def test_reactive_modes_can_emit_ranked_multi_bond_modes():
    atoms = Atoms(
        "H2Pt2",
        positions=[
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.7, 0.0, 0.0],
            [2.9, 0.0, 0.0],
        ],
    )

    modes = enumerate_reactive_bond_modes(
        atoms,
        molecule_indices="1-2",
        cutoff_A=1.1,
        max_modes=4,
        max_bonds_per_mode=2,
    )

    assert modes[0]["reactive_bonds_1based"] == [[1, 3]]
    assert any(mode["reactive_bonds_1based"] == [[1, 3], [2, 4]] for mode in modes)
