"""Tests for the offline release-readiness checker."""

from __future__ import annotations

import importlib.util
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
    return tmp_path


def test_release_readiness_accepts_matching_tag_and_compatibility_line(tmp_path):
    """A version-matched tag and exact compatibility line make a release ready."""
    checker = _load_checker()

    assert checker.main(["--root", str(_fixture_root(tmp_path)), "--tag", "v9.8.7"]) == 0


@pytest.mark.parametrize(
    ("tag", "fixture_kwargs", "remove_note"),
    [
        ("9.8.7", {}, False),
        ("v9.8.8", {}, False),
        ("v9.8.7", {}, True),
        ("v9.8.7", {"compatibility": "9.8.6"}, False),
    ],
)
def test_release_readiness_rejects_invalid_release_contract(
    tmp_path, tag, fixture_kwargs, remove_note
):
    """A malformed tag, missing note, or wrong compatibility line blocks readiness."""
    checker = _load_checker()
    root = _fixture_root(tmp_path, **fixture_kwargs)
    if remove_note:
        (root / "docs" / "releases" / "RELEASE_NOTES_9.8.7.md").unlink()

    assert checker.main(["--root", str(root), "--tag", tag]) != 0
