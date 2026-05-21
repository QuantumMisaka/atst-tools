"""Tests for the vendored abacuslite profile helpers."""

from types import SimpleNamespace

import pytest
from ase import Atoms

from atst_tools.external.ASE_interface.abacuslite.core import AbacusProfile, AbacusTemplate
from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru, write_stru


def test_parse_version_accepts_legacy_abacus_version_line():
    """ABACUS <= 3.9 style version output remains supported."""
    assert AbacusProfile.parse_version("ABACUS version v3.9.0.17\n") == "v3.9.0.17"


def test_parse_version_accepts_banner_abacus_version_line():
    """ABACUS LTS 3.10.1 prints the version in the startup banner."""
    stdout = """
                              ABACUS v3.10.1

               Atomic-orbital Based Ab-initio Computation at UStc
"""
    assert AbacusProfile.parse_version(stdout) == "v3.10.1"


def test_parse_version_reports_unrecognized_output():
    """Unexpected version output should fail with an actionable message."""
    with pytest.raises(RuntimeError, match="Could not parse ABACUS version"):
        AbacusProfile.parse_version("unrecognized output")


def test_version_falls_back_to_bare_executable_when_mpi_stdout_is_empty(monkeypatch):
    """MPI launchers may suppress ABACUS --version stdout inside Slurm."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        if command[:3] == ["mpirun", "-np", "4"]:
            return ""
        return "ABACUS version v3.10.1\n"

    from atst_tools.external.ASE_interface.abacuslite import core

    monkeypatch.setattr(core, "read_stdout", fake_read_stdout)

    profile = AbacusProfile("mpirun -np 4 abacus")

    assert profile.version() == "v3.10.1"
    assert calls == [
        ["mpirun", "-np", "4", "abacus", "--version"],
        ["abacus", "--version"],
    ]


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
