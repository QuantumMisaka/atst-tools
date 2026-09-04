"""Governance tests for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERAL_TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def test_general_pr_ci_workflow_runs_full_pytest_suite():
    """General PR CI should run the full unit test suite on Python 3.10."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")

    assert "name: Tests" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'python-version: "3.10"' in workflow
    assert 'python -m pip install -e ".[test]"' in workflow
    assert "python -m pytest tests -q" in workflow


def test_general_ci_covers_main_and_documentation_governance():
    """General CI should cover main pushes and the documentation checker."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")

    assert "  push:\n    branches: [main]" in workflow
    assert "  test:\n" in workflow
    assert "  documentation-governance:\n" in workflow
    assert "python scripts/check_docs_governance.py" in workflow
    assert workflow.count('python-version: "3.10"') == 2
    assert workflow.count('python -m pip install -e ".[test]"') == 2
    assert "id-token: write" not in workflow


def test_release_workflow_separates_resolution_preflight_and_publish():
    """Release publication must consume a verified preflight artifact."""
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "  resolve-release:\n" in workflow
    assert "  release-preflight:\n" in workflow
    assert "  publish:\n" in workflow
    assert "ref: ${{ steps.resolve-release.outputs.ref }}" in workflow
    assert "needs: resolve-release" in workflow
    assert "ref: ${{ needs.resolve-release.outputs.ref }}" in workflow
    assert "python scripts/check_release_readiness.py --tag \"$RELEASE_TAG\"" in workflow
    assert "python -m pytest tests -q" in workflow
    assert "python scripts/check_docs_governance.py" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check --strict dist/*" in workflow
    assert "python scripts/verify_wheel_api.py" in workflow
    assert "path: dist/*" in workflow

    readiness = workflow.index("python scripts/check_release_readiness.py")
    pytest = workflow.index("python -m pytest tests -q", readiness)
    docs = workflow.index("python scripts/check_docs_governance.py", pytest)
    build = workflow.index("python -m build", docs)
    twine = workflow.index("python -m twine check --strict dist/*", build)
    verify = workflow.index("python scripts/verify_wheel_api.py", twine)
    artifact = workflow.index("actions/upload-artifact@v4", verify)
    assert readiness < pytest < docs < build < twine < verify < artifact


def test_release_publish_has_only_preflight_dependency_and_oidc_permission():
    """Only the publish job may request the PyPI OIDC token."""
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = workflow.split("  publish:\n", 1)[1]

    assert "needs: release-preflight" in publish
    assert "needs: resolve-release" not in publish
    assert "id-token: write" in publish
    assert workflow.count("id-token: write") == 1
    assert "id-token: write" not in workflow.split("  publish:\n", 1)[0]
