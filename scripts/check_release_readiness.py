"""Check the local facts required before publishing a GitHub release."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

if sys.version_info >= (3, 11):
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - part of the Python 3.11 stdlib.
        tomllib = None
else:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


def load_project_version(root: Path) -> str:
    """Read the package version from ``pyproject.toml``."""
    if tomllib is None:
        raise RuntimeError(
            "TOML parser is unavailable; install the release extra (tomli on Python <3.11)"
        )
    path = root / "pyproject.toml"
    with path.open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]

    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml [project].version must be a non-empty string")
    return version


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse checker arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--tag", required=True, help="v-prefixed release tag")
    return parser.parse_args(argv)


def _resolve_commit(root: Path, ref: str) -> str:
    """Resolve a local Git ref to a commit without contacting a remote."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or "").strip()
        message = f"Git ref {ref!r} does not resolve to a commit"
        if detail:
            message += f": {detail}"
        raise RuntimeError(message) from exc

    commit = result.stdout.strip()
    if not commit:
        raise RuntimeError(f"Git ref {ref!r} does not resolve to a commit")
    return commit


def main(argv: Sequence[str] | None = None) -> int:
    """Return zero only when the local release facts are internally consistent."""
    args = _parse_args(argv)
    root = args.root.resolve()

    try:
        version = load_project_version(root)
    except (OSError, UnicodeDecodeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: unable to read project version: {exc}", file=sys.stderr)
        return 1

    expected_tag = f"v{version}"
    if args.tag != expected_tag:
        print(
            f"ERROR: release tag {args.tag!r} must exactly match {expected_tag!r}",
            file=sys.stderr,
        )
        return 1

    try:
        tag_commit = _resolve_commit(root, f"refs/tags/{args.tag}^{{commit}}")
        head_commit = _resolve_commit(root, "HEAD^{commit}")
    except RuntimeError as exc:
        print(f"ERROR: unable to verify release tag: {exc}", file=sys.stderr)
        return 1

    if tag_commit != head_commit:
        print(
            f"ERROR: release tag {args.tag!r} resolves to {tag_commit}, but HEAD is {head_commit}",
            file=sys.stderr,
        )
        return 1

    release_note = root / "docs" / "releases" / f"RELEASE_NOTES_{version}.md"
    try:
        if not release_note.is_file():
            print(
                f"ERROR: release note is missing: {release_note.relative_to(root)}",
                file=sys.stderr,
            )
            return 1
        text = release_note.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: unable to read release note: {exc}", file=sys.stderr)
        return 1

    compatibility_line = f"- Package version: `{version}`."
    if compatibility_line not in text.splitlines():
        print(
            f"ERROR: release note must contain the exact Compatibility line {compatibility_line!r}",
            file=sys.stderr,
        )
        return 1

    print(f"release readiness checks passed: {args.tag} is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
