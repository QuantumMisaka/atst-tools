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
