"""Contracts for the maintained stable-Python-API documentation path."""

from __future__ import annotations

import ast
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
API_REFERENCE = ROOT / "docs/user/PYTHON_API_REFERENCE.md"
API_EXAMPLE = ROOT / "examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py"
RELEASE_NOTES = ROOT / "docs/releases/RELEASE_NOTES_2.2.0.md"


def test_api_reference_is_linked_from_public_navigation():
    assert "docs/user/PYTHON_API_REFERENCE.md" in (ROOT / "README.md").read_text(
        encoding="utf-8"
    )
    assert "user/PYTHON_API_REFERENCE.md" in (ROOT / "docs/index.md").read_text(
        encoding="utf-8"
    )


def test_public_api_reference_uses_only_the_stable_import_namespace():
    text = API_REFERENCE.read_text(encoding="utf-8")

    assert "from atst_tools.api import" in text
    for forbidden in (
        "from atst import",
        "from atst_tools.workflows",
        "from atst_tools.mep",
        "from atst_tools.calculators",
    ):
        assert forbidden not in text


def test_api_reference_states_execution_and_backend_boundaries():
    text = API_REFERENCE.read_text(encoding="utf-8")

    for phrase in (
        "current working directory",
        "root rank",
        "external-abacuslite-first",
        "provided ASE calculator",
        "experimental",
        "Deprecation",
    ):
        assert phrase in text


def test_ccqn_docs_state_production_abacus_calculator_boundary():
    """Production ABACUS CCQN setup remains an explicit caller responsibility."""
    reference = API_REFERENCE.read_text(encoding="utf-8")
    example = API_EXAMPLE.read_text(encoding="utf-8")
    examples_readme = (ROOT / "examples/README.md").read_text(encoding="utf-8")

    for text in (reference, example, examples_readme):
        assert "caller-created" in text
        assert "correctly configured" in text
        assert "pseudopotential" in text
        assert "orbital" in text
        assert "executable/runtime" in text
        assert "ATST does not configure" in text


def test_ccqn_api_example_has_required_header_and_automatic_mode_options():
    text = API_EXAMPLE.read_text(encoding="utf-8")

    for phrase in (
        "CCQN",
        "ATST",
        "pip install atst-tools",
        "https://github.com/QuantumMisaka/atst-tools",
        "CLI",
        "from atst_tools.api import",
        "auto_reactive_bonds",
    ):
        assert phrase in text
    assert "abacuslite" in text.lower()


def test_ccqn_api_example_executes_through_public_api_import_only(monkeypatch):
    from ase.io import read
    import atst_tools.api as api

    calls = []

    def fake_run_ccqn(atoms, calculator, options):
        calls.append((atoms, calculator, options))
        return SimpleNamespace(status="complete", metadata={"backend_source": "provided"})

    monkeypatch.setattr(api, "run_ccqn", fake_run_ccqn)
    monkeypatch.chdir(API_EXAMPLE.parent)
    runpy.run_path(str(API_EXAMPLE), run_name="__main__")

    tree = ast.parse(API_EXAMPLE.read_text(encoding="utf-8"))
    atst_imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("atst")
    ]
    assert atst_imports == ["atst_tools.api"]
    assert len(calls) == 1
    expected = read(API_EXAMPLE.parent / "inputs" / "ccqn_init.extxyz")
    assert calls[0][0].get_chemical_formula() == expected.get_chemical_formula()
    assert calls[0][0].get_positions().tolist() == expected.get_positions().tolist()
    assert calls[0][2].auto_reactive_bonds["enabled"] is True


def test_ccqn_extxyz_matches_authoritative_stru_conversion():
    """The documented CCQN input preserves the STRU structure semantics."""
    import numpy as np
    from ase.constraints import FixAtoms
    from ase.io import read
    from atst_tools.utils.io import read_structure

    inputs = API_EXAMPLE.parent / "inputs"
    expected = read_structure(inputs / "ccqn_init.stru")
    actual = read(inputs / "ccqn_init.extxyz")

    assert actual.get_chemical_symbols() == expected.get_chemical_symbols()
    np.testing.assert_allclose(actual.cell.array, expected.cell.array, rtol=0, atol=1e-8)
    np.testing.assert_allclose(actual.positions, expected.positions, rtol=0, atol=1e-7)
    np.testing.assert_allclose(
        actual.get_initial_magnetic_moments(), expected.get_initial_magnetic_moments(), rtol=0, atol=1e-12
    )

    expected_fixed = set(expected.constraints[0].get_indices())
    actual_fixed = {
        index
        for constraint in actual.constraints
        if isinstance(constraint, FixAtoms)
        for index in constraint.get_indices()
    }
    assert expected_fixed == actual_fixed
    assert expected_fixed == set(range(2, 34))


def test_runner_reference_documents_installed_protocol_and_matches_help():
    """The public reference exposes the installed runner rather than internals."""
    completed = subprocess.run(
        [sys.executable, "-m", "atst_tools.api.runner", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    for flag in (
        "--config",
        "--workdir",
        "--result-json",
        "--dry-run",
        "--restart",
        "--check-input",
        "--check-input-timeout",
        "--abacus-executable",
    ):
        assert flag in completed.stdout

    reference = API_REFERENCE.read_text(encoding="utf-8")
    for phrase in (
        "python -m atst_tools.api.runner",
        "atst-api-result-v1",
        "root rank",
        "0",
        "2",
        "1",
        "atomic",
        "Slurm",
        "mpirun",
    ):
        assert phrase in reference


def test_release_notes_describe_the_final_branch_tag_and_mpi_gate():
    """Release documentation must match the finalized branch, tag, and runner gate."""
    notes = RELEASE_NOTES.read_text(encoding="utf-8")

    assert "**Branch**: `main`" in notes
    assert "**Tag**: `v2.2.0`" in notes
    assert "two-rank API runner dry-run" in notes
    assert "two-rank CLI dry-run" not in notes
