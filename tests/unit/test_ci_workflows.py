"""Governance tests for GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GENERAL_TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def _job_block(workflow: str, job_name: str) -> str:
    """Return one top-level GitHub Actions job block from static YAML text."""
    pattern = rf"(?ms)^  {re.escape(job_name)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)"
    match = re.search(pattern, workflow)
    assert match is not None, f"missing workflow job: {job_name}"
    return match.group(0)


def _job_permissions(job: str) -> list[str]:
    """Return the entries in a job-local permissions mapping."""
    match = re.search(r"(?ms)^    permissions:\n(?P<body>(?:^      [^\n]+\n)+)", job)
    assert match is not None, "missing job-local permissions mapping"
    return [line.strip() for line in match.group("body").splitlines()]


def _artifact_step(job: str, action: str) -> str:
    """Return the step containing one upload/download action."""
    action_start = job.index(f"        uses: {action}@v4")
    step_start = job.rfind("      - ", 0, action_start)
    assert step_start >= 0, f"missing step for {action}"
    next_step = re.search(r"(?m)^      - ", job[action_start:])
    step_end = action_start + next_step.start() if next_step else len(job)
    return job[step_start:step_end]


def _artifact_name(job: str, action: str) -> str:
    """Return the artifact name configured for one upload/download action."""
    step = _artifact_step(job, action)
    match = re.search(r"(?m)^          name: ([^\n]+)", step)
    assert match is not None, f"missing artifact name for {action}"
    return match.group(1).strip()


def test_general_pr_ci_workflow_runs_full_pytest_suite():
    """General PR CI should run the full unit test suite on Python 3.10."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")
    test_job = _job_block(workflow, "test")

    assert "name: Tests" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'python-version: "3.10"' in workflow
    assert 'python -m pip install -e ".[test]"' in workflow
    assert "python -m pytest tests -q" in test_job


def test_general_ci_covers_main_and_documentation_governance():
    """General CI should cover main pushes and the documentation checker."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")
    docs_job = _job_block(workflow, "documentation-governance")

    assert "  push:\n    branches: [main]" in workflow
    assert "  test:\n" in workflow
    assert "  documentation-governance:\n" in workflow
    assert "python scripts/check_docs_governance.py" in docs_job
    assert workflow.count('python-version: "3.10"') == 2
    assert workflow.count('python -m pip install -e ".[test]"') == 2
    assert "id-token: write" not in workflow


def test_release_workflow_separates_resolution_preflight_and_publish():
    """Release publication must consume a verified preflight artifact."""
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    preflight = _job_block(workflow, "release-preflight")
    publish = _job_block(workflow, "publish")

    assert "  resolve-release:\n" in workflow
    assert "  release-preflight:\n" in workflow
    assert "  publish:\n" in workflow
    assert "ref: ${{ steps.resolve-release.outputs.ref }}" in workflow
    assert "needs: resolve-release" in preflight
    assert "ref: ${{ needs.resolve-release.outputs.ref }}" in preflight
    assert "python scripts/check_release_readiness.py --tag \"$RELEASE_TAG\"" in preflight
    assert "python -m pytest tests -q" in preflight
    assert "python scripts/check_docs_governance.py" in preflight
    assert "python -m build" in preflight
    assert "python -m twine check --strict dist/*" in preflight
    assert "python scripts/verify_wheel_api.py" in preflight
    assert "actions/upload-artifact@v4" in preflight
    assert "path: dist/*" in preflight
    assert _artifact_name(preflight, "actions/upload-artifact") == "python-distributions"
    assert _artifact_name(publish, "actions/download-artifact") == "python-distributions"

    readiness = preflight.index("python scripts/check_release_readiness.py")
    pytest = preflight.index("python -m pytest tests -q", readiness)
    docs = preflight.index("python scripts/check_docs_governance.py", pytest)
    build = preflight.index("python -m build", docs)
    twine = preflight.index("python -m twine check --strict dist/*", build)
    verify = preflight.index("python scripts/verify_wheel_api.py", twine)
    artifact = preflight.index("actions/upload-artifact@v4", verify)
    assert readiness < pytest < docs < build < twine < verify < artifact


def test_release_publish_has_only_preflight_dependency_and_oidc_permission():
    """Only the publish job may request the PyPI OIDC token."""
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = _job_block(workflow, "publish")

    assert "needs: release-preflight" in publish
    assert "needs: resolve-release" not in publish
    assert "actions/download-artifact@v4" in publish
    assert "actions/checkout@v4" not in publish
    assert "python -m build" not in publish
    assert _job_permissions(publish) == ["id-token: write"]
    assert workflow.count("id-token: write") == 1


def test_artifact_name_does_not_leak_from_a_later_step():
    """Artifact extraction must not accept a later step's ``with.name``."""
    job = """      - name: Upload distributions artifact
        uses: actions/upload-artifact@v4
        with:
          path: dist/*
      - name: Later step
        run: echo done
        with:
          name: python-distributions
"""

    with pytest.raises(AssertionError, match="missing artifact name"):
        _artifact_name(job, "actions/upload-artifact")
