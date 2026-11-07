"""Candidate and reaction-atom selection helpers for D2S-style workflows."""

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator

from atst_tools.utils.analysis import (
    displacement_share,
    get_anchored_displacement_analysis,
    get_displacement_analysis,
    path_progress,
    rank_candidates,
)
from atst_tools.utils.reactive_modes import detect_bond_changes


def _image(symbols, positions, energy=0.0):
    atoms = Atoms(symbols, positions=positions)
    atoms.calc = SinglePointCalculator(
        atoms, energy=energy, forces=np.zeros((len(atoms), 3))
    )
    atoms.info["energy"] = energy
    return atoms


def test_anchored_selection_uses_candidate_not_global_maximum():
    chain = [
        _image("H", [[0.0, 0.0, 0.0]], energy=0.0),
        _image("H", [[0.3, 0.0, 0.0]], energy=0.2),
        _image("H", [[0.6, 0.0, 0.0]], energy=2.0),
        _image("H", [[0.9, 0.0, 0.0]], energy=0.3),
    ]

    anchored = get_anchored_displacement_analysis(chain, 1, thr=0.1)
    global_max = get_displacement_analysis(chain, thr=0.1)

    assert anchored[0] == 1
    assert global_max[0] == 2


def test_displacement_share_uses_minimum_image():
    cell = [10.0, 10.0, 10.0]
    chain = [
        _image("H2", [[0.1, 0.0, 0.0], [5.0, 0.0, 0.0]], energy=0.0),
        _image("H2", [[9.9, 0.0, 0.0], [5.1, 0.0, 0.0]], energy=1.0),
        _image("H2", [[9.7, 0.0, 0.0], [5.2, 0.0, 0.0]], energy=0.0),
    ]
    for atoms in chain:
        atoms.set_cell(cell)
        atoms.set_pbc(True)

    share = displacement_share(chain, 1)

    np.testing.assert_allclose(share.sum(), 1.0)
    assert share[0] == pytest.approx(2.0 / 3.0, abs=1e-3)
    assert share[1] == pytest.approx(1.0 / 3.0, abs=1e-3)


def test_path_progress_is_zero_at_init_and_one_at_final():
    chain = [
        _image("H", [[0.0, 0.0, 0.0]], energy=0.0),
        _image("H", [[0.5, 0.0, 0.0]], energy=1.0),
        _image("H", [[1.0, 0.0, 0.0]], energy=0.0),
    ]

    progress = path_progress(chain)

    np.testing.assert_allclose(progress, [0.0, 0.5, 1.0])


def test_rank_candidates_prefers_in_window_before_global_maximum():
    chain = [
        _image("H", [[0.0, 0.0, 0.0]], energy=0.0),
        _image("H", [[0.05, 0.0, 0.0]], energy=2.0),
        _image("H", [[0.50, 0.0, 0.0]], energy=0.5),
        _image("H", [[0.95, 0.0, 0.0]], energy=1.0),
        _image("H", [[1.0, 0.0, 0.0]], energy=0.0),
    ]

    ranked = rank_candidates(chain, k=3)

    assert ranked[0]["index"] == 2
    assert ranked[0]["flags"] == []
    assert {item["index"] for item in ranked} == {2, 1, 3}


def test_detect_bond_changes_forms_and_breaks_co_bond():
    init = Atoms("CO", positions=[[0.0, 0.0, 0.0], [3.1, 0.0, 0.0]])
    final = Atoms("CO", positions=[[0.0, 0.0, 0.0], [1.17, 0.0, 0.0]])

    result = detect_bond_changes(init, final)

    assert result["radii_source"].startswith("ase.data.covalent_radii")
    assert result["reactive_atoms_1based"] == [1, 2]
    assert [bond["kind"] for bond in result["bonds"]] == ["formed"]
    assert result["bonds"][0]["pair"] == [1, 2]

    broken = detect_bond_changes(final, init)
    assert [bond["kind"] for bond in broken["bonds"]] == ["broken"]


def test_detect_bond_changes_reports_only_chemical_changes():
    init = Atoms("CO", positions=[[0.0, 0.0, 0.0], [1.17, 0.0, 0.0]])
    final = Atoms("CO", positions=[[0.0, 0.0, 0.0], [1.35, 0.0, 0.0]])

    result = detect_bond_changes(init, final, change_tol_A=0.1)

    assert [bond["kind"] for bond in result["bonds"]] == ["changed"]

    tiny = detect_bond_changes(init, init)
    assert tiny["bonds"] == []
    assert tiny["reactive_atoms_1based"] == []


def test_detect_bond_changes_molecule_filter_skips_catalyst_catalyst():
    init = Atoms(
        "Pd2CO",
        positions=[
            [0.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [0.0, 0.0, 5.0],
            [3.1, 0.0, 5.0],
        ],
    )
    final = Atoms(
        "Pd2CO",
        positions=[
            [0.0, 0.0, 0.0],
            [2.8, 0.0, 0.0],
            [0.0, 0.0, 5.0],
            [1.17, 0.0, 5.0],
        ],
    )

    unfiltered = detect_bond_changes(init, final)
    filtered = detect_bond_changes(init, final, molecule_indices=[3, 4])

    assert any(bond["pair"] == [1, 2] for bond in unfiltered["bonds"])
    assert all(bond["pair"] != [1, 2] for bond in filtered["bonds"])
    assert filtered["reactive_atoms_1based"] == [3, 4]


def test_detect_bond_changes_records_fallback_radii():
    init = Atoms("Pa2", positions=[[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    final = Atoms("Pa2", positions=[[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])

    result = detect_bond_changes(init, final)

    assert result["radii_quality"] == "fallback"
    assert result["fallback_elements"] == ["Pa"]
