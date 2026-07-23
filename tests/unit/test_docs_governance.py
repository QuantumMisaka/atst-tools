import importlib.util
from pathlib import Path


# User-facing pages may describe product capabilities and portable execution
# concepts, but must not become a maintenance runbook.  Keep this list
# explicit: adding a term requires an intentional documentation-boundary
# decision rather than silently broadening a substring search.
USER_ENTRYPOINTS = (
    Path("README.md"),
    Path("docs/index.md"),
    Path("examples/README.md"),
)
FORBIDDEN_USER_TERMS = (
    "sai",
    "pytest",
    "coverage",
    ".github/workflows",
    "test suite",
    "ci pipeline",
    "github actions",
    "sbatch",
    "8v100v0",
    "rush-gpu",
    "huge-gpu",
)


def _forbidden_user_terms(text: str) -> list[str]:
    """Return case-insensitive maintainer/site phrases found in user prose."""
    normalized = text.casefold()
    return [term for term in FORBIDDEN_USER_TERMS if term in normalized]


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


def test_user_boundary_detects_maintainer_phrases_but_allows_ci_neb():
    """Generic CI-NEB scientific prose must not be mistaken for CI operations."""
    assert _forbidden_user_terms("Run the test suite through the CI pipeline in GitHub Actions.") == [
        "test suite",
        "ci pipeline",
        "github actions",
    ]
    assert _forbidden_user_terms("Run a CI-NEB workflow with MPI.") == []


def test_user_entrypoints_exclude_maintainer_and_site_operations():
    """User navigation stays product-focused while developer operations remain discoverable."""
    root = Path(__file__).resolve().parents[2]
    user_paths = [root / relative for relative in USER_ENTRYPOINTS]
    user_paths.extend(sorted((root / "docs/user").rglob("*.md")))

    violations = []
    for path in user_paths:
        text = path.read_text(encoding="utf-8")
        for term in _forbidden_user_terms(text):
            violations.append(f"{path.relative_to(root)} contains forbidden term {term!r}")
    assert not violations, "\n".join(violations)

    operations_guide = root / "docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md"
    assert operations_guide.is_file()
    handover = (root / "docs/developer/HANDOVER.md").read_text(encoding="utf-8")
    status_report = (root / "docs/reports/DOCUMENTATION_STATUS_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "EXAMPLE_VALIDATION_OPERATIONS.md" in handover
    assert "docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md" in status_report
