"""CCQN reactive-bond selection: prefer IS/product changes over proximity."""

from ase import Atoms

from atst_tools.mep.ccqn import _select_reactive_bonds


def test_select_reactive_bonds_prefers_is_product_change():
    init = Atoms("CO", positions=[[0.0, 0.0, 0.0], [3.1, 0.0, 0.0]])
    final = Atoms("CO", positions=[[0.0, 0.0, 0.0], [1.17, 0.0, 0.0]])

    modes, selected, bonds, source = _select_reactive_bonds(
        init,
        final,
        {"molecule_indices": [1, 2], "max_bonds_per_mode": 1},
    )

    assert source == "is_fs_diff"
    assert selected["reactive_bonds_1based"] == [[1, 2]]
    assert bonds == [(0, 1)]
    assert modes == [selected]


def test_select_reactive_bonds_falls_back_to_proximity_without_product():
    atoms = Atoms(
        "COPd",
        positions=[[0.0, 0.0, 0.0], [1.17, 0.0, 0.0], [2.3, 0.0, 0.0]],
    )

    modes, selected, bonds, source = _select_reactive_bonds(
        atoms,
        None,
        {"molecule_indices": [1, 2], "cutoff_A": 3.0, "max_modes": 5},
    )

    assert source == "auto"
    assert modes
    assert selected in modes
    assert bonds
    assert all(0 in pair or 1 in pair for pair in bonds)


def test_select_reactive_bonds_falls_back_when_product_has_no_change():
    atoms = Atoms(
        "COPd",
        positions=[[0.0, 0.0, 0.0], [1.17, 0.0, 0.0], [2.3, 0.0, 0.0]],
    )

    modes, selected, bonds, source = _select_reactive_bonds(
        atoms,
        atoms.copy(),
        {"molecule_indices": [1, 2], "cutoff_A": 3.0, "max_modes": 5},
    )

    assert source == "auto"
    assert modes
