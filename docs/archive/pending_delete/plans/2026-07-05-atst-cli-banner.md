# ATST CLI Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an ATST ASCII-art banner that credits core developer @QuantumMisaka and named contributors @Jerry and @MoseyQAQ without polluting workflow, JSON, YAML, or version command output.

**Architecture:** Keep the banner as a small, dependency-free utility under `src/atst_tools/utils/` so it can be rendered by CLI code without importing workflow calculators. Expose it through a new lightweight `atst banner` subcommand and include it in top-level `atst --help`; keep `atst run`, post/summary/config commands, and `atst --version` machine-readable. Document the new command in the maintained CLI user paths.

**Tech Stack:** Python 3.10+, argparse, pytest, ATST-Tools CLI/docs governance.

---

## Current Context

- Console script entry point: `pyproject.toml` exposes `atst = "atst_tools.scripts.cli:main"`.
- Unified CLI implementation: `src/atst_tools/scripts/cli.py`.
- Legacy workflow-only CLI module: `src/atst_tools/scripts/main.py`; do not add the banner there unless future work intentionally changes the legacy internal entry point.
- Existing CLI tests: `tests/unit/test_cli.py`.
- User-facing CLI docs: `docs/user/CLI_REFERENCE.md`, `README.md`, and `docs/skills/atst-cli/SKILL.md`.
- Governance note: this is a CLI behavior change, so update CLI docs and add focused CLI tests. It does not change YAML schema, examples, calculators, or workflow support status.

## Design Decisions

- The banner text is ASCII-only to match repository editing defaults.
- `atst banner` prints only the banner and credits, ending with one newline.
- `atst --help` shows the banner above the command overview so users see it naturally.
- `atst --version` remains exactly `atst <version>` because an existing test asserts this and package managers/scripts commonly parse version output.
- Workflow and post-processing commands do not print the banner by default because they may be used in Slurm logs, JSON/YAML pipelines, or lightweight command output checks.

## File Structure

- Create: `src/atst_tools/utils/banner.py`
  - Responsibility: hold the ATST ASCII art, contributor credit lines, and a `render_banner()` function.
  - Dependencies: standard library only.

- Create: `tests/unit/test_banner.py`
  - Responsibility: unit-test banner rendering independently from argparse.

- Modify: `src/atst_tools/scripts/cli.py:1-25`
  - Responsibility: import `render_banner`.

- Modify: `src/atst_tools/scripts/cli.py:760-789`
  - Responsibility: include banner in top-level parser description, add `atst banner` subcommand, and add a help example.

- Modify: `src/atst_tools/scripts/cli.py:791-795`
  - Responsibility: keep command dispatch unchanged through `args.func(args)`.

- Modify: `tests/unit/test_cli.py:40-70`
  - Responsibility: preserve version-output behavior and add focused banner CLI assertions.

- Modify: `README.md:120-153`
  - Responsibility: add `atst banner` to the quick-start command list.

- Modify: `docs/user/CLI_REFERENCE.md:1-20`
  - Responsibility: document the project banner command and help behavior.

- Modify: `docs/skills/atst-cli/SKILL.md:12-55`
  - Responsibility: add the command to CLI first checks and lightweight command snippets.

## Implementation Tasks

### Task 1: Add a Dependency-Free Banner Renderer

**Files:**
- Create: `src/atst_tools/utils/banner.py`
- Create: `tests/unit/test_banner.py`

- [ ] **Step 1: Write the failing banner renderer test**

Create `tests/unit/test_banner.py` with:

```python
"""Tests for the ATST-Tools project banner."""

from atst_tools.utils.banner import ATST_ASCII, BANNER_CREDITS, render_banner


def test_render_banner_contains_ascii_atst_and_contributor_credits():
    """The banner should include the ATST art and governed credit lines."""
    banner = render_banner()

    assert ATST_ASCII in banner
    assert BANNER_CREDITS in banner
    assert "Core developer: @QuantumMisaka" in banner
    assert "Contributors: @Jerry, @MoseyQAQ, and the ATST-Tools contributors" in banner
    assert banner.endswith("\n")
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_banner.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'atst_tools.utils.banner'`.

- [ ] **Step 3: Add the banner renderer**

Create `src/atst_tools/utils/banner.py` with:

```python
"""Project banner rendering for ATST-Tools."""

from __future__ import annotations

ATST_ASCII = r"""
    _  _____ ____ _____
   / \|_   _/ ___|_   _|
  / _ \ | | \___ \ | |
 / ___ \| |  ___) || |
/_/   \_\_| |____/ |_|
""".strip("\n")

BANNER_CREDITS = (
    "Core developer: @QuantumMisaka\n"
    "Contributors: @Jerry, @MoseyQAQ, and the ATST-Tools contributors"
)


def render_banner() -> str:
    """Return the ATST project banner.

    Returns:
        ASCII banner text with contributor credits and a trailing newline.
    """
    return f"{ATST_ASCII}\n{BANNER_CREDITS}\n"
```

- [ ] **Step 4: Run the banner renderer test to verify it passes**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_banner.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the renderer**

Run:

```bash
git add src/atst_tools/utils/banner.py tests/unit/test_banner.py
git commit -m "feat: add ATST banner renderer"
```

### Task 2: Wire the Banner Into the Unified CLI

**Files:**
- Modify: `src/atst_tools/scripts/cli.py:1-25`
- Modify: `src/atst_tools/scripts/cli.py:740-789`
- Modify: `tests/unit/test_cli.py:40-70`

- [ ] **Step 1: Write failing CLI banner tests**

Insert these tests in `tests/unit/test_cli.py` after `test_atst_version_uses_governed_package_version`:

```python
def test_atst_banner_prints_ascii_and_contributor_references(capsys):
    from atst_tools.scripts import cli
    from atst_tools.utils.banner import ATST_ASCII

    cli.main(["banner"])

    output = capsys.readouterr().out
    assert ATST_ASCII in output
    assert "Core developer: @QuantumMisaka" in output
    assert "Contributors: @Jerry, @MoseyQAQ, and the ATST-Tools contributors" in output


def test_atst_help_includes_banner_and_banner_command(capsys):
    from atst_tools.scripts import cli

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "Core developer: @QuantumMisaka" in output
    assert "atst banner" in output
    assert "Run a YAML-driven workflow" in output
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run:

```bash
env PYTHONPATH=src pytest \
  tests/unit/test_cli.py::test_atst_banner_prints_ascii_and_contributor_references \
  tests/unit/test_cli.py::test_atst_help_includes_banner_and_banner_command \
  -q
```

Expected: FAIL because `banner` is not a registered subcommand and top-level help does not include the banner.

- [ ] **Step 3: Import the renderer in the CLI**

Add this import in `src/atst_tools/scripts/cli.py` near the other `atst_tools` imports:

```python
from atst_tools.utils.banner import render_banner
```

- [ ] **Step 4: Add banner command helpers**

Insert these functions before `_add_run_parser` in `src/atst_tools/scripts/cli.py`:

```python
def _banner_command(args):
    """Print the ATST-Tools project banner."""
    print(render_banner(), end="")


def _add_banner_parser(subparsers):
    parser = subparsers.add_parser(
        "banner",
        help="Print the ATST-Tools banner and contributor credits",
        description=render_banner(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.set_defaults(func=_banner_command)
```

- [ ] **Step 5: Update the top-level parser**

Replace the current `build_parser()` description and epilog setup in `src/atst_tools/scripts/cli.py` with:

```python
def build_parser():
    parser = argparse.ArgumentParser(
        prog="atst",
        description=f"{render_banner()}\nATST-Tools: ASE workflows and lightweight helpers",
        epilog=dedent(
            """\
            Examples:
              atst banner
              atst run config.yaml
              atst config validate config.yaml --print-normalized
              atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
              atst neb post neb.traj --n-max 5 --vib-analysis
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {run_cli._package_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_banner_parser(subparsers)
    _add_run_parser(subparsers)
    _add_config_parser(subparsers)
    _add_abacus_parser(subparsers)
    _add_neb_parser(subparsers)
    _add_dimer_parser(subparsers)
    _add_relax_parser(subparsers)
    _add_vibration_parser(subparsers)
    _add_single_ended_summary_parser(subparsers, "sella")
    _add_single_ended_summary_parser(subparsers, "ccqn")
    _add_d2s_parser(subparsers)
    _add_md_parser(subparsers)
    _add_traj_parser(subparsers)
    return parser
```

- [ ] **Step 6: Run targeted CLI tests**

Run:

```bash
env PYTHONPATH=src pytest \
  tests/unit/test_cli.py::test_atst_version_uses_governed_package_version \
  tests/unit/test_cli.py::test_atst_banner_prints_ascii_and_contributor_references \
  tests/unit/test_cli.py::test_atst_help_includes_banner_and_banner_command \
  -q
```

Expected: PASS with `3 passed`. The version test proves `atst --version` remains unpolluted.

- [ ] **Step 7: Run the full CLI test file**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_cli.py -q
```

Expected: PASS for the full file.

- [ ] **Step 8: Commit the CLI wiring**

Run:

```bash
git add src/atst_tools/scripts/cli.py tests/unit/test_cli.py
git commit -m "feat: expose ATST banner in CLI"
```

### Task 3: Update Maintained CLI Documentation

**Files:**
- Modify: `README.md:120-153`
- Modify: `docs/user/CLI_REFERENCE.md:1-20`
- Modify: `docs/skills/atst-cli/SKILL.md:12-55`

- [ ] **Step 1: Update README quick-start commands**

In `README.md`, after the "List available workflow types" block, add:

```markdown
Print the project banner and contributor credits:

```bash
atst banner
```
```

- [ ] **Step 2: Update the CLI reference**

In `docs/user/CLI_REFERENCE.md`, after the opening paragraph, add:

```markdown
## Project Banner

```bash
atst banner
atst --help
```

`atst banner` prints the ATST ASCII-art banner and contributor credits for
@QuantumMisaka, @Jerry, @MoseyQAQ, and the wider ATST-Tools contributor
community. `atst --help` shows the same banner above the command overview.
Workflow, post-processing, JSON, YAML, and `--version` outputs remain
machine-readable and do not print the banner by default.
```

- [ ] **Step 3: Update the maintained atst-cli skill**

In `docs/skills/atst-cli/SKILL.md`, update the "First Checks" command block to:

```bash
git branch --show-current
git status --short
atst --version
atst banner
atst --help
```

In the "Lightweight Commands" command block, add this line at the top:

```bash
atst banner
```

- [ ] **Step 4: Check docs formatting and conflict markers**

Run:

```bash
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
```

Expected: both commands exit 0 and print no conflict markers.

- [ ] **Step 5: Commit docs**

Run:

```bash
git add README.md docs/user/CLI_REFERENCE.md docs/skills/atst-cli/SKILL.md
git commit -m "docs: document ATST banner command"
```

### Task 4: Final Verification

**Files:**
- Verify: `src/atst_tools/utils/banner.py`
- Verify: `src/atst_tools/scripts/cli.py`
- Verify: `tests/unit/test_banner.py`
- Verify: `tests/unit/test_cli.py`
- Verify: `README.md`
- Verify: `docs/user/CLI_REFERENCE.md`
- Verify: `docs/skills/atst-cli/SKILL.md`

- [ ] **Step 1: Run banner and CLI unit tests**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_banner.py tests/unit/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Run package metadata smoke for console script safety**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_package_metadata.py::test_optional_dependency_groups_cover_feature_specific_stacks -q
```

Expected: PASS. This confirms the banner feature did not add new runtime dependencies or extras.

- [ ] **Step 3: Manually inspect CLI output boundaries**

Run:

```bash
env PYTHONPATH=src python -m atst_tools.scripts.cli banner
env PYTHONPATH=src python -m atst_tools.scripts.cli --help
env PYTHONPATH=src python -m atst_tools.scripts.cli --version
```

Expected:

```text
atst --version output remains exactly one line like: atst 2.1.3
atst banner output includes: Core developer: @QuantumMisaka
atst --help output includes: atst banner
```

- [ ] **Step 4: Run final whitespace and conflict-marker checks**

Run:

```bash
git diff --check -- README.md docs examples/README.md AGENTS.md src tests
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md src tests
```

Expected: both commands exit 0 and print no conflict markers.

- [ ] **Step 5: Review changed files**

Run:

```bash
git status --short
git diff --stat HEAD
git diff HEAD -- README.md docs/user/CLI_REFERENCE.md docs/skills/atst-cli/SKILL.md src/atst_tools/utils/banner.py src/atst_tools/scripts/cli.py tests/unit/test_banner.py tests/unit/test_cli.py
```

Expected: only banner-related code, tests, and documentation are changed.

## Self-Review Result

- Spec coverage: The plan adds an ASCII-art ATST banner, credits @QuantumMisaka, credits @Jerry and @MoseyQAQ, includes the broader contributor community, and exposes the banner through maintained CLI user paths.
- Placeholder scan: No unresolved implementation placeholders are present.
- Type consistency: The only new public helper is `render_banner() -> str`; CLI tests and docs use the same `atst banner` command name.
- Scope check: This is one focused CLI/documentation change. It does not require YAML schema generation, examples, Slurm validation, or report-led feature status updates.
