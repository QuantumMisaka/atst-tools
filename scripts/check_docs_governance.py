"""Check ATST-Tools documentation governance invariants."""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ACTIVE_MARKDOWN_ROOTS = (
    Path("README.md"),
    Path("examples/README.md"),
    Path("AGENTS.md"),
    Path("docs"),
)
CONFLICT_MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REPORT_LINK = re.compile(r"`(docs/reports/[^`]+?)`")
PENDING_LINK = re.compile(r"`(docs/archive/pending_delete/[^`]+?)`")
METADATA_ALIASES = {
    "version": ("**Version**", "**Version:**", "**版本**", "**版本:**"),
    "date": ("**Date**", "**Date:**", "**日期**", "**日期:**", "**Last Updated**", "Date:", "日期："),
    "status": ("**Status**", "**Status:**", "**状态**", "**状态:**"),
    "owner": ("**Owner**", "**Owner:**", "**责任人**", "**责任人:**"),
}


def active_markdown_files(root: Path) -> list[Path]:
    """Return active Markdown files that participate in governance checks."""
    files: list[Path] = []
    for entry in ACTIVE_MARKDOWN_ROOTS:
        path = root / entry
        if path.is_file() and path.suffix == ".md":
            files.append(path)
        elif path.is_dir():
            for markdown in path.rglob("*.md"):
                relative = markdown.relative_to(root)
                if len(relative.parts) >= 2 and relative.parts[:2] == ("docs", "archive"):
                    continue
                files.append(markdown)
    return sorted(set(files))


def report_files(root: Path) -> set[Path]:
    """Return active Markdown and HTML report files."""
    reports_dir = root / "docs" / "reports"
    return {
        path
        for path in reports_dir.iterdir()
        if path.is_file() and path.suffix in {".md", ".html"}
    }


def _strip_anchor(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.split("#", 1)[0]


def check_conflict_markers(root: Path) -> list[str]:
    """Check active Markdown files for unresolved conflict markers."""
    issues: list[str] = []
    for path in active_markdown_files(root):
        text = path.read_text(encoding="utf-8")
        if CONFLICT_MARKER.search(text):
            issues.append(f"{path.relative_to(root)} contains merge conflict marker")
    return issues


def check_markdown_links(root: Path) -> list[str]:
    """Check local relative Markdown links in active Markdown files."""
    issues: list[str] = []
    for path in active_markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = _strip_anchor(match.group(1))
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if "://" in target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                issues.append(f"{path.relative_to(root)} links outside repository: {target}")
                continue
            if not resolved.exists():
                issues.append(f"{path.relative_to(root)} has missing link target: {target}")
    return issues


def check_report_ledger(root: Path) -> list[str]:
    """Check that active reports are recorded in the documentation status ledger."""
    ledger = root / "docs" / "reports" / "DOCUMENTATION_STATUS_REPORT.md"
    ledger_text = ledger.read_text(encoding="utf-8")
    active_ledger_text = ledger_text.split("### L4:", 1)[0]
    mentioned = {
        root / link
        for link in REPORT_LINK.findall(active_ledger_text)
        if Path(link).suffix in {".md", ".html"}
    }
    expected = report_files(root) - {ledger}

    issues: list[str] = []
    for path in sorted(expected - mentioned):
        issues.append(f"active report is missing from documentation ledger: {path.relative_to(root)}")
    for path in sorted(mentioned - expected - {ledger}):
        if not path.exists():
            issues.append(f"documentation ledger references missing active report: {path.relative_to(root)}")
    return issues


def check_report_metadata(root: Path) -> list[str]:
    """Check active Markdown reports for required governance metadata."""
    issues: list[str] = []
    for path in sorted((root / "docs" / "reports").glob("*.md")):
        head = path.read_text(encoding="utf-8")[:1000]
        missing = [
            field
            for field, aliases in METADATA_ALIASES.items()
            if not any(alias in head for alias in aliases)
        ]
        if missing:
            issues.append(f"{path.relative_to(root)} missing metadata: {', '.join(missing)}")
    return issues


def check_pending_delete_inventory(root: Path) -> list[str]:
    """Check pending-delete files are recorded in both pending README and ledger."""
    pending_root = root / "docs" / "archive" / "pending_delete"
    pending_readme = pending_root / "README.md"
    ledger = root / "docs" / "reports" / "DOCUMENTATION_STATUS_REPORT.md"
    pending_text = pending_readme.read_text(encoding="utf-8")
    ledger_text = ledger.read_text(encoding="utf-8")
    ledger_mentions = {root / link for link in PENDING_LINK.findall(ledger_text)}

    issues: list[str] = []
    for path in sorted(p for p in pending_root.rglob("*") if p.is_file() and p != pending_readme):
        relative_to_pending = path.relative_to(pending_root).as_posix()
        if relative_to_pending not in pending_text:
            issues.append(f"pending-delete README omits {path.relative_to(root)}")
        if path not in ledger_mentions:
            issues.append(f"documentation ledger omits pending-delete file {path.relative_to(root)}")
    return issues


def check_html_reports(root: Path) -> list[str]:
    """Parse active HTML reports with Python's standard HTML parser."""
    issues: list[str] = []
    for path in sorted((root / "docs" / "reports").glob("*.html")):
        parser = HTMLParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except Exception as exc:  # pragma: no cover - HTMLParser rarely raises.
            issues.append(f"{path.relative_to(root)} failed HTMLParser parse: {exc}")
    return issues


def check_repository(root: Path) -> list[str]:
    """Return documentation governance issues for a repository root."""
    root = root.resolve()
    issues: list[str] = []
    issues.extend(check_conflict_markers(root))
    issues.extend(check_markdown_links(root))
    issues.extend(check_report_ledger(root))
    issues.extend(check_report_metadata(root))
    issues.extend(check_pending_delete_inventory(root))
    issues.extend(check_html_reports(root))
    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root to check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    issues = check_repository(args.root)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1
    print("documentation governance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
