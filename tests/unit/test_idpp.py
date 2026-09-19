from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import read, write

import pytest

from atst_tools.external.ASE_interface.abacuslite.io.generalio import write_stru
from atst_tools.utils import idpp
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
    monkeypatch.setattr(idpp, "_interpolate", lambda method, start_atoms, end_atoms, n_images, tol: [start_atoms, start_atoms.copy(), end_atoms])

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
        lambda method, start_atoms, end_atoms, n_images, tol: [start_atoms.copy(), end_atoms.copy()],
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
    """Reference implementation kept in-test: per-pair scan, no vectorization."""
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
    worst_difference = 0.0
    for cell, frac, mic in _random_idpp_cells(220, seed=20260920):
        natoms = len(frac)
        images = [
            Atoms("H" * natoms, scaled_positions=frac.copy(), cell=cell, pbc=True),
            Atoms("H" * natoms, scaled_positions=frac + 0.05, cell=cell, pbc=True),
            Atoms("H" * natoms, scaled_positions=frac - 0.05, cell=cell, pbc=True),
        ]
        solver = Fast_IDPPSolver(images, mic=mic)
        reference = _reference_build_translations(solver, images)

        assert np.array_equal(solver.translations, reference), f"case {cases} (natoms={natoms}, mic={mic})"
        worst_difference = max(worst_difference, float(np.max(np.abs(solver.translations - reference))))
        cases += 1

    assert cases >= 200
    assert worst_difference == 0.0


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

    assert np.array_equal(solver.translations, reference)
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
