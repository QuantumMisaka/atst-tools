from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "abacuslite-ase-interface.yml"


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
    """The abacuslite CI should compare the vendored snapshot with pinned upstream."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "ABACUS_DEVELOP_REF: 762919f6421dc1b79f9213e902a79b37b66db937" in workflow
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
