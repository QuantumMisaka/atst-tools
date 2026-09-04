"""Check the local facts required before publishing a GitHub release."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility for the maintenance env.
    tomllib = None


_PROJECT_VERSION = re.compile(
    r"(?ms)^\[project\]\s*(?:[^\[]*?)^version\s*=\s*['\"]([^'\"]+)['\"]"
)


def _project_version(root: Path) -> str:
    """Read the package version from ``pyproject.toml``."""
    path = root / "pyproject.toml"
    if tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]

    match = _PROJECT_VERSION.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("pyproject.toml has no [project].version")
    return match.group(1)


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
        version = _project_version(root)
    except (OSError, KeyError, TypeError, ValueError) as exc:
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
    if not release_note.is_file():
        print(f"ERROR: release note is missing: {release_note.relative_to(root)}", file=sys.stderr)
        return 1

    compatibility_line = f"- Package version: `{version}`."
    text = release_note.read_text(encoding="utf-8")
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
