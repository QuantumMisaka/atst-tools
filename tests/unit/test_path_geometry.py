"""MIC contact facts and conservative path publication checks."""

import numpy as np
import pytest
from ase import Atoms

from atst_tools.utils.path_geometry import path_contact_facts, validate_path_geometry


def test_contact_facts_identify_collapsed_mic_pair_in_skew_cell():
    cell = [[8.3575, 0, 0], [4.17875, 7.2378, 0], [0, 0, 20]]
    endpoint = Atoms("Pd2", positions=[[0, 0, 0], [2.77, 0, 0]], cell=cell, pbc=True)
    collapsed = endpoint.copy()
    collapsed.positions[1] = [8.3575 - 0.205, 0, 0]
    facts = path_contact_facts([endpoint, collapsed, endpoint.copy()])
    assert facts["min_distance_A"] == pytest.approx(0.205)
    assert facts["min_distance_pair"] == (0, 1)
    assert facts["min_distance_image"] == 1
    assert facts["min_distance_ratio"] == pytest.approx(0.205 / 2.77)
    assert facts["ratio_image"] == 1
    with pytest.raises(ValueError, match=r"image 2.*Pd1-Pd2.*0.205"):
        validate_path_geometry([endpoint, collapsed, endpoint.copy()], context="D2S rough DyNEB")


def test_short_hydrogen_bond_and_endpoint_ratio_alone_are_accepted():
    endpoint = Atoms("H2", positions=[[0, 0, 0], [2.0, 0, 0]])
    bonded = Atoms("H2", positions=[[0, 0, 0], [0.74, 0, 0]])
    facts = validate_path_geometry([endpoint, bonded, endpoint.copy()])
    assert facts["min_distance_ratio"] < 0.5
    assert facts["min_distance_A"] == pytest.approx(0.74)


def test_contact_validation_respects_nonperiodic_direction():
    atoms = Atoms("Pd2", positions=[[0, 0, 0], [0, 0, 7.9]], cell=[8, 8, 8], pbc=[1, 1, 0])
    assert validate_path_geometry([atoms, atoms.copy()])["min_distance_A"] == pytest.approx(7.9)


@pytest.mark.parametrize("invalid", [np.nan, np.inf])
def test_nonfinite_single_atom_path_rejected_before_distance_evaluation(invalid):
    atoms = Atoms("H", positions=[[invalid, 0, 0]])
    with pytest.raises(ValueError, match="non-finite positions.*image 1"):
        validate_path_geometry([atoms, atoms.copy()])


def test_coincident_atoms_and_nonfinite_cell_are_rejected():
    atoms = Atoms("H2", positions=np.zeros((2, 3)))
    with pytest.raises(ValueError, match=r"H1-H2.*0.000"):
        validate_path_geometry([atoms])
    atoms = Atoms("H", cell=[np.inf, 8, 8])
    with pytest.raises(ValueError, match="non-finite cell.*image 1"):
        validate_path_geometry([atoms, atoms.copy()])


def test_empty_or_single_atom_contact_facts_have_no_pairs():
    assert path_contact_facts([]) == {}
    assert validate_path_geometry([Atoms("H"), Atoms("H")]) == {}


def test_single_frame_contact_summary_keeps_empty_path_semantics():
    atoms = Atoms('H2', positions=[[0, 0, 0], [0.74, 0, 0]])
    assert path_contact_facts([atoms]) == {}
    atoms.positions[1] = atoms.positions[0]
    assert path_contact_facts([atoms]) == {}
    with pytest.raises(ValueError, match='severe atomic overlap'):
        validate_path_geometry([atoms])
