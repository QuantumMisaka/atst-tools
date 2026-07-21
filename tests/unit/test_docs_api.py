"""Contracts for the maintained stable-Python-API documentation path."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
API_REFERENCE = ROOT / "docs/user/PYTHON_API_REFERENCE.md"
API_EXAMPLE = ROOT / "examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py"


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
    assert "abacuslite" not in text.lower()


def test_ccqn_api_example_executes_through_public_api_import_only(monkeypatch):
    from ase import Atoms
    import ase.io
    import atst_tools.api as api

    calls = []

    def fake_run_ccqn(atoms, calculator, options):
        calls.append((atoms, calculator, options))
        return SimpleNamespace(status="complete", metadata={"backend_source": "provided"})

    monkeypatch.setattr(api, "run_ccqn", fake_run_ccqn)
    monkeypatch.setattr(ase.io, "read", lambda path: Atoms("H2Au64"))
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
    assert calls[0][2].auto_reactive_bonds["enabled"] is True
