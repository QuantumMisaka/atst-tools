import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms
from ase.io import read, write

from atst_tools.utils.analysis import get_displacement_analysis
from atst_tools.utils.io import read_structure
from atst_tools.utils.post import NEBPost


def _atoms(symbols="H", energy=0.0, positions=None, forces=None):
    if positions is None:
        positions = [[0.0, 0.0, 0.0]]
    atoms = Atoms(symbols, positions=positions)
    if forces is None:
        forces = np.zeros((len(atoms), 3))
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
    atoms.info["energy"] = energy
    atoms.arrays["forces"] = np.asarray(forces, dtype=float)
    return atoms


def test_displacement_analysis_selects_highest_energy_and_moving_atoms():
    chain = [
        _atoms("H2", 0.0, [[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        _atoms("H2", 1.0, [[0.5, 0.0, 0.0], [0.0, 0.0, 1.1]]),
        _atoms("H2", 0.1, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.2]]),
    ]

    ts_index, main_indices, norm_vector = get_displacement_analysis(chain, thr=0.5)

    assert ts_index == 1
    assert main_indices == [0]
    assert norm_vector[0] > norm_vector[1]


def test_displacement_analysis_handles_zero_displacement():
    atom = _atoms("H", 1.0, [[0.0, 0.0, 0.0]])

    ts_index, main_indices, norm_vector = get_displacement_analysis([atom], thr=0.1)

    assert ts_index == 0
    assert main_indices == []
    np.testing.assert_allclose(norm_vector, np.zeros(0))


def test_nebpost_recovers_info_energy_and_writes_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    images = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[1.0, 0.0, 0.0]]),
        Atoms("H", positions=[[2.0, 0.0, 0.0]]),
    ]
    for index, atoms in enumerate(images):
        atoms.info["energy"] = float(index)
        atoms.arrays["forces"] = np.zeros((1, 3))

    post = NEBPost(images, n_max=1)
    assert [atoms.get_potential_energy() for atoms in post.neb_chain] == [0.0, 1.0, 2.0]

    post.write_latest_bands("latest")
    assert len(read("latest.traj", index=":")) == 3
    assert len(read("latest.extxyz", index=":")) == 3


def test_nebpost_equal_endpoint_barrier_and_plot_all_use_known_band_size(monkeypatch):
    images = [
        _atoms("H", 0.0, [[0.0, 0.0, 0.0]]),
        _atoms("H", 1.0, [[1.0, 0.0, 0.0]]),
        _atoms("H", 0.0, [[2.0, 0.0, 0.0]]),
    ]
    post = NEBPost(images, n_max=0)

    barrier, delta_e = post.get_barrier()
    assert barrier == pytest.approx(1.0)
    assert delta_e == pytest.approx(0.0)

    def fake_plot_bands(self, **kwargs):
        assert kwargs["nimages"] == 3
        return "figure"

    monkeypatch.setattr("atst_tools.utils.post.NEBTools.plot_bands", fake_plot_bands)

    assert post.plot_all_bands() == "figure"


def test_nebpost_energy_profile_reports_absolute_and_relative_energies():
    images = [
        _atoms("H", 2.0, [[0.0, 0.0, 0.0]]),
        _atoms("H", 3.5, [[1.0, 0.0, 0.0]]),
        _atoms("H", 2.4, [[2.0, 0.0, 0.0]]),
    ]

    profile = NEBPost(images, n_max=0).energy_profile()

    assert [row["image"] for row in profile] == [0, 1, 2]
    assert [row["energy_eV"] for row in profile] == pytest.approx([2.0, 3.5, 2.4])
    assert [row["rel_energy_eV"] for row in profile] == pytest.approx([0.0, 1.5, 0.4])
    assert [row["max_force_eV_per_A"] for row in profile] == pytest.approx([0.0, 0.0, 0.0])


def test_nebpost_nmax_zero_does_not_guess_band_size_twice(monkeypatch):
    images = [
        _atoms("H", 0.0, [[0.0, 0.0, 0.0]]),
        _atoms("H", 1.0, [[1.0, 0.0, 0.0]]),
        _atoms("H", 0.0, [[2.0, 0.0, 0.0]]),
    ]

    calls = []

    class CountingNEBTools:
        def __init__(self, images):
            self.images = images

        def _guess_nimages(self):
            calls.append("_guess_nimages")
            return 3

    monkeypatch.setattr("atst_tools.utils.post.NEBTools", CountingNEBTools)

    post = NEBPost(images, n_max=0)

    assert calls == []
    assert post.n_images == 3
    assert post.neb_chain == images


def test_nebpost_rejects_invalid_nmax_values():
    images = [_atoms("H", 0.0), _atoms("H", 1.0)]

    with pytest.raises(ValueError, match="n_max"):
        NEBPost(images, n_max=-1)
    with pytest.raises(ValueError, match="n_max"):
        NEBPost(images, n_max=1.5)


def test_nebpost_missing_energy_and_forces_recover_to_zero_defaults():
    images = [
        Atoms("H", positions=[[0.0, 0.0, 0.0]]),
        Atoms("H", positions=[[1.0, 0.0, 0.0]]),
        Atoms("H", positions=[[2.0, 0.0, 0.0]]),
    ]

    profile = NEBPost(images, n_max=0).energy_profile()

    assert [row["energy_eV"] for row in profile] == pytest.approx([0.0, 0.0, 0.0])
    assert [row["max_force_eV_per_A"] for row in profile] == pytest.approx([0.0, 0.0, 0.0])


def test_nebpost_ts_structure_keeps_cif_when_stru_writer_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    images = [_atoms("H", 0.0), _atoms("H", 1.0), _atoms("H", 0.5)]
    writes = []

    def fake_write(filename, atoms, format=None):
        writes.append((filename, format))
        if format == "stru":
            raise ValueError("unsupported format")
        Path(filename).write_text("written\n", encoding="utf-8")

    monkeypatch.setattr("atst_tools.utils.post.write", fake_write)

    NEBPost(images, n_max=0).get_TS_stru("ts")

    assert writes == [("ts.cif", "cif"), ("ts.stru", "stru")]
    assert (tmp_path / "ts.cif").exists()
    assert not (tmp_path / "ts.stru").exists()


def test_nebpost_plot_and_view_fallbacks(monkeypatch):
    images = [_atoms("H", 0.0), _atoms("H", 1.0), _atoms("H", 0.5)]
    post = NEBPost(images, n_max=0)
    commands = []

    monkeypatch.setattr(
        "atst_tools.utils.post.NEBTools.plot_bands",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("plot failed")),
    )
    monkeypatch.setattr("os.system", lambda command: commands.append(command) or 0)

    assert post.plot_neb_bands() is None
    assert post.plot_all_bands() is None

    post.view_neb_bands("neb.traj")
    assert commands == ["ase gui neb.traj@-3:"]


def test_read_structure_dispatches_abacus_stru(tmp_path):
    (tmp_path / "STRU").write_text(
        """ATOMIC_SPECIES
H 1.0 H.upf

NUMERICAL_ORBITAL
H.orb

LATTICE_CONSTANT
1.889726

LATTICE_VECTORS
8.0 0.0 0.0
0.0 8.0 0.0
0.0 0.0 8.0

ATOMIC_POSITIONS
Direct

H
0.0
2
0.0 0.0 0.0 0 0 0 mag 1.0
0.5 0.0 0.0 1 1 1 mag 0.0
""",
        encoding="utf-8",
    )

    parsed = read_structure(tmp_path / "STRU")

    assert parsed.get_chemical_symbols() == ["H", "H"]
    assert parsed.pbc.all()
    assert parsed.constraints
    np.testing.assert_allclose(parsed.get_initial_magnetic_moments(), [1.0, 0.0])


def test_read_structure_supports_cartesian_stru_coordinates(tmp_path):
    (tmp_path / "cartesian.stru").write_text(
        """ATOMIC_SPECIES
H 1.0 H.upf
He 4.0 He.upf

NUMERICAL_ORBITAL
H.orb
He.orb

LATTICE_CONSTANT
1.8897261258369282

LATTICE_VECTORS
5.0 0.0 0.0
0.0 6.0 0.0
0.0 0.0 7.0

ATOMIC_POSITIONS
Cartesian

H
0.0
1
1.0 0.0 0.0

He
0.0
1
0.0 2.0 0.0
""",
        encoding="utf-8",
    )

    parsed = read_structure(tmp_path / "cartesian.stru")

    assert parsed.get_chemical_symbols() == ["H", "He"]
    np.testing.assert_allclose(parsed.get_scaled_positions(), [[0.2, 0.0, 0.0], [0.0, 1 / 3, 0.0]])


def test_read_structure_supports_vector_magnetic_moments(tmp_path):
    (tmp_path / "vector_mag.stru").write_text(
        """ATOMIC_SPECIES
H 1.0 H.upf
He 4.0 He.upf

LATTICE_CONSTANT
1.8897261258369282

LATTICE_VECTORS
5.0 0.0 0.0
0.0 6.0 0.0
0.0 0.0 7.0

ATOMIC_POSITIONS
Direct

H
0.0
1
0.0 0.0 0.0 mag 1.0 0.0 0.0

He
0.0
1
0.5 0.0 0.0 mag 0.0 2.0 0.0
""",
        encoding="utf-8",
    )

    parsed = read_structure(tmp_path / "vector_mag.stru")

    np.testing.assert_allclose(parsed.get_initial_magnetic_moments(), [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])


def test_read_structure_only_preserves_full_fixatoms_and_drops_velocities(tmp_path):
    (tmp_path / "mobility_velocity.stru").write_text(
        """ATOMIC_SPECIES
H 1.0 H.upf
He 4.0 He.upf

LATTICE_CONSTANT
1.8897261258369282

LATTICE_VECTORS
5.0 0.0 0.0
0.0 6.0 0.0
0.0 0.0 7.0

ATOMIC_POSITIONS
Direct

H
0.0
1
0.0 0.0 0.0 m 0 0 0 v 0.1 0.2 0.3

He
0.0
1
0.5 0.0 0.0 m 1 0 1 v 0.4 0.5 0.6
""",
        encoding="utf-8",
    )

    parsed = read_structure(tmp_path / "mobility_velocity.stru")

    assert len(parsed.constraints) == 1
    assert isinstance(parsed.constraints[0], FixAtoms)
    np.testing.assert_array_equal(parsed.constraints[0].index, [0])
    np.testing.assert_allclose(parsed.get_velocities(), np.zeros((2, 3)))


def test_read_structure_uses_ase_for_non_stru(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    structure = tmp_path / "h.xyz"
    write(structure, atoms)

    assert read_structure(structure).get_chemical_symbols() == ["H"]


def test_collect_abacus_output_records_parsed_frame(tmp_path, monkeypatch):
    from atst_tools.utils import abacus_io

    run_dir = tmp_path / "run"
    out_dir = run_dir / "OUT.ABACUS"
    out_dir.mkdir(parents=True)
    (run_dir / "INPUT").write_text("INPUT_PARAMETERS\n", encoding="utf-8")
    (run_dir / "KPT").write_text("K_POINTS\n", encoding="utf-8")
    (run_dir / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")
    (out_dir / "running_scf.log").write_text("mock\n", encoding="utf-8")
    atoms = _atoms("H", energy=-1.25, forces=[[0.1, 0.2, 0.0]])

    monkeypatch.setattr(abacus_io, "_parse_last_abacus_frame", lambda log: atoms)
    summary = abacus_io.collect_abacus_output(str(run_dir), str(tmp_path / "summary.json"), structure=str(tmp_path / "last.xyz"))

    assert summary["parsed"] is True
    assert summary["energy_eV"] == pytest.approx(-1.25)
    assert summary["max_force_eV_per_ang"] == pytest.approx(np.linalg.norm([0.1, 0.2, 0.0]))
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["frames"] == 1
    assert (tmp_path / "last.xyz").is_file()


def test_collect_abacus_output_requires_existing_run_dir(tmp_path):
    from atst_tools.utils.abacus_io import collect_abacus_output

    with pytest.raises(FileNotFoundError):
        collect_abacus_output(str(tmp_path / "missing"), str(tmp_path / "summary.json"))
