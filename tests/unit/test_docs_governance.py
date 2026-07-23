import importlib.util
import re
from pathlib import Path

import pytest


# User-facing pages may describe product capabilities and portable execution
# concepts, but must not become a maintenance runbook.  Keep this list
# explicit: adding a term requires an intentional documentation-boundary
# decision rather than silently broadening a substring search.
USER_ENTRYPOINTS = (
    Path("README.md"),
    Path("docs/index.md"),
    Path("examples/README.md"),
)
FORBIDDEN_USER_PATTERNS = {
    "sai": r"\bsai\b",
    "test": r"\btests?\b",
    "pytest": r"\bpytest\b",
    "coverage": r"\bcoverage\b",
    "ci": r"\bci\b(?!-neb)",
    ".github/workflows": r"\.github/workflows",
    "github actions": r"\bgithub actions\b",
    "sbatch": r"\bsbatch\b",
    "module": r"\bmodules?\b",
    "partition": r"\bpartition\b",
    "qos": r"\bqos\b",
    "server": r"\bservers?\b",
    "job": r"\bjobs?\b",
    "validation-run": r"\bvalidation[_ -]?runs?\b",
    "8v100v0": r"\b8v100v0\b",
    "rush-gpu": r"\brush-gpu\b",
    "huge-gpu": r"\bhuge-gpu\b",
}


def _forbidden_user_terms(text: str) -> list[str]:
    """Return case-insensitive maintainer/site phrases found in user prose."""
    return [
        term
        for term, pattern in FORBIDDEN_USER_PATTERNS.items()
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def _user_entrypoint_text(path: Path) -> str:
    """Return user-facing prose, restricting the index to its User Path section."""
    text = path.read_text(encoding="utf-8")
    if path.as_posix().endswith("docs/index.md"):
        return text.split("## User Path\n", 1)[1].split("## Developer Path\n", 1)[0]
    return text


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


@pytest.mark.parametrize(
    ("phrase", "term"),
    [
        ("run the TEST suite", "test"),
        ("maintained through a CI pipeline", "ci"),
        ("load a MODULE", "module"),
        ("choose a PARTITION", "partition"),
        ("request a QOS", "qos"),
        ("connect to the SERVER", "server"),
        ("connect to the SERVERS", "server"),
        ("submit a JOB", "job"),
        ("record a validation-run", "validation-run"),
        ("record validation runs", "validation-run"),
        ("record validation_runs", "validation-run"),
    ],
)
def test_user_boundary_detects_maintainer_phrases(phrase, term):
    """User prose rejects each common maintainer or site-operation phrase."""
    assert _forbidden_user_terms(phrase) == [term]


def test_user_boundary_allows_scientific_ci_neb_and_config_validation():
    """Generic CI-NEB scientific prose must not be mistaken for CI operations."""
    assert _forbidden_user_terms("Run a CI-NEB workflow with MPI.") == []
    assert _forbidden_user_terms("Use atst config validate config.yaml.") == []


def test_docs_index_user_boundary_excludes_developer_and_project_manager_paths(tmp_path):
    """Maintainer navigation outside User Path cannot trigger the user-doc gate."""
    index = tmp_path / "docs" / "index.md"
    index.parent.mkdir()
    index.write_text(
        "## User Path\nUse atst config validate config.yaml.\n"
        "## Developer Path\nRun tests on the SAI site.\n"
        "## Project Manager Path\nReview the CI validation-run.\n",
        encoding="utf-8",
    )

    assert _forbidden_user_terms(_user_entrypoint_text(index)) == []


def test_user_entrypoints_exclude_maintainer_and_site_operations():
    """User navigation stays product-focused while developer operations remain discoverable."""
    root = Path(__file__).resolve().parents[2]
    user_paths = [root / relative for relative in USER_ENTRYPOINTS]
    user_paths.extend(sorted((root / "docs/user").rglob("*.md")))

    violations = []
    for path in user_paths:
        text = _user_entrypoint_text(path)
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
