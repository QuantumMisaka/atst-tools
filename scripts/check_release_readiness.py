"""Check the local facts required before publishing a GitHub release."""

from __future__ import annotations

import argparse
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
