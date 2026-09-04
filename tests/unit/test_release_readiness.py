"""Tests for the offline release-readiness checker."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_checker():
    script = ROOT / "scripts" / "check_release_readiness.py"
    spec = importlib.util.spec_from_file_location("check_release_readiness", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fixture_root(tmp_path: Path, compatibility: str = "9.8.7") -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture-package"\nversion = "9.8.7"\n',
        encoding="utf-8",
    )
    release_dir = tmp_path / "docs" / "releases"
    release_dir.mkdir(parents=True)
    (release_dir / "RELEASE_NOTES_9.8.7.md").write_text(
        "# Fixture release\n\n## Compatibility\n\n"
        f"- Package version: `{compatibility}`.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "pyproject.toml", "docs"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    subprocess.run(["git", "tag", "v9.8.7"], cwd=tmp_path, check=True)
    return tmp_path


def test_release_readiness_accepts_matching_tag_and_compatibility_line(tmp_path):
    """A version-matched tag and exact compatibility line make a release ready."""
    checker = _load_checker()

    assert checker.main(["--root", str(_fixture_root(tmp_path)), "--tag", "v9.8.7"]) == 0


@pytest.mark.parametrize("tag_setup", ["missing", "non-commit", "mismatched"])
def test_release_readiness_requires_tag_to_resolve_to_checked_out_head(tmp_path, tag_setup, capsys):
    """Readiness rejects a missing, non-commit, or mismatched release tag."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    if tag_setup == "missing":
        subprocess.run(["git", "tag", "-d", "v9.8.7"], cwd=root, check=True, capture_output=True)
    elif tag_setup == "non-commit":
        subprocess.run(["git", "tag", "-d", "v9.8.7"], cwd=root, check=True, capture_output=True)
        blob = subprocess.run(
            ["git", "rev-parse", "HEAD:pyproject.toml"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(["git", "tag", "v9.8.7", blob], cwd=root, check=True)
    else:
        (root / "marker").write_text("different commit\n", encoding="utf-8")
        subprocess.run(["git", "add", "marker"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "different commit"], cwd=root, check=True)

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "tag" in captured.err.lower()
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("tag", "fixture_kwargs", "remove_note", "message"),
    [
        ("9.8.7", {}, False, "must exactly match"),
        ("v9.8.8", {}, False, "must exactly match"),
        ("v9.8.7", {}, True, "release note is missing"),
        ("v9.8.7", {"compatibility": "9.8.6"}, False, "exact Compatibility line"),
    ],
)
def test_release_readiness_rejects_invalid_release_contract(
    tmp_path, tag, fixture_kwargs, remove_note, message, capsys
):
    """A malformed tag, missing note, or wrong compatibility line blocks readiness."""
    checker = _load_checker()
    root = _fixture_root(tmp_path, **fixture_kwargs)
    if remove_note:
        (root / "docs" / "releases" / "RELEASE_NOTES_9.8.7.md").unlink()

    assert checker.main(["--root", str(root), "--tag", tag]) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert message in captured.err


@pytest.mark.parametrize(
    "pyproject_contents",
    [
        b"[project]\nversion = [\n",
        b"[project]\nversion = \"9.8.7\"\n\xff",
    ],
)
def test_release_readiness_reports_malformed_or_undecodable_metadata(tmp_path, pyproject_contents, capsys):
    """Malformed or undecodable project metadata returns one diagnostic."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    (root / "pyproject.toml").write_bytes(pyproject_contents)

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "project version" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_reports_missing_project_metadata(tmp_path, capsys):
    """A missing project file returns one clear diagnostic rather than a traceback."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    (root / "pyproject.toml").unlink()

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "project version" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_reports_undecodable_release_note(tmp_path, capsys):
    """An undecodable release note returns one clear diagnostic."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    (root / "docs" / "releases" / "RELEASE_NOTES_9.8.7.md").write_bytes(b"\xff")

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "release note" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_reports_unreadable_release_note(tmp_path, capsys):
    """An unreadable release note returns one clear diagnostic."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    release_note = root / "docs" / "releases" / "RELEASE_NOTES_9.8.7.md"
    release_note.chmod(0)
    try:
        assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    finally:
        release_note.chmod(0o644)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "unable to read release note" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_rejects_malformed_toml_after_valid_version(tmp_path, capsys):
    """A malformed TOML suffix cannot be hidden by an earlier valid version."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture-package"\nversion = "9.8.7"\n[broken\n',
        encoding="utf-8",
    )

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "project version" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_ignores_multiline_string_version_decoy(tmp_path, capsys):
    """A version-looking line inside a multiline string is not project metadata."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\n'
        'description = """\n'
        'version = "9.8.7"\n'
        '"""\n'
        'version = "9.8.8"\n',
        encoding="utf-8",
    )

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "must exactly match 'v9.8.8'" in captured.err
    assert "Traceback" not in captured.err


def test_release_readiness_reports_missing_tomli_without_traceback(tmp_path, monkeypatch, capsys):
    """A Python 3.10 environment without tomli fails with one clear diagnostic."""
    checker = _load_checker()
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(checker, "tomllib", None)

    assert checker.main(["--root", str(root), "--tag", "v9.8.7"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("ERROR:") == 1
    assert "tomli" in captured.err
    assert "Traceback" not in captured.err
