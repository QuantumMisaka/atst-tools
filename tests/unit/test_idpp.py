import numpy as np
from ase import Atoms

import pytest

from atst_tools.utils.idpp import Fast_IDPPSolver, align_atom_indices, robust_interpolate, set_fix_for_Atoms, set_magmom_for_Atoms


def test_fast_idpp_uses_cartesian_nearest_image_for_skewed_cells():
    cell = np.array(
        [
            [12.32269518, 0.0, 0.0],
            [0.0, 19.99999267, 0.0],
            [-6.16153959, 0.0, 10.67154129],
        ]
    )
    frac_i = np.array([0.10, 0.10, 0.10])
    frac_j = frac_i - np.array([-0.534498273, 0.000165182, -0.069037364])
    positions = np.dot(np.vstack([frac_i, frac_j]), cell)
    atoms = Atoms("CH", positions=positions, cell=cell, pbc=True)
    solver = Fast_IDPPSolver([atoms, atoms.copy(), atoms.copy()])

    assert np.allclose(solver._nearest_image(frac_i, frac_j), [0.0, 0.0, 0.0])
    assert not np.allclose(np.round(frac_i - frac_j), [0.0, 0.0, 0.0])


def test_align_atom_indices_reorders_same_element_targets_without_moving_atoms():
    reference = Atoms("H2", positions=[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], cell=[8.0, 8.0, 8.0], pbc=True)
    target = Atoms("H2", positions=[[2.1, 0.0, 0.0], [0.1, 0.0, 0.0]], cell=[8.0, 8.0, 8.0], pbc=True)

    aligned = align_atom_indices(reference, target)

    np.testing.assert_allclose(aligned.positions, [[0.1, 0.0, 0.0], [2.1, 0.0, 0.0]])
    np.testing.assert_allclose(aligned.cell.array, reference.cell.array)
    assert aligned.pbc.all()


def test_align_atom_indices_rejects_element_count_mismatch():
    reference = Atoms("HH", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    target = Atoms("HO", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])

    with pytest.raises(ValueError, match="Count mismatch"):
        align_atom_indices(reference, target)


def test_robust_interpolate_uses_short_periodic_path():
    start = Atoms("H", scaled_positions=[[0.9, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    end = Atoms("H", scaled_positions=[[0.1, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)

    path = robust_interpolate(start, end, nimages=1)

    assert len(path) == 3
    np.testing.assert_allclose(path[1].get_scaled_positions(wrap=False), [[1.0, 0.0, 0.0]])


def test_fix_and_magmom_helpers_apply_expected_metadata():
    atoms = Atoms(
        "FeH",
        scaled_positions=[[0.0, 0.1, 0.0], [0.0, 0.8, 0.0]],
        cell=[5.0, 5.0, 5.0],
        pbc=True,
    )

    set_fix_for_Atoms(atoms, fix_height=0.2, fix_dir=1)
    set_magmom_for_Atoms(atoms, mag_ele=["Fe"], mag_num=[2.5])

    assert atoms.constraints
    np.testing.assert_allclose(atoms.get_initial_magnetic_moments(), [2.5, 0.0])
