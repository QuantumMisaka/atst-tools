"""Tests for the abacuslite vendored snapshot drift checker."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_abacuslite_snapshot.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_abacuslite_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_snapshot_checker_accepts_packaging_imports_and_embedded_test_churn(tmp_path, capsys):
    checker = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(
        upstream / "abacuslite" / "core.py",
        "from abacuslite.io.generalio import read_stru\n"
        "VALUE = 1\n\n"
        "class TestCore:\n"
        "    def test_upstream_only(self):\n"
        "        assert VALUE == 1\n",
    )
    _write(
        vendored / "abacuslite" / "core.py",
        "from .io.generalio import read_stru\nVALUE = 1\n",
    )
    _write(upstream / "README.md", "upstream docs\n")
    _write(vendored / "README.md", "upstream docs\n")
    _write(vendored / "__init__.py", "\"\"\"ATST package marker.\"\"\"\n")

    assert checker.compare_snapshots(upstream, vendored) == 0
    assert capsys.readouterr().out == ""


def test_snapshot_checker_reports_implementation_drift(tmp_path, capsys):
    checker = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(upstream / "abacuslite" / "io" / "latestio.py", "VALUE = 1\n")
    _write(vendored / "abacuslite" / "io" / "latestio.py", "VALUE = 2\n")

    assert checker.compare_snapshots(upstream, vendored) == 1
    output = capsys.readouterr().out
    assert "Implementation drift detected" in output
    assert "-VALUE = 1" in output
    assert "+VALUE = 2" in output


def test_snapshot_checker_ignores_python_comment_only_churn(tmp_path, capsys):
    checker = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(
        upstream / "abacuslite" / "core.py",
        "# upstream-only explanatory comment\nVALUE = 1\n",
    )
    _write(
        vendored / "abacuslite" / "core.py",
        "# ATST wraps the same explanation differently\n\nVALUE = 1\n",
    )

    assert checker.compare_snapshots(upstream, vendored) == 0
    assert capsys.readouterr().out == ""


def test_snapshot_checker_accepts_documented_legacy_band_parser_adaptation(tmp_path, capsys):
    checker = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    upstream_block = """\
def read_band_from_running_log(raw):
    while j < len(raw) and len(rows) < nbnd:
        if re.match(ekb_leading_pat, raw[j]):
            break
        parts = raw[j].strip().split()
        if len(parts) >= 3 and parts[0].isdigit():
            try:
                band_index = int(parts[0])
                if band_index == len(rows) + 1:
                    rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                pass
        j += 1
"""
    vendored_block = """\
def read_band_from_running_log(raw):
    while j < len(raw) and len(rows) < nbnd:
        parts = raw[j].strip().split()
        if len(parts) >= 3 and parts[0].isdigit():
            try:
                rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                pass
        j += 1
"""
    _write(upstream / "abacuslite" / "io" / "legacyio.py", upstream_block)
    _write(vendored / "abacuslite" / "io" / "legacyio.py", vendored_block)

    assert checker.compare_snapshots(upstream, vendored) == 0
    assert capsys.readouterr().out == ""


def test_snapshot_checker_keeps_non_test_class_test_named_methods(tmp_path, capsys):
    checker = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(
        upstream / "abacuslite" / "core.py",
        "class Probe:\n"
        "    def test_connection(self):\n"
        "        return 'upstream'\n",
    )
    _write(
        vendored / "abacuslite" / "core.py",
        "class Probe:\n"
        "    def test_connection(self):\n"
        "        return 'vendored'\n",
    )

    assert checker.compare_snapshots(upstream, vendored) == 1
    output = capsys.readouterr().out
    assert "Implementation drift detected" in output
    assert "-        return 'upstream'" in output
    assert "+        return 'vendored'" in output
