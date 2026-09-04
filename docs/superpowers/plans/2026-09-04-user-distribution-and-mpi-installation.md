# ATST-Tools User Distribution and MPI Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the same README reliably route GitHub, Gitee, and PyPI users to portable ATST documentation while keeping serial installation free of mpi4py and making image-parallel MPI setup diagnosable on arbitrary sites.

**Spec:** `docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html` (§requirements R1-R9, §decisions, §architecture, §errors, §testing)

**Architecture:** Keep repository Markdown as the sole content source. The same README identifies GitHub as the collaboration authority, Gitee as the maintainer-synchronized read-only mirror, and PyPI as package distribution; its top-level absolute links work when PyPI cannot resolve relative paths. Keep a single `atst-tools` distribution: serial behavior stays in the base package, and only an externally launched image-parallel run needs the existing `parallel` extra and a site-compatible mpi4py build.

**Tech Stack:** Python 3.10+, setuptools extras, pytest, Markdown/HTML documentation, ASE, mpi4py (optional).

## Global Constraints

- GitHub `QuantumMisaka/atst-tools` is the collaboration/authoritative repository; Gitee `jamesmisaka/atst-tools` is a maintainer-manually-pulled mirror with the same README—create no mirror-specific content, config, or automation (§decisions).
- PyPI remains the sole package publisher. Do not add a second distribution or make `mpi4py` a base dependency (§goals, R4-R6).
- User entrypoints stay site-neutral; retain SAI module/QOS/job evidence only in developer operations and reports (§requirements R7).
- Keep every public change additive and backward-compatible: no YAML, CLI, or API contract change (§rollout).
- Use `conda run -n atst-dev` for repository tests; never submit an external scheduler job in this plan.

---

## File Structure

| Path | Responsibility after implementation |
| --- | --- |
| `README.md` | Cross-channel first landing page; absolute GitHub/Gitee guide and example links; installation-profile matrix; collaboration/mirror boundary. |
| `docs/index.md` | Repository-local user/developer/project-manager navigation; points back to README distribution boundary without site instructions. |
| `docs/user/USER_GUIDE_CN.md` | Current release identity, correct source clone URL, portable serial/DP/image-parallel installation and preflight guidance. |
| `docs/user/CONFIG_REFERENCE.md` | Generic image-parallel launch semantics and site-MPI ownership boundary. |
| `docs/user/PYTHON_API_REFERENCE.md` | Clarifies that `[parallel]` is only for externally launched image-parallel workflows. |
| `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` | Generic mpi4py/site-MPI matching and recovery guidance for ABACUS users. |
| `examples/README.md` | Site-neutral learning paths; points users to the portable MPI guide rather than maintenance operations. |
| `AGENTS.md` | Calls SAI a maintainer validation environment, not a product prerequisite. |
| `docs/skills/atst-cli/SKILL.md` | Developer-only CLI instructions without obsolete main/v1.5 branch policy. |
| `docs/developer/HANDOVER.md` | Dependency-change checklist requires testing base and `parallel` installation boundaries. |
| `docs/releases/RELEASE_NOTES_2.2.3.md` | Corrects its Compatibility package-version typo. |
| `src/atst_tools/utils/mpi.py` | Emits a portable missing-mpi4py recovery diagnostic; does not name SAI or one ABACUS module. |
| `tests/unit/test_docs_governance.py` | Tests structural user-entrypoint, distribution URL, site-neutrality, and stale-fact contracts. |
| `tests/unit/test_mpi_parallel.py` | Tests the MPI-launcher missing-dependency diagnostic contract. |
| `tests/unit/test_package_metadata.py` | Protects base-vs-`parallel` dependency separation. |
| `docs/reports/DOCUMENTATION_STATUS_REPORT.md` | Registers this implementation plan and updates the new SPEC status after implementation. |

## Task 1: Cross-channel user landing and portable installation documentation

**Files:**
- Modify: `tests/unit/test_docs_governance.py:11-16, 108-132`
- Modify: `tests/unit/test_package_metadata.py:24-51`
- Modify: `README.md:1-110`
- Modify: `docs/index.md:1-33`
- Modify: `docs/user/USER_GUIDE_CN.md:1-105`
- Modify: `docs/user/CONFIG_REFERENCE.md:139-155`
- Modify: `docs/user/PYTHON_API_REFERENCE.md:29-34`
- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md:142-160`
- Modify: `examples/README.md:1-155`

**Test strategy:**
- Behavior boundary: a README rendered on PyPI exposes absolute user-guide and examples links to both `main` repositories, while a base install remains demonstrably free of the `mpi4py` dependency.
- Existing suite to extend: `tests/unit/test_docs_governance.py`, `tests/unit/test_package_metadata.py`.
- New test file justification: none; these files already own public-documentation boundaries and package dependency policy.
- Temporary probes: none.

**Interfaces:**
- Consumes: the approved repository identities and README policy from SPEC R1-R6.
- Produces: a portable documentation/installation contract consumed by Task 2 diagnostics and Task 3 governance documentation.

- [x] **Step 1: Write failing documentation and metadata contract tests**

  Add these constants and tests to `tests/unit/test_docs_governance.py`; use parsed Markdown targets rather than asserting the whole prose body:

  ```python
  CANONICAL_REPOSITORIES = {
      "GitHub": "https://github.com/QuantumMisaka/atst-tools",
      "Gitee": "https://gitee.com/jamesmisaka/atst-tools",
  }


  def _markdown_targets(text: str) -> set[str]:
      return {match.group(1).strip("<>") for match in MARKDOWN_LINK.finditer(text)}


  def test_readme_has_absolute_cross_channel_user_entrypoints():
      targets = _markdown_targets(Path("README.md").read_text(encoding="utf-8"))

      expected = {
          "https://github.com/QuantumMisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md",
          "https://gitee.com/jamesmisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md",
          "https://github.com/QuantumMisaka/atst-tools/tree/main/examples",
          "https://gitee.com/jamesmisaka/atst-tools/tree/main/examples",
      }
      assert expected <= targets


  def test_active_user_docs_use_current_repository_and_release_facts():
      texts = {
          path: (Path(path).read_text(encoding="utf-8"))
          for path in ("README.md", "docs/user/USER_GUIDE_CN.md")
      }

      assert all("https://github.com/QuantumMisaka/atst-tools.git" in text for text in texts.values())
      assert all("https://github.com/deepmodeling/atst-tools.git" not in text for text in texts.values())
      assert "当前 2.2.3 版本" in texts["docs/user/USER_GUIDE_CN.md"]
      assert "RELEASE_NOTES_2.2.3.md" in texts["docs/user/USER_GUIDE_CN.md"]
  ```

  Add this test to `tests/unit/test_package_metadata.py` immediately after `test_runtime_dependency_policy_is_explicit`:

  ```python
  def test_serial_install_keeps_mpi4py_outside_base_dependencies() -> None:
      """Only the explicit image-parallel extra may request mpi4py."""
      project = _project_metadata()

      assert all("mpi4py" not in dependency for dependency in project["dependencies"])
      assert project["optional-dependencies"]["parallel"] == ["mpi4py>=4.1.2"]
  ```

- [x] **Step 2: Run the focused tests to verify RED**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_docs_governance.py::test_readme_has_absolute_cross_channel_user_entrypoints \
    tests/unit/test_docs_governance.py::test_active_user_docs_use_current_repository_and_release_facts \
    -q
  ```

  Expected: FAIL because the current README has no Gitee absolute guide/example links, uses the obsolete source clone URL, and the Chinese guide still claims 2.2.1.

- [x] **Step 3: Implement the smallest coherent README and user-document update**

  At the top of `README.md`, after the badges and before the project paragraph, add one identical cross-channel navigation block:

  ```markdown
  > 用户文档与示例：
  > [GitHub 用户指南](https://github.com/QuantumMisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md)
  > · [Gitee 用户指南](https://gitee.com/jamesmisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md)
  > · [GitHub 示例](https://github.com/QuantumMisaka/atst-tools/tree/main/examples)
  > · [Gitee 示例](https://gitee.com/jamesmisaka/atst-tools/tree/main/examples)
  >
  > 协作与规范源在 GitHub；Gitee 是维护者从 GitHub 手动拉取的同内容只读镜像；PyPI 仅发布 Python 包。
  ```

  Replace the source clone block in both `README.md` and `docs/user/USER_GUIDE_CN.md` with:

  ```bash
  git clone https://github.com/QuantumMisaka/atst-tools.git
  cd atst-tools
  pip install .
  ```

  Directly after the default install command, replace the undifferentiated optional-extra list with a three-profile explanation:

  ```markdown
  - **Serial（默认）**：`pip install atst-tools`；不安装也不需要 `mpi4py`，可运行全部非 image-parallel 工作流和串行 NEB/AutoNEB。
  - **DP**：`pip install "atst-tools[dp]"`；仅 DeePMD-kit calculator 工作流需要。
  - **Image-parallel NEB/AutoNEB**：`pip install "atst-tools[parallel]"`；仅当通过外部 `mpirun`/`srun` 启动一个 Python rank 对应一个活动 image 时需要。
  ```

  In `docs/index.md`, add this site-neutral sentence at the end of its User Path introductory paragraph, before the numbered links:

  ```markdown
  从 PyPI 阅读 README 时，请使用 README 顶部的 GitHub/Gitee 绝对用户文档入口；仓库内浏览继续使用下列本地链接。
  ```

  In `USER_GUIDE_CN.md`, change the opening release reference from 2.2.1 to 2.2.3 and its release-note link to `RELEASE_NOTES_2.2.3.md`. Add the portable MPI preflight and recovery block after the three profiles:

  ```bash
  python -c "from mpi4py import MPI; print(MPI.Get_library_version())"
  mpiexec -n 2 python -c "from mpi4py import MPI; print(MPI.COMM_WORLD.Get_rank())"
  ```

  ```bash
  MPICC="$(command -v mpicc)" \
    python -m pip install --no-cache-dir --force-reinstall --no-binary=mpi4py mpi4py
  ```

  Follow the second block with this exact sentence: “仅在站点已加载与外层 launcher 和 ABACUS 一致的 MPI 实现后执行该重装；串行用户不需要安装 mpi4py。”

  In `CONFIG_REFERENCE.md`, append this paragraph immediately after the existing NEB outer/inner MPI distinction: “Image parallel 是可选能力；默认的单进程 NEB/AutoNEB 不导入 mpi4py。通过外部 MPI 启动前，先按用户指南完成 mpi4py import 与 two-rank launcher 预检；若 wheel 与站点 MPI 不兼容，应使用站点 `mpicc` 从源码重装 mpi4py。”

  In `PYTHON_API_REFERENCE.md`, replace the existing `[parallel]` installation comment with `# only for externally launched image-parallel NEB/AutoNEB; serial use does not install mpi4py` and add one following sentence explaining that an external host owns matching mpi4py to its MPI launcher.

  In `ABACUSLITE_WRAPPER_GUIDE.md`, replace any site-specific mpi4py build example with the exact generic recovery command above and state that the site’s ABACUS and outer launcher must use the same MPI implementation.

  In `examples/README.md`, replace the link sentence “For image-level MPI configuration and the maintained execution records, see the example validation operations guide” with a Markdown link whose label is `ABACUSLite wrapper guide`, whose target is `../docs/user/ABACUSLITE_WRAPPER_GUIDE.md`, followed by: “maintained execution records are maintainer evidence, not an example prerequisite.” Keep `mpirun` as a generic outer-launch example; do not introduce module, partition, QOS, SAI, or job text into user entrypoints.

- [x] **Step 4: Run focused tests to verify GREEN**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_docs_governance.py \
    tests/unit/test_package_metadata.py \
    -q
  ```

  Expected: PASS, including the new cross-channel URL, current-release, and serial-dependency tests.

- [x] **Step 5: Refactor the documentation test helpers and run the owning suite**

  Keep `_markdown_targets()` as the one parser helper for entry-link assertions; do not add prose-wide snapshot assertions. Re-run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_docs_governance.py \
    tests/unit/test_package_metadata.py \
    tests/unit/test_examples.py \
    -q
  ```

  Expected: PASS. The existing user-boundary test must still report no forbidden SAI/site-operation terms in all user entrypoints.

- [x] **Step 6: Commit the user-entrypoint change**

  ```bash
  git add README.md docs/index.md docs/user/USER_GUIDE_CN.md \
    docs/user/CONFIG_REFERENCE.md docs/user/PYTHON_API_REFERENCE.md \
    docs/user/ABACUSLITE_WRAPPER_GUIDE.md examples/README.md \
    tests/unit/test_docs_governance.py tests/unit/test_package_metadata.py
  git commit -m "docs: clarify distribution and MPI install profiles"
  ```

### Task 2: Make missing-mpi4py diagnostics portable and test it with RED-GREEN

**Files:**
- Modify: `tests/unit/test_mpi_parallel.py:71-85`
- Modify: `src/atst_tools/utils/mpi.py:27-45`

**Test strategy:**
- Behavior boundary: an MPI-launched process without mpi4py receives a clear generic recovery message that names the `parallel` extra and a site-compatible source-build path, but no SAI-specific runtime.
- Existing suite to extend: `tests/unit/test_mpi_parallel.py`.
- New test file justification: none; this suite owns `bootstrap_mpi_for_ase()` and its launcher behavior.
- Temporary probes: none.

**Interfaces:**
- Consumes: `bootstrap_mpi_for_ase()` in `atst_tools.utils.mpi`; Task 1's user-facing MPI terminology.
- Produces: unchanged `RuntimeError` exception type with a portable diagnostic string for API/CLI error wrapping.

- [x] **Step 1: Write the failing missing-mpi4py diagnostic test**

  Replace the broad `match="mpi4py"` assertion in `test_bootstrap_requires_mpi4py_under_mpi_launcher` with the following focused assertions after capturing `excinfo`:

  ```python
  message = str(excinfo.value)
  assert "atst-tools[parallel]" in message
  assert "site MPI implementation" in message
  assert "MPICC" in message
  assert "--no-binary=mpi4py" in message
  assert "SAI" not in message
  assert "LTS" not in message
  ```

- [x] **Step 2: Run the focused test to verify RED**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_mpi_parallel.py::test_bootstrap_requires_mpi4py_under_mpi_launcher \
    -q
  ```

  Expected: FAIL because the current message names an ABACUS LTS module and has no `atst-tools[parallel]` or site-MPI wording.

- [x] **Step 3: Replace the SAI-specific recovery message with a portable message**

  In the `except ImportError` block in `bootstrap_mpi_for_ase()`, retain `RuntimeError` and `from exc`, but replace the string with:

  ```python
  raise RuntimeError(
      "MPI-launched ATST-Tools image parallelism requires mpi4py. "
      'Install the optional dependency with `python -m pip install "atst-tools[parallel]"`. '
      "For a site-managed or vendor MPI stack, load the same site MPI implementation "
      "used by your launcher and ABACUS, then rebuild mpi4py with that compiler: "
      'MPICC="$(command -v mpicc)" python -m pip install '
      "--no-cache-dir --force-reinstall --no-binary=mpi4py mpi4py."
  ) from exc
  ```

  Do not import mpi4py earlier, change launcher detection, or add any fallback MPI implementation.

- [x] **Step 4: Run the focused test to verify GREEN**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_mpi_parallel.py::test_bootstrap_requires_mpi4py_under_mpi_launcher \
    -q
  ```

  Expected: PASS; the same test must still create an `ImportError` only under the mocked MPI launcher environment.

- [x] **Step 5: Run the MPI/API ownership suites after refactor**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_mpi_parallel.py \
    tests/unit/test_api.py \
    tests/integration/test_mpi_failure_sync.py \
    -q
  ```

  Expected: PASS, with real-launcher integration tests skipped unless `ATST_RUN_MPI_TESTS=1` is explicitly set.

- [x] **Step 6: Commit the MPI diagnostic change**

  ```bash
  git add src/atst_tools/utils/mpi.py tests/unit/test_mpi_parallel.py
  git commit -m "fix(mpi): document portable mpi4py recovery"
  ```

### Task 3: Reclassify maintenance-only SAI guidance, remove stale facts, and close governance

**Files:**
- Modify: `AGENTS.md:30-35, 61`
- Modify: `docs/skills/atst-cli/SKILL.md:10-18`
- Modify: `docs/developer/HANDOVER.md:68-94`
- Modify: `docs/releases/RELEASE_NOTES_2.2.3.md:62-68`
- Modify: `docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`
- Modify: `tests/unit/test_docs_governance.py`

**Test strategy:**
- Behavior boundary: maintainers can find SAI validation evidence without the user-facing contract inheriting it; all active release and branch facts are correct.
- Existing suite to extend: `tests/unit/test_docs_governance.py`.
- New test file justification: none; it owns user/maintainer documentation boundaries.
- Temporary probes: none.

**Interfaces:**
- Consumes: Task 1's user-boundary test and the completed portable installation content; SPEC R7-R9.
- Produces: governed metadata that marks the SPEC implemented and records the implementation plan, with no user-facing SAI expansion.

- [x] **Step 1: Write failing stale-fact and maintenance-boundary tests**

  Add this test to `tests/unit/test_docs_governance.py`:

  ```python
  def test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy():
      agents = Path("AGENTS.md").read_text(encoding="utf-8")
      cli_skill = Path("docs/skills/atst-cli/SKILL.md").read_text(encoding="utf-8")
      release_notes = Path("docs/releases/RELEASE_NOTES_2.2.3.md").read_text(encoding="utf-8")

      assert "维护验证环境" in agents
      assert "用户运行前提" not in agents
      assert "main is the v1.5.x legacy line" not in cli_skill
      assert "- Package version: `2.2.3`." in release_notes
  ```

- [x] **Step 2: Run the focused test to verify RED**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_docs_governance.py::test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy \
    -q
  ```

  Expected: FAIL because AGENTS currently calls the SAI paragraph “开发测试环境”, the CLI skill still calls main a v1.5 legacy line, and 2.2.3 release notes still state 2.3.0 in Compatibility.

- [x] **Step 3: Apply the minimum governance/documentation corrections**

  In `AGENTS.md`, rename the relevant heading to “维护验证环境（SAI）”; state that SAI details govern maintainer validation evidence and do not limit end-user sites. Replace “项目当前在开发并行NEB模块” with the current fact that image-level NEB/AutoNEB is supported and needs an MPI-compatible Python environment for real parallel validation.

  In `docs/skills/atst-cli/SKILL.md`, retain its developer-only `atst-dev` instruction but remove the two lines that prohibit main changes and label main as v1.5 legacy. In `HANDOVER.md` §6, add a dependency-maintenance bullet that base-install tests must remain mpi4py-free and that `parallel` users must verify a site-compatible MPI import/launcher before image-parallel validation.

  In `RELEASE_NOTES_2.2.3.md`, change exactly:

  ```markdown
  - Package version: `2.3.0`.
  ```

  to:

  ```markdown
  - Package version: `2.2.3`.
  ```

  After local verification, record the SPEC as “本地实施完成，待发布后外部渲染验证”; register this plan in the “Spec / Plan / Review 登记” table and keep the remaining external-render validation explicit in `DOCUMENTATION_STATUS_REPORT.md`.

- [x] **Step 4: Run focused tests to verify GREEN**

  Run:

  ```bash
  conda run -n atst-dev python -m pytest \
    tests/unit/test_docs_governance.py::test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy \
    tests/unit/test_docs_governance.py::test_user_entrypoints_exclude_maintainer_and_site_operations \
    -q
  ```

  Expected: PASS. SAI remains visible to maintainers but no new term enters the README, docs index, user guide, or examples learning map.

- [x] **Step 5: Run documentation and complete-suite verification**

  Run:

  ```bash
  git diff --check -- README.md docs examples/README.md AGENTS.md
  rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
  conda run -n atst-dev python scripts/check_docs_governance.py
  conda run -n atst-dev python -m pytest tests -q
  ```

  Expected: the first two commands have no output; governance prints `documentation governance checks passed`; pytest passes with only the existing opt-in MPI/toolbox skips.

- [ ] **Step 6: Inspect external render targets without changing them, then commit**

  Manually open the GitHub, Gitee, and PyPI README renderings. Confirm that GitHub and Gitee show the same README content, and that the PyPI absolute guide/example links point outside `pypi.org/project/atst-tools/`. Do not push, publish, or trigger mirror synchronization from this task.

  ```bash
  git add AGENTS.md docs/skills/atst-cli/SKILL.md docs/developer/HANDOVER.md \
    docs/releases/RELEASE_NOTES_2.2.3.md \
    docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html \
    docs/superpowers/plans/2026-09-04-user-distribution-and-mpi-installation.md \
    docs/reports/DOCUMENTATION_STATUS_REPORT.md tests/unit/test_docs_governance.py
  git commit -m "docs: complete distribution and MPI guidance"
  ```

## Plan Self-Review

### Spec coverage

- R1-R3 are implemented and tested in Task 1 through the shared README, exact repository links, and corrected source-clone facts.
- R4 and R6 are protected in Task 1's base-vs-extra metadata test and serial installation prose; no new distribution is introduced.
- R5 is implemented with Task 1's portable preflight and Task 2's runtime diagnostic, with a focused RED-GREEN test.
- R7 is preserved by Task 1's user-boundary suite and Task 3's maintenance-only label.
- R8 is handled by Task 1 (user-guide facts) and Task 3 (AGENTS, CLI skill, release note).
- R9 is covered by the added Markdown-target, stale-fact, package metadata, MPI diagnostic, docs-governance, and full-suite checks.
- The confirmed manual-mirror constraint is carried in the global constraints, Task 1 README block, and Task 3's no-push/no-sync manual inspection step.

### Placeholder and interface review

The plan has no unassigned paths, generic test instruction, temporary probe, or invented runtime interface. The only production interface touched is the existing `bootstrap_mpi_for_ase()` `RuntimeError`; its type and chaining remain unchanged. Tasks 2 and 3 consume the documents and behavior produced by Task 1 without new cross-task APIs.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-04-user-distribution-and-mpi-installation.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh worker per task with review between tasks.
2. **Inline Execution** — execute task-by-task in this session with checkpoints.

Choose one option after reviewing this plan.
