import importlib.util
from pathlib import Path


def _load_governance_script():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "check_docs_governance.py"
    spec = importlib.util.spec_from_file_location("check_docs_governance", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_docs_governance_checks_pass_for_current_tree():
    root = Path(__file__).resolve().parents[2]
    module = _load_governance_script()

    issues = module.check_repository(root)

    assert issues == []


def test_docs_governance_cli_returns_success_for_current_tree():
    root = Path(__file__).resolve().parents[2]
    module = _load_governance_script()

    assert module.main(["--root", str(root)]) == 0
