import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "abacuslite-ase-interface.yml"
SNAPSHOT = ROOT / "src" / "atst_tools" / "external" / "ASE_interface" / "ABACUSLITE_SNAPSHOT.md"


def test_abacuslite_ci_workflow_exists():
    """The vendored ASE interface should have a dedicated maintenance CI."""
    assert WORKFLOW.exists()


def test_abacuslite_ci_runs_atst_regression_and_vendored_module_tests():
    """The CI should cover both ATST wrappers and upstream-style parser tests."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "tests/unit/test_abacuslite_profile.py" in workflow
    assert "tests/unit/test_abacus_io.py" in workflow
    assert "atst_tools.external.ASE_interface.abacuslite.io.generalio" in workflow
    assert "atst_tools.external.ASE_interface.abacuslite.io.legacyio" in workflow
    assert "atst_tools.external.ASE_interface.abacuslite.io.latestio" in workflow
    assert "atst_tools.external.ASE_interface.abacuslite.utils.ksampling" in workflow
    assert "src/atst_tools/external/ASE_interface/**" in workflow


def test_abacuslite_ci_runs_snapshot_drift_checker():
    """The abacuslite CI should resolve ABACUS_DEVELOP_REF from ABACUSLITE_SNAPSHOT.md (single source of truth)."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    snapshot = SNAPSHOT.read_text(encoding="utf-8")

    # ABACUSLITE_SNAPSHOT.md pins exactly one upstream baseline SHA (spec R4/P6).
    baselines = re.findall(r"当前基线：上游 `([0-9a-f]{40})`", snapshot)
    assert len(baselines) == 1
    baseline = baselines[0]

    # The workflow must parse ABACUS_DEVELOP_REF from ABACUSLITE_SNAPSHOT.md instead of hardcoding it,
    # so the pinned baseline is never written twice.
    assert "ABACUSLITE_SNAPSHOT.md" in workflow
    assert "当前基线：上游" in workflow
    assert "ABACUS_DEVELOP_REF" in workflow
    assert baseline not in workflow

    assert "repository: deepmodeling/abacus-develop" in workflow
    assert "path: abacus-develop" in workflow
    assert "scripts/check_abacuslite_snapshot.py" in workflow
    assert "--upstream abacus-develop/interfaces/ASE_interface" in workflow
    assert "--vendored src/atst_tools/external/ASE_interface" in workflow


def test_abacuslite_ci_runs_reorder_and_snapshot_tests_when_ci_changes():
    """Workflow path filters should include new abacuslite CI guard files."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "tests/unit/test_abacuslite_io_reorder.py" in workflow
    assert "tests/unit/test_abacuslite_snapshot_ci.py" in workflow
    assert "scripts/check_abacuslite_snapshot.py" in workflow
