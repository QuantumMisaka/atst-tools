import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import write

from atst_tools.utils.restart_helpers import (
    check_cache_files,
    clean_cache_files,
    get_last_frame,
    get_last_neb_band,
)


def _atoms(energy=0.0):
    atoms = Atoms("H", positions=[[energy, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


def test_get_last_frame_reads_final_trajectory_frame(tmp_path):
    traj = tmp_path / "relax.traj"
    write(traj, [_atoms(0.0), _atoms(1.0)])

    atoms = get_last_frame(traj)

    assert atoms.get_potential_energy() == 1.0


def test_get_last_neb_band_requires_complete_band(tmp_path):
    traj = tmp_path / "neb.traj"
    write(traj, [_atoms(0.0), _atoms(1.0), _atoms(2.0), _atoms(3.0), _atoms(4.0)])

    with pytest.raises(ValueError, match="whole number of bands"):
        get_last_neb_band(traj, 3)


def test_get_last_neb_band_returns_last_complete_band(tmp_path):
    traj = tmp_path / "neb.traj"
    write(traj, [_atoms(0.0), _atoms(1.0), _atoms(2.0), _atoms(3.0), _atoms(4.0), _atoms(5.0)])

    band = get_last_neb_band(traj, 3)

    assert [atoms.get_potential_energy() for atoms in band] == [3.0, 4.0, 5.0]


def test_cache_helpers_detect_and_clean_bad_json(tmp_path):
    vib = tmp_path / "vib"
    vib.mkdir()
    good = vib / "cache.eq.json"
    bad = vib / "cache.0x+.json"
    empty = vib / "cache.0x-.json"
    good.write_text(json.dumps({"forces": [0.0]}), encoding="utf-8")
    bad.write_text("{bad json", encoding="utf-8")
    empty.touch()

    status = check_cache_files(vib)
    assert status["valid"] == [good]
    assert status["invalid"] == [bad, empty]

    clean_cache_files(vib, keep_good=True)
    assert good.exists()
    assert not bad.exists()
    assert not empty.exists()


def test_cache_helpers_can_remove_whole_cache_directory(tmp_path):
    vib = tmp_path / "vib"
    vib.mkdir()
    (vib / "cache.eq.json").write_text("{}", encoding="utf-8")

    clean_cache_files(vib, keep_good=False)

    assert not vib.exists()
