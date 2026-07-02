"""Tests for abacuslite profile helpers used by ATST-Tools."""

from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms, FixCartesian

from atst_tools.calculators import abacuslite_backend
from atst_tools.calculators.abacuslite_backend import ATSTAbacusProfile
from atst_tools.external.ASE_interface.abacuslite.core import AbacusProfile, AbacusTemplate
from atst_tools.external.ASE_interface.abacuslite.io.generalio import file_safe_backup, read_stru, write_stru


def test_parse_version_accepts_legacy_abacus_version_line():
    """ABACUS <= 3.9 style version output remains supported."""
    assert AbacusProfile.parse_version("ABACUS version v3.9.0.17\n") == "v3.9.0.17"


def test_atst_parse_version_accepts_banner_abacus_version_line():
    """ATST's profile adapter supports the ABACUS LTS startup banner."""
    stdout = """
                              ABACUS v3.10.1

               Atomic-orbital Based Ab-initio Computation at UStc
"""
    assert ATSTAbacusProfile.parse_version(stdout) == "v3.10.1"


def test_atst_parse_version_reports_unrecognized_output():
    """Unexpected version output should fail with an actionable message."""
    with pytest.raises(RuntimeError, match="Could not parse ABACUS version"):
        ATSTAbacusProfile.parse_version("unrecognized output")


def test_atst_version_uses_bare_executable_for_wrapped_run_command(monkeypatch):
    """Version probing should not run mpirun -np N abacus --version by default."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile("mpirun -np 4 abacus")

    assert profile.version() == "v3.10.1"
    assert calls == [["abacus", "--version"]]


def test_atst_version_uses_bare_executable_for_env_sanitized_command(monkeypatch):
    """Version probing should skip env -u prefixes used for MPI env cleanup."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile("env -u OMPI_COMM_WORLD_SIZE -u PMIX_RANK abacus")

    assert profile.version() == "v3.10.1"
    assert calls == [["abacus", "--version"]]


def test_atst_version_command_override_is_used_verbatim(monkeypatch):
    """Site-specific version probe commands can be configured explicitly."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS version v3.9.0.17\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile(
        "mpirun -np 4 abacus",
        version_command="srun --partition debug abacus --version",
    )

    assert profile.version() == "v3.9.0.17"
    assert calls == [["srun", "--partition", "debug", "abacus", "--version"]]


def test_vendored_abacusprofile_version_keeps_native_probe(monkeypatch):
    """The vendored abacuslite profile should not contain ATST's fallback policy."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS version v3.9.0.17\n"

    from atst_tools.external.ASE_interface.abacuslite import core

    monkeypatch.setattr(core, "read_stdout", fake_read_stdout)

    profile = AbacusProfile("mpirun -np 4 abacus")

    assert profile.version() == "v3.9.0.17"
    assert calls == [["mpirun", "-np", "4", "abacus", "--version"]]


def test_file_safe_backup_rotates_existing_integer_backups_without_clobber(tmp_path):
    """Existing numbered backups should move up one slot before live file backup."""
    live = tmp_path / "STRU"
    backup0 = tmp_path / "STRU.bak.0"
    backup1 = tmp_path / "STRU.bak.1"
    non_integer_backup = tmp_path / "STRU.bak.note"

    live.write_text("live\n", encoding="utf-8")
    backup0.write_text("old-zero\n", encoding="utf-8")
    backup1.write_text("old-one\n", encoding="utf-8")
    non_integer_backup.write_text("keep-me\n", encoding="utf-8")

    file_safe_backup(live)

    assert not live.exists()
    assert backup0.read_text(encoding="utf-8") == "live\n"
    assert backup1.read_text(encoding="utf-8") == "old-zero\n"
    assert (tmp_path / "STRU.bak.2").read_text(encoding="utf-8") == "old-one\n"
    assert non_integer_backup.read_text(encoding="utf-8") == "keep-me\n"


def test_file_safe_backup_preserves_noncanonical_numeric_suffixes(tmp_path):
    """Only canonical non-negative backup indexes should be rotated."""
    live = tmp_path / "STRU"
    backup0 = tmp_path / "STRU.bak.0"
    leading_zero_backup = tmp_path / "STRU.bak.01"
    signed_positive_backup = tmp_path / "STRU.bak.+1"
    signed_negative_backup = tmp_path / "STRU.bak.-1"

    live.write_text("live\n", encoding="utf-8")
    backup0.write_text("old-zero\n", encoding="utf-8")
    leading_zero_backup.write_text("leading-zero\n", encoding="utf-8")
    signed_positive_backup.write_text("signed-positive\n", encoding="utf-8")
    signed_negative_backup.write_text("signed-negative\n", encoding="utf-8")

    file_safe_backup(live)

    assert not live.exists()
    assert backup0.read_text(encoding="utf-8") == "live\n"
    assert (tmp_path / "STRU.bak.1").read_text(encoding="utf-8") == "old-zero\n"
    assert leading_zero_backup.read_text(encoding="utf-8") == "leading-zero\n"
    assert signed_positive_backup.read_text(encoding="utf-8") == "signed-positive\n"
    assert signed_negative_backup.read_text(encoding="utf-8") == "signed-negative\n"


def test_write_stru_preserves_first_occurrence_species_order(tmp_path):
    """STRU species blocks should follow ASE atom order, not alphabetical order."""
    atoms = Atoms(
        symbols=["C", "C", "Pt", "H", "H"],
        positions=[
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
        ],
        cell=[10.0, 10.0, 10.0],
    )

    write_stru(
        atoms,
        outdir=tmp_path,
        pp_file={"C": "C.upf", "Pt": "Pt.upf", "H": "H.upf"},
        orb_file={"C": "C.orb", "Pt": "Pt.orb", "H": "H.orb"},
    )

    data = read_stru(tmp_path / "STRU")
    assert [species["symbol"] for species in data["species"]] == ["C", "Pt", "H"]
    assert [species["orb_file"] for species in data["species"]] == ["C.orb", "Pt.orb", "H.orb"]


def test_write_stru_records_cartesian_coordinates_pp_basis_and_magmom(tmp_path):
    """STRU writer covers core ABACUS input metadata and magnetic moments."""
    atoms = Atoms(
        symbols=["H", "He", "H"],
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        cell=[5.0, 6.0, 7.0],
        pbc=True,
    )
    atoms.set_initial_magnetic_moments([1.0, 0.0, 2.0])

    write_stru(
        atoms,
        outdir=tmp_path,
        pp_file={"H": "H.upf", "He": "He.upf"},
        orb_file={"H": "H.orb", "He": "He.orb"},
    )

    data = read_stru(tmp_path / "STRU")

    assert data["coord_type"] == "Cartesian"
    assert [(species["symbol"], species["pp_file"], species["orb_file"]) for species in data["species"]] == [
        ("H", "H.upf", "H.orb"),
        ("He", "He.upf", "He.orb"),
    ]
    np.testing.assert_allclose(data["species"][0]["atom"][0]["coord"], [0.0, 0.0, 0.0])
    np.testing.assert_allclose(data["species"][0]["atom"][1]["coord"], [0.0, 1.0, 0.0])
    assert data["species"][0]["atom"][0]["mag"] == 1.0
    assert data["species"][0]["atom"][1]["mag"] == 2.0


def test_write_stru_preserves_constraints_as_mobility_and_zeroes_velocities(tmp_path):
    """ASE constraints should round-trip to ABACUS mobility flags."""
    atoms = Atoms(
        symbols=["H", "He", "H"],
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        cell=[5.0, 6.0, 7.0],
        pbc=True,
    )
    atoms.set_constraint([FixAtoms(indices=[0]), FixCartesian(1, [True, False, True])])
    atoms.set_velocities([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])

    write_stru(
        atoms,
        outdir=tmp_path,
        pp_file={"H": "H.upf", "He": "He.upf"},
        orb_file={"H": "H.orb", "He": "He.orb"},
    )

    data = read_stru(tmp_path / "STRU")
    atoms_in_stru = [atom for species in data["species"] for atom in species["atom"]]

    assert [atom["m"] for atom in atoms_in_stru] == [[0, 0, 0], [1, 1, 1], [0, 1, 0]]
    assert [atom["v"] for atom in atoms_in_stru] == [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]


def test_abacus_template_uses_first_occurrence_species_grouping(tmp_path):
    """Template atom reordering should match the STRU writer's species order."""
    atoms = Atoms(
        symbols=["C", "Pt", "H", "C", "H"],
        positions=[
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
        ],
        cell=[10.0, 10.0, 10.0],
    )
    profile = SimpleNamespace(pseudo_dir=str(tmp_path), orbital_dir=str(tmp_path))
    template = AbacusTemplate()

    template.write_input(
        profile,
        tmp_path,
        atoms,
        parameters={
            "calculation": "scf",
            "pseudopotentials": {"C": "C.upf", "Pt": "Pt.upf", "H": "H.upf"},
            "basissets": {"C": "C.orb", "Pt": "Pt.orb", "H": "H.orb"},
        },
        properties=["energy", "forces"],
    )

    data = read_stru(tmp_path / "STRU")
    assert [species["symbol"] for species in data["species"]] == ["C", "Pt", "H"]
    assert template.atomorder == [0, 2, 3, 1, 4]


class _ConflictingKeywordTemplate(AbacusTemplate):
    implemented_properties = [*AbacusTemplate.implemented_properties, "mock_a", "mock_b"]

    @staticmethod
    def get_mock_a_keywords(parameters):
        return {"cal_force": "1"}

    @staticmethod
    def get_mock_b_keywords(parameters):
        return {"cal_force": "0"}


def test_property_keywords_raise_when_properties_disagree_on_same_keyword():
    """Two requested properties should not silently overwrite the same keyword."""
    template = _ConflictingKeywordTemplate()

    with pytest.raises(ValueError, match="cal_force=0"):
        template.get_property_keywords({"calculation": "scf"}, ["mock_a", "mock_b"])


def test_property_keywords_raise_when_property_overwrites_user_keyword():
    """Property-derived keywords should not silently overwrite explicit user input."""
    template = AbacusTemplate()

    with pytest.raises(ValueError, match="nspin=2"):
        template.get_property_keywords({"calculation": "scf", "nspin": "1"}, ["magmom"])


def test_abacus_template_does_not_advertise_dipole_until_tddft_is_supported():
    """The ASE property list should not include a property the writer rejects."""
    assert "dipole" not in AbacusTemplate.implemented_properties


def test_abacus_template_rejects_dipole_property_keyword_request():
    """Direct keyword mapping should reject dipole after it is removed from support."""
    template = AbacusTemplate()

    with pytest.raises(AssertionError):
        template.get_property_keywords({"calculation": "scf"}, ["dipole"])


def test_property_keywords_accept_equivalent_user_keyword_values():
    """Equivalent int/string user keywords should not be false conflicts."""
    template = AbacusTemplate()

    parameters = template.get_property_keywords({"calculation": "scf", "nspin": 2}, ["magmom"])

    assert parameters["nspin"] == "2"
