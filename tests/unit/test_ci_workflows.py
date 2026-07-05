"""Governance tests for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERAL_TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_general_pr_ci_workflow_runs_full_pytest_suite():
    """General PR CI should run the full unit test suite on Python 3.10."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")

    assert "name: Tests" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'python-version: "3.10"' in workflow
    assert 'python -m pip install -e ".[test]"' in workflow
    assert "python -m pytest tests -q" in workflow
