"""Tests for abacuslite profile helpers used by ATST-Tools."""

from types import SimpleNamespace

import pytest
from ase import Atoms

from atst_tools.calculators import abacuslite_backend
from atst_tools.calculators.abacuslite_backend import ATSTAbacusProfile
from atst_tools.external.ASE_interface.abacuslite.core import AbacusProfile, AbacusTemplate
from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru, write_stru


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
