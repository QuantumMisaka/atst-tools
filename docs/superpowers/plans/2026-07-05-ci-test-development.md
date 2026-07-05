# CI Test Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen ATST-Tools CI so abacuslite upstream drift, ABACUS ASE I/O regressions, and ordinary project test failures are caught automatically during pull requests.

**Architecture:** First add a focused regression test for the confirmed abacuslite `magmoms` reorder drift and sync the vendored backend implementation. Then add a small snapshot-drift checker script that compares the vendored ASE interface against a pinned upstream `abacus-develop` checkout after normalizing ATST's packaging-only differences. Finally wire the checker into the existing abacuslite CI, add a general PR test workflow for the full unit suite, and update developer-facing documentation.

**Tech Stack:** Python 3.10, pytest, unittest, GitHub Actions, ASE, vendored `abacuslite`.

---

## Current Context

- Existing abacuslite CI: `.github/workflows/abacuslite-ase-interface.yml`.
- Existing release CI: `.github/workflows/publish-pypi.yml`.
- No general pull-request workflow currently runs `pytest tests -q`.
- Vendored backend root: `src/atst_tools/external/ASE_interface`.
- Upstream reference root in this checkout: `temp_repos/abacus-develop/interfaces/ASE_interface`.
- Pinned upstream reference commit for CI checkout: `762919f6421dc1b79f9213e902a79b37b66db937`.
- Confirmed drift: upstream now reorders calculator `magmoms` with `mag[ind]` when `read_abacus_out(..., sort_atoms_with=...)` reorders atoms, while ATST currently passes `mag` unchanged in:
  - `src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py`
  - `src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py`
- Existing ATST abacuslite tests cover backup rotation, property keyword conflicts, dipole de-advertising, STRU species order, and mobility flags, but not `read_abacus_out` calculator magmom reordering.

## File Structure

- Create: `tests/unit/test_abacuslite_io_reorder.py`
  - Responsibility: pytest regression coverage for ABACUS output readers when `sort_atoms_with` reorders atoms.

- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py`
  - Responsibility: latest-format ABACUS output reader; sync calculator `magmoms` with reordered atom order.

- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py`
  - Responsibility: legacy-format ABACUS output reader; sync calculator `magmoms` with reordered atom order.

- Create: `scripts/check_abacuslite_snapshot.py`
  - Responsibility: compare upstream and vendored ASE interface trees while normalizing packaging-only import differences and ignoring embedded unittest method churn in vendored module files.

- Create: `tests/unit/test_abacuslite_snapshot_ci.py`
  - Responsibility: unit-test the snapshot checker's expected normalization and drift reporting.

- Modify: `.github/workflows/abacuslite-ase-interface.yml`
  - Responsibility: run abacuslite regression tests, vendored module unittests, and the pinned upstream snapshot drift check.

- Modify: `tests/unit/test_abacuslite_ci.py`
  - Responsibility: enforce that abacuslite CI includes the drift checker, pinned upstream ref, and new regression test.

- Create: `.github/workflows/tests.yml`
  - Responsibility: general pull-request CI for the full pytest suite.

- Create: `tests/unit/test_ci_workflows.py`
  - Responsibility: guard the general CI workflow structure.

- Modify: `README.md`
  - Responsibility: validation section should mention general PR CI and abacuslite-specific CI.

- Modify: `docs/developer/HANDOVER.md`
  - Responsibility: document commands and expectations for abacuslite snapshot sync and CI maintenance.

- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`
  - Responsibility: update tested vendored backend fixes and drift-check boundary.

## Implementation Tasks

### Task 1: Add `magmoms` Reorder Regression and Sync Vendored Readers

**Files:**
- Create: `tests/unit/test_abacuslite_io_reorder.py`
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py:507-511`
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py:901-905`

- [ ] **Step 1: Write the failing reader regression test**

Create `tests/unit/test_abacuslite_io_reorder.py` with:

```python
"""Regression tests for abacuslite output reader atom reordering."""

from __future__ import annotations

import numpy as np
import pytest

from atst_tools.external.ASE_interface.abacuslite.io import latestio, legacyio


def _mock_reader_data():
    frame = {
        "elem": ["Na", "Na", "Cl"],
        "coords": np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
            ]
        ),
        "cell": np.eye(3),
    }
    elecstate = [
        {
            "k": np.zeros((1, 1, 3)),
            "e": np.zeros((1, 1, 1)),
            "occ": np.ones((1, 1, 1)),
        }
    ]
    energies = [{"E_KohnSham": -1.0, "E_Fermi": 0.0}]
    kpoints = ((np.zeros((1, 3)), np.ones(1), None), None, None, None, None)
    magmoms = [np.array([10.0, 20.0, 30.0])]
    return frame, elecstate, energies, kpoints, magmoms


def _patch_reader(module, monkeypatch, frame, elecstate, energies, kpoints, magmoms):
    monkeypatch.setattr(module, "read_esolver_type_from_running_log", lambda lines: "ksdft")
    monkeypatch.setattr(module, "read_traj_from_running_log", lambda lines: [frame])
    monkeypatch.setattr(module, "read_forces_from_running_log", lambda lines: [])
    monkeypatch.setattr(module, "read_stress_from_running_log", lambda lines: [])
    monkeypatch.setattr(module, "read_kpoints_from_running_log", lambda lines: kpoints)
    monkeypatch.setattr(module, "read_energies_from_running_log", lambda lines: ([], energies))
    monkeypatch.setattr(module, "read_iter_header_from_running_log", lambda lines: [])
    monkeypatch.setattr(module, "find_final_info_with_iter_header", lambda rows, headers: energies)
    monkeypatch.setattr(module, "read_magmom_from_running_log", lambda lines: magmoms)
    if module is latestio:
        monkeypatch.setattr(module, "read_band_from_eig_occ", lambda path: elecstate)
    else:
        monkeypatch.setattr(module, "read_band_from_running_log", lambda lines: elecstate)


@pytest.mark.parametrize("module", [latestio, legacyio])
def test_read_abacus_out_reorders_calculator_magmoms_with_atoms(module, tmp_path, monkeypatch):
    """Reader result magmoms should follow reordered Atoms indices."""
    running_log = tmp_path / "running_scf.log"
    running_log.write_text("", encoding="utf-8")
    (tmp_path / "eig_occ.txt").write_text("", encoding="utf-8")
    frame, elecstate, energies, kpoints, magmoms = _mock_reader_data()
    _patch_reader(module, monkeypatch, frame, elecstate, energies, kpoints, magmoms)

    atoms = module.read_abacus_out(running_log, sort_atoms_with=[0, 2, 1])[0]

    assert atoms.get_chemical_symbols() == ["Na", "Cl", "Na"]
    np.testing.assert_allclose(atoms.get_initial_magnetic_moments(), [10.0, 30.0, 20.0])
    np.testing.assert_allclose(atoms.calc.results["magmoms"], [10.0, 30.0, 20.0])
```

- [ ] **Step 2: Run the new regression test to verify it fails**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_io_reorder.py -q
```

Expected: FAIL for both parametrized cases because `atoms.calc.results["magmoms"]` is `[10.0, 20.0, 30.0]` instead of `[10.0, 30.0, 20.0]`.

- [ ] **Step 3: Sync `latestio.py` with upstream magmom reordering**

In `src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py`, replace the calculator construction line:

```python
                                        magmoms=mag, efermi=ener['E_Fermi'],
```

with:

```python
                                        magmoms=mag[ind], efermi=ener['E_Fermi'],
```

- [ ] **Step 4: Sync `legacyio.py` with upstream magmom reordering**

In `src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py`, replace the calculator construction line:

```python
                                        magmoms=mag, efermi=ener['E_Fermi'],
```

with:

```python
                                        magmoms=mag[ind], efermi=ener['E_Fermi'],
```

- [ ] **Step 5: Run the targeted regression test to verify it passes**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_io_reorder.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 6: Run abacuslite regression and package-mode reader tests**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_io_reorder.py tests/unit/test_abacuslite_profile.py tests/unit/test_abacus_io.py tests/unit/test_abacuslite_ci.py -q
conda run -n atst-dev python -m unittest atst_tools.external.ASE_interface.abacuslite.io.latestio atst_tools.external.ASE_interface.abacuslite.io.legacyio -v
```

Expected: pytest PASS; unittest PASS with only the existing skipped pseudo/orbital tests outside these two modules absent from this command.

- [ ] **Step 7: Commit the reader sync**

Run:

```bash
git add tests/unit/test_abacuslite_io_reorder.py src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py
git commit -m "fix: sync abacuslite magmom reorder"
```

### Task 2: Add a Pinned Upstream Snapshot Drift Checker

**Files:**
- Create: `scripts/check_abacuslite_snapshot.py`
- Create: `tests/unit/test_abacuslite_snapshot_ci.py`

- [ ] **Step 1: Write failing unit tests for the snapshot checker**

Create `tests/unit/test_abacuslite_snapshot_ci.py` with:

```python
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
    _write(upstream / "abacuslite" / "core.py", "from abacuslite.io.generalio import read_stru\nVALUE = 1\n\nclass TestCore:\n    def test_upstream_only(self):\n        assert VALUE == 1\n")
    _write(vendored / "abacuslite" / "core.py", "from .io.generalio import read_stru\nVALUE = 1\n")
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
```

- [ ] **Step 2: Run snapshot checker tests to verify they fail**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_snapshot_ci.py -q
```

Expected: FAIL because `scripts/check_abacuslite_snapshot.py` does not exist.

- [ ] **Step 3: Add the snapshot checker script**

Create `scripts/check_abacuslite_snapshot.py` with:

```python
#!/usr/bin/env python3
"""Compare ATST's vendored abacuslite snapshot with a pinned upstream tree."""

from __future__ import annotations

import argparse
import ast
import difflib
import re
from pathlib import Path
from typing import Iterable


IGNORED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
VENDORED_ONLY_FILES = {Path("__init__.py")}


def _is_ignored(relative_path: Path) -> bool:
    if any(part in IGNORED_DIR_NAMES or part.endswith(".egg-info") for part in relative_path.parts):
        return True
    return relative_path.suffix in IGNORED_SUFFIXES


def _iter_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and not _is_ignored(path.relative_to(root))
    }


def _remove_embedded_test_methods(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    remove_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            end_lineno = getattr(node, "end_lineno", node.lineno)
            remove_lines.update(range(node.lineno, end_lineno + 1))

    if not remove_lines:
        return source

    lines = source.splitlines()
    filtered = [line for lineno, line in enumerate(lines, start=1) if lineno not in remove_lines]
    text = "\n".join(filtered)
    return f"{text}\n" if source.endswith("\n") else text


def _normalize_packaging_imports(source: str) -> str:
    replacements = {
        "from .io.generalio import": "from abacuslite.io.generalio import",
        "from .io.legacyio import": "from abacuslite.io.legacyio import",
        "from .io.latestio import": "from abacuslite.io.latestio import",
        "from .legacyio import": "from abacuslite.io.legacyio import",
    }
    for before, after in replacements.items():
        source = source.replace(before, after)
    return source


def _normalized_text(root: Path, relative_path: Path) -> str:
    source = (root / relative_path).read_text(encoding="utf-8")
    if relative_path.suffix == ".py" and relative_path.parts and relative_path.parts[0] == "abacuslite":
        source = _remove_embedded_test_methods(source)
        source = _normalize_packaging_imports(source)
    source = re.sub(r"[ \t]+$", "", source, flags=re.MULTILINE)
    return source


def _format_file_list(title: str, paths: Iterable[Path]) -> list[str]:
    listed = sorted(paths)
    if not listed:
        return []
    return [title, *[f"  - {path.as_posix()}" for path in listed]]


def compare_snapshots(upstream: Path, vendored: Path) -> int:
    """Return zero when vendored abacuslite matches the normalized upstream tree."""
    upstream = upstream.resolve()
    vendored = vendored.resolve()
    upstream_files = _iter_files(upstream)
    vendored_files = _iter_files(vendored)

    missing = upstream_files - vendored_files
    extra = vendored_files - upstream_files - VENDORED_ONLY_FILES
    output: list[str] = []
    output.extend(_format_file_list("Missing vendored files:", missing))
    output.extend(_format_file_list("Unexpected vendored-only files:", extra))

    for relative_path in sorted(upstream_files & vendored_files):
        upstream_text = _normalized_text(upstream, relative_path)
        vendored_text = _normalized_text(vendored, relative_path)
        if upstream_text == vendored_text:
            continue
        diff = difflib.unified_diff(
            upstream_text.splitlines(),
            vendored_text.splitlines(),
            fromfile=f"upstream/{relative_path.as_posix()}",
            tofile=f"vendored/{relative_path.as_posix()}",
            lineterm="",
        )
        output.append(f"Implementation drift detected in {relative_path.as_posix()}:")
        output.extend(diff)

    if output:
        print("\n".join(output))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the snapshot comparison command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True, type=Path, help="Path to upstream interfaces/ASE_interface")
    parser.add_argument("--vendored", required=True, type=Path, help="Path to ATST vendored ASE_interface")
    args = parser.parse_args(argv)
    if not args.upstream.exists():
        raise SystemExit(f"Upstream path does not exist: {args.upstream}")
    if not args.vendored.exists():
        raise SystemExit(f"Vendored path does not exist: {args.vendored}")
    return compare_snapshots(args.upstream, args.vendored)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run snapshot checker unit tests**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_snapshot_ci.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Run the checker against the local upstream temp repo**

Run:

```bash
conda run -n atst-dev python scripts/check_abacuslite_snapshot.py \
  --upstream temp_repos/abacus-develop/interfaces/ASE_interface \
  --vendored src/atst_tools/external/ASE_interface
```

Expected: PASS with no output after Task 1's `magmoms=mag[ind]` sync. If it reports drift, inspect the diff and either sync the implementation or adjust the normalizer only for packaging/test-only differences.

- [ ] **Step 6: Commit the drift checker**

Run:

```bash
git add scripts/check_abacuslite_snapshot.py tests/unit/test_abacuslite_snapshot_ci.py
git commit -m "test: add abacuslite snapshot drift checker"
```

### Task 3: Wire the Drift Checker Into AbacusLite CI

**Files:**
- Modify: `.github/workflows/abacuslite-ase-interface.yml`
- Modify: `tests/unit/test_abacuslite_ci.py`

- [ ] **Step 1: Write failing workflow governance tests**

Append these tests to `tests/unit/test_abacuslite_ci.py`:

```python
def test_abacuslite_ci_runs_snapshot_drift_checker():
    """The abacuslite CI should compare the vendored snapshot with pinned upstream."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "ABACUS_DEVELOP_REF: 762919f6421dc1b79f9213e902a79b37b66db937" in workflow
    assert "repository: deepmodeling/abacus-develop" in workflow
    assert "path: abacus-develop" in workflow
    assert "scripts/check_abacuslite_snapshot.py" in workflow
    assert "--upstream abacus-develop/interfaces/ASE_interface" in workflow
    assert "--vendored src/atst_tools/external/ASE_interface" in workflow


def test_abacuslite_ci_runs_reorder_and_snapshot_tests_when_ci_changes():
    """Workflow path filters should include new abacuslite CI guard files."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "tests/unit/test_abacuslite_io_reorder.py" in workflow
    assert "tests/unit/test_abacuslite_snapshot_ci.py" in workflow
    assert "scripts/check_abacuslite_snapshot.py" in workflow
```

- [ ] **Step 2: Run workflow governance tests to verify they fail**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_ci.py -q
```

Expected: FAIL because the workflow does not yet include the snapshot checker, pinned upstream checkout, or new test paths.

- [ ] **Step 3: Update the abacuslite CI workflow**

Replace `.github/workflows/abacuslite-ase-interface.yml` with:

```yaml
name: abacuslite ASE Interface Tests

on:
  pull_request:
    paths:
      - ".github/workflows/abacuslite-ase-interface.yml"
      - "scripts/check_abacuslite_snapshot.py"
      - "src/atst_tools/calculators/**"
      - "src/atst_tools/external/ASE_interface/**"
      - "src/atst_tools/utils/abacus_io.py"
      - "tests/unit/test_abacus_io.py"
      - "tests/unit/test_abacuslite_ci.py"
      - "tests/unit/test_abacuslite_io_reorder.py"
      - "tests/unit/test_abacuslite_profile.py"
      - "tests/unit/test_abacuslite_snapshot_ci.py"
      - "pyproject.toml"
  workflow_dispatch:

permissions:
  contents: read

defaults:
  run:
    shell: bash

env:
  ABACUS_DEVELOP_REF: 762919f6421dc1b79f9213e902a79b37b66db937

jobs:
  abacuslite-unit:
    name: abacuslite vendored interface
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Checkout ABACUS upstream reference
        uses: actions/checkout@v4
        with:
          repository: deepmodeling/abacus-develop
          ref: ${{ env.ABACUS_DEVELOP_REF }}
          path: abacus-develop

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install ATST-Tools test environment
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[test]"

      - name: Check vendored abacuslite snapshot drift
        run: |
          python scripts/check_abacuslite_snapshot.py \
            --upstream abacus-develop/interfaces/ASE_interface \
            --vendored src/atst_tools/external/ASE_interface

      - name: Run ATST abacuslite regression tests
        run: |
          python -m pytest \
            tests/unit/test_abacuslite_profile.py \
            tests/unit/test_abacus_io.py \
            tests/unit/test_abacuslite_io_reorder.py \
            tests/unit/test_abacuslite_snapshot_ci.py \
            tests/unit/test_abacuslite_ci.py \
            -q

      - name: Run vendored abacuslite package unit tests
        run: |
          python -m unittest atst_tools.external.ASE_interface.abacuslite.io.generalio -v
          python -m unittest atst_tools.external.ASE_interface.abacuslite.io.legacyio -v
          python -m unittest atst_tools.external.ASE_interface.abacuslite.io.latestio -v
          python -m unittest atst_tools.external.ASE_interface.abacuslite.utils.ksampling -v
```

- [ ] **Step 4: Run workflow governance tests**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_abacuslite_ci.py tests/unit/test_abacuslite_snapshot_ci.py -q
```

Expected: PASS.

- [ ] **Step 5: Run local abacuslite CI equivalent**

Run:

```bash
conda run -n atst-dev python scripts/check_abacuslite_snapshot.py \
  --upstream temp_repos/abacus-develop/interfaces/ASE_interface \
  --vendored src/atst_tools/external/ASE_interface
conda run -n atst-dev pytest \
  tests/unit/test_abacuslite_profile.py \
  tests/unit/test_abacus_io.py \
  tests/unit/test_abacuslite_io_reorder.py \
  tests/unit/test_abacuslite_snapshot_ci.py \
  tests/unit/test_abacuslite_ci.py \
  -q
conda run -n atst-dev python -m unittest atst_tools.external.ASE_interface.abacuslite.io.generalio atst_tools.external.ASE_interface.abacuslite.io.legacyio atst_tools.external.ASE_interface.abacuslite.io.latestio atst_tools.external.ASE_interface.abacuslite.utils.ksampling -v
```

Expected: all commands PASS.

- [ ] **Step 6: Commit the abacuslite CI wiring**

Run:

```bash
git add .github/workflows/abacuslite-ase-interface.yml tests/unit/test_abacuslite_ci.py
git commit -m "ci: check abacuslite snapshot drift"
```

### Task 4: Add General Pull Request Test CI

**Files:**
- Create: `.github/workflows/tests.yml`
- Create: `tests/unit/test_ci_workflows.py`

- [ ] **Step 1: Write failing workflow governance test**

Create `tests/unit/test_ci_workflows.py` with:

```python
"""Governance tests for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERAL_TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_general_pr_ci_workflow_runs_full_pytest_suite():
    """General PR CI should run the full unit test suite on Python 3.10."""
    workflow = GENERAL_TESTS_WORKFLOW.read_text(encoding="utf-8")

    assert "name: Tests" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'python-version: "3.10"' in workflow
    assert 'python -m pip install -e ".[test]"' in workflow
    assert "python -m pytest tests -q" in workflow
```

- [ ] **Step 2: Run workflow governance test to verify it fails**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_ci_workflows.py -q
```

Expected: FAIL with `FileNotFoundError` because `.github/workflows/tests.yml` does not exist.

- [ ] **Step 3: Add general PR CI workflow**

Create `.github/workflows/tests.yml` with:

```yaml
name: Tests

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

defaults:
  run:
    shell: bash

jobs:
  unit:
    name: unit tests
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install ATST-Tools test environment
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[test]"

      - name: Run unit tests
        run: |
          python -m pytest tests -q
```

- [ ] **Step 4: Run workflow governance test**

Run:

```bash
conda run -n atst-dev pytest tests/unit/test_ci_workflows.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Run the same test command used by general CI**

Run:

```bash
conda run -n atst-dev pytest tests -q
```

Expected: PASS for the full suite.

- [ ] **Step 6: Commit general CI workflow**

Run:

```bash
git add .github/workflows/tests.yml tests/unit/test_ci_workflows.py
git commit -m "ci: run full tests on pull requests"
```

### Task 5: Update Developer and User Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/developer/HANDOVER.md:48-58`
- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md:24-42`

- [ ] **Step 1: Update README validation section**

In `README.md`, in the validation section after the unit test coverage explanation, add:

```markdown
Pull requests run the maintained unit suite through `.github/workflows/tests.yml`.
Changes touching the vendored ABACUS ASE interface also run
`.github/workflows/abacuslite-ase-interface.yml`, which checks ATST regression
tests, package-mode abacuslite unittests, and snapshot drift against the pinned
`deepmodeling/abacus-develop` ASE interface reference.
```

- [ ] **Step 2: Update backend handover checklist**

In `docs/developer/HANDOVER.md`, replace the existing abacuslite vendored ASE interface bullet in section 5 with:

```markdown
- `abacuslite` vendored ASE interface 变更需同步运行
  `.github/workflows/abacuslite-ase-interface.yml` 覆盖的 pytest 回归测试、
  package-mode upstream-style parser tests 和 snapshot drift check；不要直接使用
  上游 `xtest.sh`，因为 ATST vendored copy 使用包内相对导入，直接脚本模式会
  绕过包上下文。
- 同步 `temp_repos/abacus-develop/interfaces/ASE_interface` 时，先运行
  `conda run -n atst-dev python scripts/check_abacuslite_snapshot.py --upstream temp_repos/abacus-develop/interfaces/ASE_interface --vendored src/atst_tools/external/ASE_interface`。
  若上游 reference commit 更新，同步更新
  `.github/workflows/abacuslite-ase-interface.yml` 的 `ABACUS_DEVELOP_REF`。
```

- [ ] **Step 3: Update ABACUSLite wrapper guide**

In `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`, update the date and tested fixes paragraph under "Tested Vendored Backend Fixes" to:

```markdown
As of 2026-07-05, the vendored snapshot intentionally preserves these local
differences from `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite`:

- Relative imports so the package works under `atst_tools.external`.
- First-occurrence species grouping for generated STRU files.
- ASE `FixAtoms` and `FixCartesian` constraints written as ABACUS mobility flags.
- Tolerant legacy ABACUS band-row parsing.

The vendored snapshot also carries tested upstream-sync fixes for numbered
backup rotation, property-derived ABACUS keyword conflict detection,
unsupported TDDFT `dipole` de-advertising, and `read_abacus_out` calculator
`magmoms` reordering when atoms are sorted during result parsing. The dedicated
abacuslite CI compares implementation files against a pinned
`deepmodeling/abacus-develop` ASE interface checkout after normalizing ATST's
package-layout differences.
```

- [ ] **Step 4: Run docs checks**

Run:

```bash
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
```

Expected: `git diff --check` exits 0. The conflict-marker scan prints no matches; `rg` may exit 1 when no matches are found.

- [ ] **Step 5: Commit documentation**

Run:

```bash
git add README.md docs/developer/HANDOVER.md docs/user/ABACUSLITE_WRAPPER_GUIDE.md
git commit -m "docs: document CI and abacuslite drift checks"
```

### Task 6: Final Verification

**Files:**
- Verify: `scripts/check_abacuslite_snapshot.py`
- Verify: `.github/workflows/abacuslite-ase-interface.yml`
- Verify: `.github/workflows/tests.yml`
- Verify: `tests/unit/test_abacuslite_io_reorder.py`
- Verify: `tests/unit/test_abacuslite_snapshot_ci.py`
- Verify: `tests/unit/test_abacuslite_ci.py`
- Verify: `tests/unit/test_ci_workflows.py`
- Verify: docs changed in Task 5

- [ ] **Step 1: Run all new and touched unit tests**

Run:

```bash
conda run -n atst-dev pytest \
  tests/unit/test_abacuslite_io_reorder.py \
  tests/unit/test_abacuslite_snapshot_ci.py \
  tests/unit/test_abacuslite_ci.py \
  tests/unit/test_ci_workflows.py \
  tests/unit/test_abacuslite_profile.py \
  tests/unit/test_abacus_io.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run vendored package-mode unittest coverage**

Run:

```bash
conda run -n atst-dev python -m unittest atst_tools.external.ASE_interface.abacuslite.io.generalio atst_tools.external.ASE_interface.abacuslite.io.legacyio atst_tools.external.ASE_interface.abacuslite.io.latestio atst_tools.external.ASE_interface.abacuslite.utils.ksampling -v
```

Expected: PASS with the existing skipped pseudo/orbital loader tests.

- [ ] **Step 3: Run local snapshot drift check**

Run:

```bash
conda run -n atst-dev python scripts/check_abacuslite_snapshot.py \
  --upstream temp_repos/abacus-develop/interfaces/ASE_interface \
  --vendored src/atst_tools/external/ASE_interface
```

Expected: PASS with no output.

- [ ] **Step 4: Run the general CI command locally**

Run:

```bash
conda run -n atst-dev pytest tests -q
```

Expected: PASS for the full test suite.

- [ ] **Step 5: Run docs and conflict checks**

Run:

```bash
git diff --check -- README.md docs examples/README.md AGENTS.md src tests scripts .github
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md src tests scripts .github
```

Expected: `git diff --check` exits 0. The conflict-marker scan prints no matches; `rg` may exit 1 when no matches are found.

- [ ] **Step 6: Review changed files**

Run:

```bash
git status --short
git diff --stat HEAD
git diff HEAD -- .github/workflows/abacuslite-ase-interface.yml .github/workflows/tests.yml scripts/check_abacuslite_snapshot.py tests/unit/test_abacuslite_io_reorder.py tests/unit/test_abacuslite_snapshot_ci.py tests/unit/test_abacuslite_ci.py tests/unit/test_ci_workflows.py src/atst_tools/external/ASE_interface/abacuslite/io/latestio.py src/atst_tools/external/ASE_interface/abacuslite/io/legacyio.py README.md docs/developer/HANDOVER.md docs/user/ABACUSLITE_WRAPPER_GUIDE.md
```

Expected: only CI, tests, the two abacuslite reader sync lines, and docs changed.

## Self-Review Result

- Spec coverage: The plan fixes the confirmed abacuslite backend drift, adds regression coverage, adds a pinned upstream snapshot drift check to abacuslite CI, adds general PR test CI, and documents the new development workflow.
- Placeholder scan: No unresolved implementation placeholders are present.
- Type consistency: The snapshot checker exposes `compare_snapshots(upstream: Path, vendored: Path) -> int`, and tests/imports use that name consistently.
- Scope check: This is one cohesive CI/test-development effort. The backend code change is limited to the upstream-sync lines required for the new regression test.
