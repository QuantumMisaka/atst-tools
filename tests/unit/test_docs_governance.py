import importlib.util
import re
from pathlib import Path

import pytest


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
CANONICAL_REPOSITORIES = {
    "GitHub": "https://github.com/QuantumMisaka/atst-tools",
    "Gitee": "https://gitee.com/jamesmisaka/atst-tools",
}


def _markdown_targets(text: str) -> set[str]:
    return {match.group(1).strip("<>") for match in MARKDOWN_LINK.finditer(text)}


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


def test_readme_has_absolute_cross_channel_user_entrypoints():
    targets = _markdown_targets(Path("README.md").read_text(encoding="utf-8"))

    expected = {
        f"{CANONICAL_REPOSITORIES['GitHub']}/blob/main/docs/user/USER_GUIDE_CN.md",
        f"{CANONICAL_REPOSITORIES['Gitee']}/blob/main/docs/user/USER_GUIDE_CN.md",
        f"{CANONICAL_REPOSITORIES['GitHub']}/tree/main/examples",
        f"{CANONICAL_REPOSITORIES['Gitee']}/tree/main/examples",
    }
    assert expected <= targets


def test_active_user_docs_use_current_repository_and_release_facts():
    repository_docs = {
        path: Path(path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/user/USER_GUIDE_CN.md")
    }
    active_user_docs = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "docs/user/USER_GUIDE_CN.md",
            "docs/user/CONFIG_REFERENCE.md",
            "docs/user/PYTHON_API_REFERENCE.md",
        )
    }

    assert all("https://github.com/QuantumMisaka/atst-tools.git" in text for text in repository_docs.values())
    assert all("https://github.com/deepmodeling/atst-tools.git" not in text for text in repository_docs.values())
    assert "当前 2.2.3 版本" in active_user_docs["docs/user/USER_GUIDE_CN.md"]
    assert "RELEASE_NOTES_2.2.3.md" in active_user_docs["docs/user/USER_GUIDE_CN.md"]
    assert "**Version**: 2.2.3" in active_user_docs["docs/user/CONFIG_REFERENCE.md"]
    assert "**Version**: 2.2.1" not in active_user_docs["docs/user/CONFIG_REFERENCE.md"]
    assert "This reference tracks the current 2.2.3 release" in active_user_docs["docs/user/PYTHON_API_REFERENCE.md"]
    assert "This reference tracks the current 2.2.1 release" not in active_user_docs["docs/user/PYTHON_API_REFERENCE.md"]
    assert "(2.2.1)" in active_user_docs["docs/user/PYTHON_API_REFERENCE.md"]


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


def test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    cli_skill = Path("docs/skills/atst-cli/SKILL.md").read_text(encoding="utf-8")
    release_notes = Path("docs/releases/RELEASE_NOTES_2.2.3.md").read_text(encoding="utf-8")

    assert "维护验证环境" in agents
    assert "用户运行前提" not in agents
    assert "main is the v1.5.x legacy line" not in cli_skill
    assert "- Package version: `2.2.3`." in release_notes
