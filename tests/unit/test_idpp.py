from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixCartesian
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write

import pytest

from atst_tools.external.ASE_interface.abacuslite.io.generalio import write_stru
from atst_tools.utils import idpp
from atst_tools.utils.idpp import Fast_IDPPSolver, align_atom_indices, robust_interpolate, set_fix_for_Atoms, set_magmom_for_Atoms
from atst_tools.utils.io import read_structure


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


def test_fast_idpp_nearest_image_is_stable_for_half_cell_ties():
    atoms = Atoms("HH", scaled_positions=[[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    solver = Fast_IDPPSolver([atoms, atoms.copy(), atoms.copy()])
    frac_i = np.array([0.0, 0.0, 0.0])

    left = solver._nearest_image(frac_i, np.array([0.5 - 1e-10, 0.0, 0.0]))
    right = solver._nearest_image(frac_i, np.array([0.5 + 1e-10, 0.0, 0.0]))

    np.testing.assert_allclose(left, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(right, [0.0, 0.0, 0.0])


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


@pytest.mark.parametrize("method", ["linear", "IDPP"])
def test_preprocessing_preserves_cell_rounding_within_tolerance(method):
    start = Atoms("H", positions=[[1, 0, 0]], cell=[10, 10, 10], pbc=True)
    end = Atoms("H", positions=[[2, 0, 0]], cell=[10.000003, 10, 10], pbc=True)
    original_cell = end.cell.array.copy()
    aligned = align_atom_indices(start, end)
    path = idpp.interpolate_path(start, end, 1, method=method, quiet=True)
    np.testing.assert_array_equal(aligned.cell.array, original_cell)
    np.testing.assert_array_equal(path[-1].cell.array, original_cell)
    np.testing.assert_array_equal(end.cell.array, original_cell)
    np.testing.assert_array_equal(path[-1].positions, end.positions)


def test_partial_pbc_alignment_keeps_nonperiodic_distance_cartesian():
    reference = Atoms("HH", positions=[[0, 0, 0], [0, 0, 4]], cell=[10, 10, 10], pbc=[1, 1, 0])
    target = Atoms("HH", positions=[[0, 0, 6], [0, 0, 9]], cell=[10, 10, 10], pbc=[1, 1, 0])
    aligned = align_atom_indices(reference, target)
    np.testing.assert_array_equal(aligned.positions[:, 2], [6, 9])


@pytest.mark.parametrize("cell,pbc", [([10, 10, 10], False), ([10, 10, 0], [1, 1, 0])])
def test_idpp_unchanged_nonperiodic_pair_has_zero_objective(cell, pbc):
    atoms = Atoms("HH", positions=[[0, 0, 1], [0, 0, 8]], cell=cell, pbc=pbc)
    solver = Fast_IDPPSolver([atoms, atoms.copy(), atoms.copy()])
    objective, forces = solver._get_funcs_and_forces(np.array([image.positions for image in solver.images]))
    np.testing.assert_allclose(objective, 0, atol=1e-14)
    np.testing.assert_allclose(forces, 0, atol=1e-14)


def test_idpp_unwrapped_periodic_pair_uses_nearest_lattice_image():
    """A 27 Å pair in a 10 Å cell is 3 Å apart under periodic MIC."""
    atoms = Atoms("H2", positions=[[0, 0, 0], [27, 0, 0]], cell=[10, 10, 10], pbc=True)
    images = [atoms.copy() for _ in range(3)]
    solver = Fast_IDPPSolver(images)
    coords = np.array([image.positions for image in solver.images])

    np.testing.assert_allclose(solver.target_dists[0, 0, 1], 3.0)
    np.testing.assert_allclose(solver.translations[0, 0, 1], [-30, 0, 0])
    np.testing.assert_allclose(solver.translations[0, 1, 0], [30, 0, 0])
    objective, forces = solver._get_funcs_and_forces(coords)
    np.testing.assert_allclose(objective, 0, atol=1e-14)
    np.testing.assert_allclose(forces, 0, atol=1e-14)


def test_idpp_integer_lattice_shift_preserves_pair_geometry_and_path():
    """Unwrapping one atom by several lattice vectors leaves IDPP stationary."""
    cell = np.array([[9.0, 0.0, 0.0], [2.0, 8.0, 0.0], [1.0, -1.0, 7.0]])
    base = Atoms("H2", positions=[[0, 0, 0], [2, 1, 0]], cell=cell, pbc=True)
    shifted = base.copy()
    shifted.positions[1] += np.array([3, -4, 2]) @ cell

    for atoms in (base, shifted):
        solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
        coords = np.array([image.positions for image in solver.images])
        objective, forces = solver._get_funcs_and_forces(coords)
        np.testing.assert_allclose(objective, 0, atol=1e-14)
        np.testing.assert_allclose(forces, 0, atol=1e-14)
        path = solver.run(maxiter=2)
        np.testing.assert_allclose(path[1].positions, atoms.positions, atol=1e-14)


def test_idpp_half_cell_tie_is_repeatable_after_integer_unwrapping():
    """Equal-distance images retain the same signed pair vector after wrapping."""
    for distance in (5.0, 35.0, -25.0):
        atoms = Atoms("H2", positions=[[0, 0, 0], [distance, 0, 0]], cell=[10, 10, 10], pbc=True)
        first = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
        second = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
        np.testing.assert_array_equal(first.translations, second.translations)
        np.testing.assert_allclose(distance + first.translations[0, 0, 1, 0], 5.0)
        np.testing.assert_array_equal(first.translations[0, 1, 0], -first.translations[0, 0, 1])


def test_idpp_skew_cell_uses_image_beyond_neighboring_lattice_shifts():
    """An acute cell needs a shift much farther than the old 27 candidates."""
    cell = np.array([[10.0, 0.0, 0.0], [9.9, 0.1, 0.0], [0.0, 0.0, 10.0]])
    atoms = Atoms("H2", scaled_positions=[[0, 0, 0], [0, 0.5, 0]], cell=cell, pbc=True)
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
    coords = np.array([image.positions for image in solver.images])
    translated_pair = coords[1, 1] - coords[1, 0] + solver.translations[0, 0, 1]

    np.testing.assert_allclose(np.linalg.norm(translated_pair), np.sqrt(12.505), atol=1e-12)
    objective, forces = solver._get_funcs_and_forces(coords)
    np.testing.assert_allclose(objective, 0, atol=1e-14)
    np.testing.assert_allclose(forces, 0, atol=1e-14)


@pytest.mark.parametrize("pbc,mic,expected", [([1, 0, 0], True, 27.0), (True, False, 27.0)])
def test_idpp_does_not_wrap_disabled_periodic_directions(pbc, mic, expected):
    """The PBC mask and explicit MIC switch control pair distances."""
    atoms = Atoms("H2", positions=[[0, 0, 0], [0, 27, 0]], cell=[10, 10, 10], pbc=pbc)
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)], mic=mic)
    np.testing.assert_allclose(solver.target_dists[0, 0, 1], expected)
    np.testing.assert_allclose(solver.translations, 0)


def test_interpolation_nonperiodic_zero_cell_uses_cartesian_positions():
    start = Atoms("H", positions=[[0, 0, 0]])
    end = Atoms("H", positions=[[1, 0, 0]])
    np.testing.assert_allclose(robust_interpolate(start, end, 1)[1].positions, [[.5, 0, 0]])


@pytest.mark.parametrize("no_align", [False, True])
def test_generate_warns_before_overriding_cell_and_drops_stale_results(tmp_path, no_align):
    from ase.calculators.singlepoint import SinglePointCalculator

    start = Atoms("H", positions=[[1, 0, 0]], cell=[10, 10, 10], pbc=True)
    end = Atoms("H", positions=[[2, 0, 0]], cell=[10.00002, 10, 10], pbc=True)
    for atoms in (start, end):
        atoms.calc = SinglePointCalculator(atoms, energy=5, forces=np.zeros((1, 3)))
    write(tmp_path / "start.traj", start)
    write(tmp_path / "end.traj", end)
    with pytest.warns(UserWarning, match="reference.*image 0"):
        idpp.generate("linear", 1, str(tmp_path / "start.traj"),
                      str(tmp_path / "end.traj"), str(tmp_path / "path.traj"),
                      format=None, no_align=no_align)
    path = read(tmp_path / "path.traj", ":")
    np.testing.assert_array_equal(path[-1].cell.array, start.cell.array)
    np.testing.assert_array_equal(path[-1].positions, end.positions)
    assert path[-1].info["atst_endpoint_result"] == "placeholder"
    np.testing.assert_array_equal(read(tmp_path / "end.traj").cell.array, end.cell.array)


@pytest.mark.parametrize("method", ["linear", "IDPP"])
def test_segmented_preprocessing_keeps_one_input_cell_reference(tmp_path, method):
    """TS and final rounding do not become an artificial segment mismatch."""
    import warnings

    endpoints = [Atoms("H", positions=[[1 + i*.2, 0, 0]],
                       cell=[10 + delta, 10, 10], pbc=True)
                 for i, delta in enumerate([0, -9e-6, 9e-6])]
    paths = [tmp_path / f"{label}.traj" for label in ("start", "end", "ts")]
    for path, atoms in zip(paths, endpoints):
        write(path, atoms)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        idpp.generate(method, 2, str(paths[0]), str(paths[1]),
                      str(tmp_path / "path.traj"), format=None,
                      ts_file=str(paths[2]), no_align=True)
    # Upstream NumPy/ASE deprecations do not indicate a cell mismatch.
    assert not [warning for warning in caught
                if not issubclass(warning.category, DeprecationWarning)]
    output = read(tmp_path / "path.traj", ":")
    np.testing.assert_array_equal(output[-1].cell.array, endpoints[1].cell.array)


def test_alignment_reorders_cached_forces_with_atom_indices():
    from ase.calculators.singlepoint import SinglePointCalculator

    reference = Atoms("HH", positions=[[0, 0, 0], [2, 0, 0]])
    target = Atoms("HH", positions=[[2, 0, 0], [0, 0, 0]])
    target.calc = SinglePointCalculator(target, energy=5, forces=[[1, 0, 0], [2, 0, 0]])
    aligned = align_atom_indices(reference, target)
    np.testing.assert_array_equal(aligned.get_forces()[:, 0], [2, 1])
    np.testing.assert_array_equal(target.get_forces()[:, 0], [1, 2])


def _constrained_idpp_endpoints():
    """Return a mixed-constraint path with one fixed and two mobile atoms."""
    start = Atoms(
        "PtHH",
        positions=[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 0.0, 0.0]],
        cell=[10.0, 10.0, 10.0],
        pbc=True,
    )
    end = Atoms(
        "PtHH",
        positions=[[0.5, 0.0, 0.0], [1.5, 1.0, 2.0], [2.0, 0.0, 3.0]],
        cell=[10.0, 10.0, 10.0],
        pbc=True,
    )
    constraints = [
        FixAtoms(indices=[0]),
        FixCartesian(1, mask=[True, True, False]),
    ]
    start.set_constraint(constraints)
    end.set_constraint(constraints)
    return start, end


def test_robust_interpolate_retains_constraints_and_linear_geometry():
    """Interpolation retains constraint metadata without changing its geometry."""
    start, end = _constrained_idpp_endpoints()

    path = robust_interpolate(start, end, nimages=2)

    np.testing.assert_allclose(
        [image.positions[0, 0] for image in path], [0.0, 1.0 / 6.0, 1.0 / 3.0, 0.5]
    )
    np.testing.assert_allclose(
        [image.positions[1, 0] for image in path], [1.0, 7.0 / 6.0, 4.0 / 3.0, 1.5]
    )
    np.testing.assert_allclose(
        [image.positions[1, 2] for image in path], [1.0, 4.0 / 3.0, 5.0 / 3.0, 2.0]
    )
    assert path[1].positions[2, 2] != start.positions[2, 2]
    assert all(image.constraints for image in path[1:-1])


@pytest.mark.parametrize("optimizer", ["fire", "legacy"])
def test_fast_idpp_projects_constraint_positions_and_convergence_forces(optimizer):
    """IDPP updates and its convergence force use ASE's constraint hooks."""
    start, end = _constrained_idpp_endpoints()
    solver = Fast_IDPPSolver.from_endpoints(start, end, nimages=1)
    raw_forces = np.array([[[10.0, 20.0, 30.0], [4.0, 5.0, 6.0], [0.0, 0.0, 0.0]]])
    solver._get_funcs_and_forces = lambda coords: (np.zeros(1), raw_forces.copy())
    solver._get_total_forces = lambda coords, true_forces, spring_const: raw_forces.copy()

    initial = solver.initial_positions[0].copy()
    path = solver.run(maxiter=1, tol=0.0, gtol=0.0, step_size=0.05, max_disp=0.05, optimizer=optimizer)

    image = path[1]
    np.testing.assert_allclose(image.positions[0], initial[0], atol=0.0)
    np.testing.assert_allclose(image.positions[1, :2], initial[1, :2], atol=0.0)
    assert image.positions[2, 0] == initial[2, 0]
    assert image.positions[2, 1] == initial[2, 1]
    assert image.positions[2, 2] == initial[2, 2]
    assert solver.max_force == pytest.approx(6.0)


def test_generate_idpp_applies_fix_height_before_solver(tmp_path):
    """The generated path honors the optional height rule during IDPP."""
    start = Atoms(
        "HH",
        positions=[[0.0, 1.0, 0.0], [2.0, 8.0, 0.0]],
        cell=[10.0, 10.0, 10.0],
        pbc=True,
    )
    end = start.copy()
    end.positions[1, 0] = 3.0
    start_path = tmp_path / "start.traj"
    end_path = tmp_path / "end.traj"
    output_path = tmp_path / "path.traj"
    write(start_path, start)
    write(end_path, end)

    idpp.generate(
        method="IDPP",
        n_images=2,
        is_file=str(start_path),
        fs_file=str(end_path),
        output_file=str(output_path),
        format=None,
        fix_height=0.2,
        fix_dir=1,
        no_align=True,
    )
    path = read(output_path, index=":")

    for image in path[1:-1]:
        np.testing.assert_allclose(image.positions[0], start.positions[0], atol=0.0)
    assert any(not np.allclose(image.positions[1], start.positions[1]) for image in path[1:-1])


def test_generate_prepares_endpoint_conditions_before_relax_and_interpolation(tmp_path):
    start = Atoms("FeH", positions=[[0, 1, 0], [2, 8, 0]], cell=[10, 10, 10], pbc=True)
    end = start.copy()
    end.positions[1, 0] = 3
    start_path, end_path, output_path = (tmp_path / name for name in ("start.traj", "end.traj", "path.traj"))
    write(start_path, start)
    write(end_path, end)
    observed = []

    def prepare(initial, final):
        for endpoint in (initial, final):
            observed.append((endpoint.constraints[0].get_indices().tolist(), endpoint.get_initial_magnetic_moments().tolist()))
            endpoint.positions[1, 0] += 0.25
            endpoint.calc = SinglePointCalculator(endpoint, energy=1, forces=np.zeros((2, 3)))

    idpp.generate(
        method="IDPP", n_images=1, is_file=str(start_path), fs_file=str(end_path),
        output_file=str(output_path), format=None, fix_height=0.2, fix_dir=1,
        mag_ele=["Fe"], mag_num=[2.5], no_align=True, endpoint_prepare=prepare,
    )
    assert observed == [([0], [2.5, 0.0]), ([0], [2.5, 0.0])]
    path = read(output_path, index=":")
    assert path[0].positions[1, 0] == pytest.approx(2.25)
    assert path[-1].positions[1, 0] == pytest.approx(3.25)
    assert path[1].positions[1, 0] == pytest.approx(2.75)


def test_generate_magmom_does_not_discard_existing_endpoint_results(tmp_path):
    from atst_tools.utils.neb_endpoints import get_endpoint_results

    initial = Atoms("H", positions=[[0, 0, 0]], cell=[10, 10, 10], pbc=True)
    final = Atoms("H", positions=[[1, 0, 0]], cell=[10, 10, 10], pbc=True)
    for atoms in (initial, final):
        atoms.calc = SinglePointCalculator(atoms, energy=-1, forces=np.zeros((1, 3)))
    initial_path, final_path, output_path = (tmp_path / name for name in ("initial.traj", "final.traj", "path.traj"))
    write(initial_path, initial)
    write(final_path, final)
    observed = []

    def prepare(start, end):
        for atoms in (start, end):
            observed.append((atoms.get_initial_magnetic_moments().tolist(), get_endpoint_results(atoms)))

    idpp.generate(
        method="linear", n_images=1, is_file=str(initial_path), fs_file=str(final_path),
        output_file=str(output_path), format=None, no_align=True,
        mag_ele=["H"], mag_num=[1.0], endpoint_prepare=prepare,
    )
    assert len(observed) == 2
    for magmoms, results in observed:
        assert magmoms == [1.0]
        assert results is not None
        assert results[0] == pytest.approx(-1.0)


def test_generate_pt13_idpp_keeps_fixed_slab_and_moves_h_without_dft(tmp_path):
    """The bounded Pt12+H fixture keeps its slab fixed during path generation."""
    slab = read_structure(
        Path(__file__).resolve().parents[2] / "examples/19_constant_potential_Pt/inputs/STRU"
    )

    def endpoint(y):
        atoms = slab.copy()
        atoms += Atoms("H", positions=[[10.7302848, y, 2.4025463]])
        atoms.set_constraint(FixAtoms(indices=list(range(12))))
        return atoms

    start = endpoint(1.3871108)
    end = endpoint(4.1613325)
    start_path = tmp_path / "pt13-start.traj"
    end_path = tmp_path / "pt13-end.traj"
    output_path = tmp_path / "pt13-path.traj"
    write(start_path, start)
    write(end_path, end)

    idpp.generate(
        method="IDPP",
        n_images=2,
        is_file=str(start_path),
        fs_file=str(end_path),
        output_file=str(output_path),
        format=None,
        no_align=True,
    )
    path = read(output_path, index=":")

    for image in path[1:-1]:
        np.testing.assert_allclose(image.positions[:12], start.positions[:12], atol=1.0e-12)
    assert any(
        not np.allclose(image.positions[12], start.positions[12])
        for image in path[1:-1]
    )


def test_generate_preserves_mixed_constraints_through_alignment_and_traj(tmp_path):
    """Alignment and trajectory serialization retain partial mobility metadata."""
    start = Atoms(
        "PtH",
        positions=[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
        cell=[10.0, 10.0, 10.0],
        pbc=True,
    )
    start.set_constraint([
        FixAtoms(indices=[0]),
        FixCartesian(1, mask=[True, True, False]),
    ])
    end = Atoms(
        "HPt",
        positions=[[1.0, 1.0, 2.0], [0.0, 0.0, 0.0]],
        cell=start.cell,
        pbc=True,
    )
    end.set_constraint([
        FixCartesian(0, mask=[True, True, False]),
        FixAtoms(indices=[1]),
    ])
    start_path = tmp_path / "aligned-start.traj"
    end_path = tmp_path / "aligned-end.traj"
    output_path = tmp_path / "aligned-path.traj"
    write(start_path, start)
    write(end_path, end)

    idpp.generate(
        method="IDPP",
        n_images=1,
        is_file=str(start_path),
        fs_file=str(end_path),
        output_file=str(output_path),
        format=None,
        no_align=False,
    )
    path = read(output_path, index=":")

    assert [image.get_chemical_symbols() for image in path] == [["Pt", "H"]] * 3
    middle = path[1]
    np.testing.assert_allclose(middle.positions[0], start.positions[0], atol=0.0)
    np.testing.assert_allclose(middle.positions[1, :2], start.positions[1, :2], atol=0.0)
    assert middle.positions[1, 2] != start.positions[1, 2]
    assert any(isinstance(constraint, FixAtoms) for constraint in middle.constraints)
    assert any(isinstance(constraint, FixCartesian) for constraint in middle.constraints)


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


def test_fix_height_augments_existing_constraint_mobility():
    """The optional height rule must not replace partial Cartesian mobility."""
    atoms = Atoms(
        "HH",
        scaled_positions=[[0.0, 0.1, 0.0], [0.0, 0.8, 0.0]],
        cell=[5.0, 5.0, 5.0],
        pbc=True,
    )
    existing = FixCartesian(1, mask=[True, False, True])
    atoms.set_constraint(existing)

    set_fix_for_Atoms(atoms, fix_height=0.2, fix_dir=1)

    assert existing in atoms.constraints
    assert any(isinstance(constraint, FixAtoms) for constraint in atoms.constraints)


def test_generate_uses_non_parallel_project_structure_io(monkeypatch):
    start = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    end = Atoms("H", positions=[[1.0, 0.0, 0.0]])
    read_calls = []
    write_calls = []

    def fake_read_structure(filename, **kwargs):
        read_calls.append((filename, kwargs))
        return start.copy() if filename == "init.traj" else end.copy()

    def fake_write(filename, images, **kwargs):
        write_calls.append((filename, len(images), kwargs))

    monkeypatch.setattr(idpp, "read_structure", fake_read_structure)
    monkeypatch.setattr(idpp, "write", fake_write)
    monkeypatch.setattr(idpp, "_interpolate", lambda method, start_atoms, end_atoms, n_images, tol, **kwargs: [start_atoms, start_atoms.copy(), end_atoms])

    idpp.generate(
        method="IDPP",
        n_images=1,
        is_file="init.traj",
        fs_file="final.traj",
        output_file="chain.traj",
        format=None,
        no_align=True,
    )

    assert read_calls == [
        ("init.traj", {"format": None, "parallel": False}),
        ("final.traj", {"format": None, "parallel": False}),
    ]
    assert write_calls == [("chain.traj", 3, {"parallel": False})]


def test_generate_reads_ts_guess_with_project_structure_io(monkeypatch):
    start = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    ts = Atoms("H", positions=[[0.5, 0.0, 0.0]])
    end = Atoms("H", positions=[[1.0, 0.0, 0.0]])
    atoms_by_file = {"init.stru": start, "ts.stru": ts, "final.stru": end}
    read_calls = []

    def fake_read_structure(filename, **kwargs):
        read_calls.append((filename, kwargs))
        return atoms_by_file[filename].copy()

    monkeypatch.setattr(idpp, "read_structure", fake_read_structure)
    monkeypatch.setattr(idpp, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        idpp,
        "_interpolate",
        lambda method, start_atoms, end_atoms, n_images, tol, **kwargs: [start_atoms.copy(), end_atoms.copy()],
    )

    idpp.generate(
        method="linear",
        n_images=1,
        is_file="init.stru",
        fs_file="final.stru",
        ts_file="ts.stru",
        output_file="chain.traj",
        format=None,
        no_align=True,
    )

    assert read_calls == [
        ("init.stru", {"format": None, "parallel": False}),
        ("final.stru", {"format": None, "parallel": False}),
        ("ts.stru", {"format": None, "parallel": False}),
    ]


def test_generate_from_abacus_stru_matches_example_traj_endpoints(tmp_path):
    source_chain = Path("examples/02_neb_H2-Au/inputs/init_neb_chain.traj")
    frames = read(source_chain, index=":")
    start = frames[0]
    end = frames[-1]

    traj_start = tmp_path / "init.extxyz"
    traj_end = tmp_path / "final.extxyz"
    stru_start = tmp_path / "init.stru"
    stru_end = tmp_path / "final.stru"
    direct_output = tmp_path / "direct.traj"
    stru_output = tmp_path / "stru.traj"

    write(traj_start, start)
    write(traj_end, end)
    pp_files = {"H": "H.upf", "Au": "Au.upf"}
    orb_files = {"H": "H.orb", "Au": "Au.orb"}
    write_stru(start, str(tmp_path), pp_files, orb_files, fname=stru_start.name)
    write_stru(end, str(tmp_path), pp_files, orb_files, fname=stru_end.name)

    generate_kwargs = {
        "method": "linear",
        "n_images": 2,
        "format": None,
        "no_align": True,
        "tol": 0.05,
    }
    idpp.generate(
        is_file=str(traj_start),
        fs_file=str(traj_end),
        output_file=str(direct_output),
        **generate_kwargs,
    )
    idpp.generate(
        is_file=str(stru_start),
        fs_file=str(stru_end),
        output_file=str(stru_output),
        **generate_kwargs,
    )

    direct_images = read(direct_output, index=":")
    stru_images = read(stru_output, index=":")
    assert len(stru_images) == len(direct_images)
    for direct_atoms, stru_atoms in zip(direct_images, stru_images):
        assert stru_atoms.get_chemical_symbols() == direct_atoms.get_chemical_symbols()
        np.testing.assert_array_equal(stru_atoms.pbc, direct_atoms.pbc)
        np.testing.assert_allclose(stru_atoms.cell.array, direct_atoms.cell.array, atol=1e-10)
        np.testing.assert_allclose(stru_atoms.positions, direct_atoms.positions, atol=1e-8)


def test_generate_idpp_from_abacus_stru_matches_example_traj_endpoints(tmp_path):
    source_chain = Path("examples/02_neb_H2-Au/inputs/init_neb_chain.traj")
    frames = read(source_chain, index=":")
    start = frames[0]
    end = frames[-1]

    traj_start = tmp_path / "init.traj"
    traj_end = tmp_path / "final.traj"
    stru_start = tmp_path / "init.stru"
    stru_end = tmp_path / "final.stru"
    direct_output = tmp_path / "direct_idpp.traj"
    stru_output = tmp_path / "stru_idpp.traj"

    write(traj_start, start)
    write(traj_end, end)
    pp_files = {"H": "H.upf", "Au": "Au.upf"}
    orb_files = {"H": "H.orb", "Au": "Au.orb"}
    write_stru(start, str(tmp_path), pp_files, orb_files, fname=stru_start.name)
    write_stru(end, str(tmp_path), pp_files, orb_files, fname=stru_end.name)

    generate_kwargs = {
        "method": "IDPP",
        "n_images": 2,
        "format": None,
        "no_align": True,
        "tol": 0.05,
    }
    idpp.generate(
        is_file=str(traj_start),
        fs_file=str(traj_end),
        output_file=str(direct_output),
        **generate_kwargs,
    )
    idpp.generate(
        is_file=str(stru_start),
        fs_file=str(stru_end),
        output_file=str(stru_output),
        **generate_kwargs,
    )

    direct_images = read(direct_output, index=":")
    stru_images = read(stru_output, index=":")
    assert len(stru_images) == len(direct_images)
    for direct_atoms, stru_atoms in zip(direct_images, stru_images):
        assert stru_atoms.get_chemical_symbols() == direct_atoms.get_chemical_symbols()
        np.testing.assert_array_equal(stru_atoms.pbc, direct_atoms.pbc)
        np.testing.assert_allclose(stru_atoms.cell.array, direct_atoms.cell.array, atol=1e-12)
        np.testing.assert_allclose(stru_atoms.positions, direct_atoms.positions, atol=1e-12)


def _reference_build_translations(solver, images):
    """Return the legacy bounded scan for its valid-domain bitwise checks."""
    translations = np.zeros((solver.nimages, solver.natoms, solver.natoms, 3), dtype=float)
    if not solver.mic:
        return translations
    for image_index, image in enumerate(images[1:-1]):
        frac = image.get_scaled_positions(wrap=False)
        for i in range(solver.natoms):
            for j in range(i + 1, solver.natoms):
                shift = solver._nearest_image(frac[i], frac[j])
                cart_shift = np.dot(shift, solver.cell)
                translations[image_index, i, j] = cart_shift
                translations[image_index, j, i] = -cart_shift
    return translations


def _assert_nearest_translations_with_legacy_ties(solver, images, legacy):
    """Check ASE MIC distances, preserving legacy bits where the scan is valid."""
    i_index, j_index = np.triu_indices(solver.natoms, k=1)
    for image_index, image in enumerate(images[1:-1]):
        raw = image.positions[j_index] - image.positions[i_index]
        expected = image.get_all_distances(mic=solver.mic)[i_index, j_index]
        current = solver.translations[image_index, i_index, j_index]
        old = legacy[image_index, i_index, j_index]
        actual_dist = np.linalg.norm(raw + current, axis=1)
        old_dist = np.linalg.norm(raw + old, axis=1)
        np.testing.assert_allclose(actual_dist, expected, atol=1e-7)
        np.testing.assert_array_equal(
            solver.translations[image_index, j_index, i_index], -current
        )
        # The finite scan is a bitwise reference only when it found a genuine
        # shortest image. Elsewhere its old answer was a geometry error.
        valid = old_dist**2 <= expected**2 + solver._mic_tie_tolerance()
        np.testing.assert_array_equal(current[valid], old[valid])


def _random_idpp_cells(count, seed):
    """Yield ``(cell, frac, mic)`` triples covering triclinic, skewed, orthorhombic and tie cases."""
    rng = np.random.default_rng(seed)
    for index in range(count):
        natoms = int(rng.integers(2, 10))
        kind = index % 4
        if kind == 0:  # fully triclinic
            cell = np.array(
                [
                    [rng.uniform(3.0, 14.0), 0.0, 0.0],
                    [rng.uniform(-4.0, 4.0), rng.uniform(3.0, 14.0), 0.0],
                    [rng.uniform(-4.0, 4.0), rng.uniform(-4.0, 4.0), rng.uniform(3.0, 14.0)],
                ]
            )
        elif kind == 1:  # skewed monoclinic
            cell = np.array(
                [
                    [rng.uniform(3.0, 12.0), 0.0, 0.0],
                    [rng.uniform(-6.0, 0.0), rng.uniform(3.0, 12.0), 0.0],
                    [0.0, 0.0, rng.uniform(3.0, 12.0)],
                ]
            )
        else:  # orthorhombic; kind 3 sits on half-cell boundaries (exact periodic ties)
            cell = np.diag(rng.uniform(4.0, 12.0, size=3))
        if kind == 3:
            # Quarter-cell grid up to the half-cell boundary: every pair sits at a
            # periodic tie position yet keeps a non-zero MIC distance.
            grid = np.array(
                np.meshgrid([0.0, 0.25, 0.5], [0.0, 0.25, 0.5], [0.0, 0.25, 0.5], indexing="ij")
            ).reshape(3, -1).T
            frac = grid[rng.choice(len(grid), size=natoms, replace=False)]
        else:
            frac = rng.uniform(-0.5, 1.5, size=(natoms, 3))
        yield cell, frac, index % 6 != 5


def test_vectorized_build_translations_matches_reference_scan_bitwise():
    cases = 0
    for cell, frac, mic in _random_idpp_cells(220, seed=20260920):
        natoms = len(frac)
        images = [
            Atoms("H" * natoms, scaled_positions=frac.copy(), cell=cell, pbc=True),
            Atoms("H" * natoms, scaled_positions=frac + 0.05, cell=cell, pbc=True),
            Atoms("H" * natoms, scaled_positions=frac - 0.05, cell=cell, pbc=True),
        ]
        solver = Fast_IDPPSolver(images, mic=mic)
        reference = _reference_build_translations(solver, images)

        _assert_nearest_translations_with_legacy_ties(solver, images, reference)
        cases += 1

    assert cases >= 200


def test_vectorized_translations_match_reference_for_half_cell_ties():
    cell = [10.0, 10.0, 10.0]
    frac = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.5 - 1e-10, 0.25, 0.0], [0.5 + 1e-10, 0.75, 0.5]])
    images = [
        Atoms("H4", scaled_positions=frac.copy(), cell=cell, pbc=True),
        Atoms("H4", scaled_positions=frac.copy(), cell=cell, pbc=True),
        Atoms("H4", scaled_positions=frac.copy(), cell=cell, pbc=True),
    ]
    solver = Fast_IDPPSolver(images)

    reference = _reference_build_translations(solver, images)

    assert np.array_equal(solver.translations, reference)
    pair_shift = solver._nearest_image(frac[0], frac[1])
    np.testing.assert_allclose(solver.translations[0, 0, 1], np.dot(pair_shift, solver.cell))


def test_vectorized_translations_cover_multiple_pair_blocks():
    rng = np.random.default_rng(4242)
    natoms = 65  # 2080 pairs: more than one pair block
    cell = np.array(
        [
            [11.3, 0.0, 0.0],
            [-1.7, 12.1, 0.0],
            [0.9, -2.4, 10.7],
        ]
    )
    frac = rng.uniform(-0.5, 1.5, size=(natoms, 3))
    images = [
        Atoms("H" * natoms, scaled_positions=frac, cell=cell, pbc=True),
        Atoms("H" * natoms, scaled_positions=frac + 0.03, cell=cell, pbc=True),
        Atoms("H" * natoms, scaled_positions=frac - 0.03, cell=cell, pbc=True),
    ]
    solver = Fast_IDPPSolver(images)

    reference = _reference_build_translations(solver, images)

    _assert_nearest_translations_with_legacy_ties(solver, images, reference)
    assert np.count_nonzero(solver.translations) > 0


def test_mic_shift_rank_positions_form_a_strict_total_order():
    from atst_tools.utils import idpp as idpp_module

    candidates = idpp_module._MIC_SHIFT_CANDIDATES
    ranks = [
        (
            float(np.dot(shift, shift)),
            tuple(abs(int(value)) for value in shift),
            tuple(int(value) for value in shift),
        )
        for shift in candidates
    ]

    assert candidates[0].tolist() == [-1.0, -1.0, -1.0]
    assert candidates[-1].tolist() == [1.0, 1.0, 1.0]
    assert len(set(ranks)) == len(candidates)
    assert sorted(idpp_module._MIC_SHIFT_RANK_POSITIONS.tolist()) == list(range(len(candidates)))


@pytest.mark.parametrize("pbc,mic", [(True, True), ([True, False, True], True), (True, False)])
def test_idpp_current_pair_geometry_and_gradient_after_periodic_crossing(pbc, mic):
    """An initially selected lattice image cannot hide a later short contact."""
    cell = [[8.3575, 0, 0], [-4.17875, 7.2378, 0], [0, 0, 20]]
    atoms = Atoms("Pd2", positions=[[0, 0, 0], [5.5875, .1, 0]], cell=cell, pbc=pbc)
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)], mic=mic)
    coords = np.array([image.positions for image in solver.images])
    coords[1, 1] = [.205, .02, 0]
    objective, forces = solver._get_funcs_and_forces(coords)
    probe = atoms.copy()
    probe.positions = coords[1]
    distance = probe.get_distance(0, 1, mic=mic)
    expected = (distance - solver.target_dists[0, 0, 1]) ** 2 * solver.weights[0, 0, 1]
    assert objective[0] == pytest.approx(expected)
    assert forces[0, 1, 0] > 0
    np.testing.assert_allclose(forces.sum(axis=1), 0, atol=1e-14)
    epsilon = 1e-6
    plus, minus = coords.copy(), coords.copy()
    plus[1, 1, 0] += epsilon
    minus[1, 1, 0] -= epsilon
    derivative = (solver._get_funcs_and_forces(plus)[0][0] - solver._get_funcs_and_forces(minus)[0][0]) / (2 * epsilon)
    assert forces[0, 1, 0] == pytest.approx(-derivative, rel=1e-7)


@pytest.mark.parametrize("mic,expected", [(True, 5.0), (False, 0.0)])
def test_idpp_spring_uses_periodic_neighbor_displacements(mic, expected):
    """A wrapped endpoint keeps the physical spring length difference."""
    images = [Atoms("H", positions=[[x, 0, 0]], cell=[10, 10, 10], pbc=True) for x in (9, 10, 2)]
    solver = Fast_IDPPSolver(images, mic=mic)
    coords = np.array([image.positions for image in images])
    forces = solver._get_total_forces(coords, np.zeros((1, 1, 3)), spring_const=5)
    np.testing.assert_allclose(forces, [[[expected, 0, 0]]])


@pytest.mark.parametrize("optimizer", ["fire", "legacy"])
def test_idpp_final_report_describes_returned_coordinates(optimizer):
    atoms = Atoms("H2", positions=[[0, 0, 0], [2, 0, 0]])
    middle = atoms.copy()
    middle.positions[1, 1] = .5
    solver = Fast_IDPPSolver([atoms, middle, atoms.copy()])
    with pytest.warns(UserWarning, match="maximum iteration"):
        path = solver.run(maxiter=1, tol=0, gtol=0, optimizer=optimizer)
    coords = np.array([image.positions for image in path])
    funcs, forces = solver._get_funcs_and_forces(coords)
    total = solver._get_total_forces(coords, forces, spring_const=5)
    assert solver.final_s_idpp == pytest.approx(funcs.sum(), rel=1e-12)
    assert solver.max_force == pytest.approx(np.abs(total).max(), rel=1e-12)


@pytest.mark.parametrize("position", [[0, 0, 0], [float("nan"), 0, 0]])
def test_idpp_rejects_undefined_current_pair_geometry(position):
    atoms = Atoms("H2", positions=[[0, 0, 0], [2, 0, 0]])
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
    coords = np.array([image.positions for image in solver.images])
    coords[1, 1] = position
    with pytest.raises(ValueError, match="IDPP.*(overlap|finite)"):
        solver._get_funcs_and_forces(coords)


@pytest.mark.parametrize("symbols,distance,accepted", [("Pd2", .205, False), ("H2", .74, True)])
def test_generate_checks_contact_before_publishing_path(tmp_path, monkeypatch, symbols, distance, accepted):
    """A collapsed interpolation cannot overwrite an existing input band."""
    endpoint = Atoms(symbols, positions=[[0, 0, 0], [2.77 if symbols == "Pd2" else .74, 0, 0]])
    middle = endpoint.copy()
    middle.positions[1, 0] = distance
    monkeypatch.setattr(idpp, "read_structure", lambda *args, **kwargs: endpoint.copy())
    monkeypatch.setattr(idpp, "_interpolate", lambda *args, **kwargs: [endpoint.copy(), middle, endpoint.copy()])
    output = tmp_path / "path.traj"
    output.write_bytes(b"previous band")
    if accepted:
        idpp.generate("IDPP", 1, "start", "end", str(output), None, no_align=True)
        assert len(read(output, ":")) == 3
    else:
        with pytest.raises(ValueError, match="Generated NEB path"):
            idpp.generate("IDPP", 1, "start", "end", str(output), None, no_align=True)
        assert output.read_bytes() == b"previous band"


def test_idpp_neighbor_displacements_keep_nonperiodic_directions_cartesian():
    images = [Atoms("H", positions=[[0, y, 0]], cell=[10, 10, 10], pbc=[True, False, True]) for y in (9, 10, 2)]
    solver = Fast_IDPPSolver(images)
    coords = np.array([image.positions for image in images])
    np.testing.assert_allclose(solver._get_total_forces(coords, np.zeros((1, 1, 3)), spring_const=5), 0)


def test_idpp_pd_flat_fs_keeps_wrapped_slab_pairs_separated():
    """The real TS-to-flat-FS reproducer must converge without Pd collapse."""
    fixture = Path(__file__).resolve().parents[1] / "data" / "idpp_pd_flat_fs"
    start = read(fixture / "ts_guess.extxyz")
    end = read(fixture / "final.extxyz")
    solver = Fast_IDPPSolver.from_endpoints(start, end, nimages=4)

    path = solver.run(maxiter=2000, tol=0.05)

    assert solver.converged is True
    assert solver.iterations < 500
    assert solver.max_force < solver.gtol
    pd_indices = np.flatnonzero(start.numbers == 46)
    for image in path:
        distances = image.get_all_distances(mic=True)[np.ix_(pd_indices, pd_indices)]
        np.fill_diagonal(distances, np.inf)
        assert distances.min() > 2.0
    np.testing.assert_array_equal(path[0].positions, start.positions)
    np.testing.assert_array_equal(path[-1].positions, end.positions)
    frozen = start.constraints[0].get_indices()
    for image in path[1:-1]:
        np.testing.assert_allclose(image.positions[frozen], start.positions[frozen], atol=1e-12)


@pytest.mark.parametrize("optimizer", ["fire", "legacy"])
@pytest.mark.parametrize("pbc,mic", [(False, True), ([True, True, False], True), (True, False)])
def test_idpp_optimizers_restore_rotating_molecule_geometry(optimizer, pbc, mic):
    """Both update schemes restore bonds without violating the fixed oxygen."""
    start = Atoms("OH2", positions=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                  cell=[[10, 0, 0], [-3, 8, 0], [0, 0, 20]], pbc=pbc)
    end = start.copy()
    end.positions[1:] = [[0, 1, 0], [-1, 0, 0]]
    for atoms in (start, end):
        atoms.set_constraint(FixAtoms(indices=[0]))
    solver = Fast_IDPPSolver(robust_interpolate(start, end, 3), mic=mic)
    path = solver.run(maxiter=1000, optimizer=optimizer)
    assert solver.converged
    for image in path[1:-1]:
        np.testing.assert_allclose(image.positions[0], [0, 0, 0], atol=1e-14)
        np.testing.assert_allclose(image.get_all_distances(mic=mic), start.get_all_distances(mic=mic), atol=.02)


@pytest.mark.parametrize("optimizer", ["fire", "legacy"])
def test_idpp_empty_interior_returns_endpoints_without_optimization(optimizer):
    start = Atoms("H", positions=[[0, 0, 0]])
    end = Atoms("H", positions=[[1, 0, 0]])
    solver = Fast_IDPPSolver.from_endpoints(start, end, nimages=0)
    path = solver.run(optimizer=optimizer)
    assert solver.converged
    assert solver.iterations == 0
    assert solver.max_force == 0
    assert solver.final_s_idpp == 0
    assert len(path) == 2
    np.testing.assert_array_equal(path[0].positions, start.positions)
    np.testing.assert_array_equal(path[1].positions, end.positions)


def test_idpp_rejects_unknown_optimizer():
    atoms = Atoms("H", positions=[[0, 0, 0]])
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
    with pytest.raises(ValueError, match="optimizer"):
        solver.run(optimizer="unknown")


def test_idpp_legacy_optimizer_retains_step_multiplier_and_coordinate_cap():
    """The explicit legacy mode keeps its historical coordinate-wise update."""
    atoms = Atoms("H", positions=[[0, 0, 0]])
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(3)])
    forces = np.array([[[2., -4., .5]]])
    solver._get_funcs_and_forces = lambda coords: (np.ones(1), forces.copy())
    solver._get_total_forces = lambda coords, true_forces, spring_const: forces.copy()
    with pytest.warns(UserWarning, match="maximum iteration"):
        path = solver.run(maxiter=1, tol=0, gtol=0, step_size=.1,
                          max_disp=.15, optimizer="legacy")
    np.testing.assert_allclose(path[1].positions, [[.15, -.15, .05]])


@pytest.mark.parametrize('endpoint', [0, -1])
@pytest.mark.parametrize('nimages', [0, 1])
def test_run_rechecks_endpoints_modified_after_construction(endpoint, nimages):
    atoms = Atoms('H2', positions=[[0, 0, 0], [0.74, 0, 0]])
    solver = Fast_IDPPSolver([atoms.copy() for _ in range(nimages + 2)])
    solver.images[endpoint].positions[1] = solver.images[endpoint].positions[0]
    with pytest.raises(ValueError, match='overlapping atoms'):
        solver.run(maxiter=1)
