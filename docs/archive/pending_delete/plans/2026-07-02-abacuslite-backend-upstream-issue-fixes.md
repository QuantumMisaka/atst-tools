# AbacusLite Backend Upstream Issue Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the vendored ATST-Tools abacuslite ASE backend for the three open upstream ABACUS issues while preserving the local ATST-specific backend improvements that are not yet in upstream `abacus-develop`.

**Architecture:** Keep the vendored backend as a small, upstream-portable patch set under `src/atst_tools/external/ASE_interface/abacuslite`. Implement each upstream issue with a focused unit test first, then the smallest backend change. Do not change the current external-installed-`abacuslite`-first resolver policy in this patch; document that the tested fixes live in the vendored snapshot and must also be submitted upstream.

**Tech Stack:** Python 3.10+, ASE, pytest, vendored `abacuslite`, ATST-Tools docs governance.

---

**Implementation status:** Implemented on branch `abacuslite-upstream-issue-fixes`
by code/docs commits `5e4ed8c`, `5246872`, `8050086`, and `c2a390f`;
this plan artifact is committed separately. The active audit report is
authoritative for moving upstream state.

## Current Context

Upstream sources reviewed:

- `https://github.com/deepmodeling/abacus-develop/issues/7540`: `file_safe_backup()` can overwrite older `*.bak.N` files because it calculates the wrong index during rotation.
- `https://github.com/deepmodeling/abacus-develop/issues/7544`: `AbacusTemplate` advertises `dipole`, maps it to TDDFT keywords, then `write_input()` rejects non-`ksdft`, creating a guaranteed runtime failure for an advertised property.
- `https://github.com/deepmodeling/abacus-develop/issues/7546`: `get_property_keywords()` intends to detect contradictory property keyword requirements, but `param_cache_` is never updated.

Local comparison:

- Local vendored copy: `src/atst_tools/external/ASE_interface/abacuslite`.
- Upstream reference copy: `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite`.
- Local comparison is based on the temp checkout `33a7acdf4`; re-fetch
  remote `develop` before upstream PR work because upstream may keep moving.
- Only four abacuslite Python files differ: `core.py`, `io/generalio.py`, `io/latestio.py`, and `io/legacyio.py`.

ATST-Tools local improvements to preserve:

- Relative imports inside the vendored package so it works under `atst_tools.external.ASE_interface.abacuslite`.
- `write_stru()` and `AbacusTemplate.write_input()` preserve first-occurrence species order instead of forcing alphabetical order.
- `write_stru()` converts ASE `FixAtoms` and `FixCartesian` constraints into ABACUS STRU mobility flags.
- `legacyio.py` has a more tolerant band-energy parser for ABACUS logs with extra lines around band rows.

Baseline verification:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py -q
```

Expected baseline before implementation: `11 passed`.

Use `env PYTHONPATH=src` for local tests in this checkout. Without it, the active shell environment can import an installed `atst_tools` package from site-packages instead of this source tree.

## File Structure

- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py`
  - Responsibility: generic abacuslite I/O helpers, including safe file backup and STRU write/read helpers.
  - Preserve: `species_group_indices()` and `_constraint_mobility()`.
  - Change: replace `file_safe_backup()` rotation logic.

- Modify: `src/atst_tools/external/ASE_interface/abacuslite/core.py`
  - Responsibility: ASE `AbacusProfile`, `AbacusTemplate`, and `Abacus` calculator integration.
  - Preserve: relative imports and first-occurrence atom reordering.
  - Change: make property keyword conflict detection effective and remove the unsupported `dipole` property from the advertised ASE property contract.

- Modify: `tests/unit/test_abacuslite_profile.py`
  - Responsibility: focused ATST coverage for the vendored abacuslite backend and ATST profile adapter.
  - Change: add regression tests for backup rotation, property keyword conflicts, and the `dipole` contract.

- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`
  - Responsibility: user-facing boundary and behavior of the ATST abacuslite wrapper.
  - Change: document vendored fixes and the external-package caveat.

- Modify: `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md`
  - Responsibility: active abacuslite audit report.
  - Change: append the 2026-07-02 upstream issue review and current local-vs-upstream diff summary.

## Implementation Tasks

### Task 1: Fix Safe Backup Rotation for Issue 7540

**Files:**
- Modify: `tests/unit/test_abacuslite_profile.py:10-13`
- Modify: `tests/unit/test_abacuslite_profile.py:106`
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py:71-101`

- [ ] **Step 1: Write the failing backup rotation test**

Change the import in `tests/unit/test_abacuslite_profile.py` to include `file_safe_backup`:

```python
from atst_tools.external.ASE_interface.abacuslite.io.generalio import file_safe_backup, read_stru, write_stru
```

Insert this test before `test_write_stru_preserves_first_occurrence_species_order`:

```python
def test_file_safe_backup_rotates_existing_integer_backups_without_clobber(tmp_path):
    """Existing numbered backups should move up one slot before live file backup."""
    live = tmp_path / "STRU"
    backup0 = tmp_path / "STRU.bak.0"
    backup1 = tmp_path / "STRU.bak.1"
    non_integer_backup = tmp_path / "STRU.bak.note"

    live.write_text("live\n", encoding="utf-8")
    backup0.write_text("old-zero\n", encoding="utf-8")
    backup1.write_text("old-one\n", encoding="utf-8")
    non_integer_backup.write_text("keep-me\n", encoding="utf-8")

    file_safe_backup(live)

    assert not live.exists()
    assert backup0.read_text(encoding="utf-8") == "live\n"
    assert backup1.read_text(encoding="utf-8") == "old-zero\n"
    assert (tmp_path / "STRU.bak.2").read_text(encoding="utf-8") == "old-one\n"
    assert non_integer_backup.read_text(encoding="utf-8") == "keep-me\n"
```

- [ ] **Step 2: Run the new backup test and verify it fails**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_file_safe_backup_rotates_existing_integer_backups_without_clobber -q
```

Expected: FAIL because the current implementation does not create `STRU.bak.2` and clobbers the old `STRU.bak.0`.

- [ ] **Step 3: Replace `file_safe_backup()` with index-based rotation**

Replace `src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py:71-101` with:

```python
def file_safe_backup(fn: Path, suffix: str = 'bak'):
    '''for the case where there are already files with the same name,
    add a suffix to the file name, like `STRU.bak.0`. If there are
    already `STRU.bak.0`, rename the elder to `STRU.bak.1` and let
    the latest one be `STRU.bak.0`.

    Parameters
    ----------
    fn : Path
        The path to the file to backup. Note: it must be provided
        as the Path object so that its folder is accessible by this
        function.
    suffix : str, optional
        The suffix to add to the file name. Default is 'bak'
    '''
    assert isinstance(fn, Path)
    where = fn.parent
    prefix = f'{fn.name}.{suffix}.'
    indexed_backups = []

    for backup in where.glob(f'{fn.name}.{suffix}.*'):
        index_text = backup.name.removeprefix(prefix)
        try:
            backup_index = int(index_text)
        except ValueError:
            continue
        indexed_backups.append((backup_index, backup))

    for backup_index, backup in sorted(indexed_backups, key=lambda item: item[0], reverse=True):
        backup.rename(backup.parent / f'{fn.name}.{suffix}.{backup_index + 1}')

    if fn.exists():
        fn.rename(fn.parent / f'{fn.name}.{suffix}.0')
```

- [ ] **Step 4: Run the backup test and verify it passes**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_file_safe_backup_rotates_existing_integer_backups_without_clobber -q
```

Expected: PASS.

- [ ] **Step 5: Commit the backup fix**

Run:

```bash
git add src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py tests/unit/test_abacuslite_profile.py
git commit -m "fix: preserve abacuslite numbered backups"
```

### Task 2: Make Property Keyword Conflicts Effective for Issue 7546

**Files:**
- Modify: `tests/unit/test_abacuslite_profile.py:218`
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/core.py:193-230`

- [ ] **Step 1: Write failing tests for property-property and user-property conflicts**

Append these tests after `test_abacus_template_uses_first_occurrence_species_grouping` in `tests/unit/test_abacuslite_profile.py`:

```python
class _ConflictingKeywordTemplate(AbacusTemplate):
    implemented_properties = [*AbacusTemplate.implemented_properties, "mock_a", "mock_b"]

    @staticmethod
    def get_mock_a_keywords(parameters):
        return {"cal_force": "1"}

    @staticmethod
    def get_mock_b_keywords(parameters):
        return {"cal_force": "0"}


def test_property_keywords_raise_when_properties_disagree_on_same_keyword():
    """Two requested properties should not silently overwrite the same keyword."""
    template = _ConflictingKeywordTemplate()

    with pytest.raises(ValueError, match="cal_force=0"):
        template.get_property_keywords({"calculation": "scf"}, ["mock_a", "mock_b"])


def test_property_keywords_raise_when_property_overwrites_user_keyword():
    """Property-derived keywords should not silently overwrite explicit user input."""
    template = AbacusTemplate()

    with pytest.raises(ValueError, match="nspin=2"):
        template.get_property_keywords({"calculation": "scf", "nspin": "1"}, ["magmom"])


def test_property_keywords_accept_equivalent_user_keyword_values():
    """Equivalent int/string user keywords should not be false conflicts."""
    template = AbacusTemplate()

    parameters = template.get_property_keywords({"calculation": "scf", "nspin": 2}, ["magmom"])

    assert parameters["nspin"] == "2"
```

- [ ] **Step 2: Run the new conflict tests and verify they fail for the right reason**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_property_keywords_raise_when_properties_disagree_on_same_keyword tests/unit/test_abacuslite_profile.py::test_property_keywords_raise_when_property_overwrites_user_keyword -q
```

Expected: FAIL with `Failed: DID NOT RAISE <class 'ValueError'>`.

- [ ] **Step 3: Replace `get_property_keywords()` with cache-updating conflict checks**

Replace `src/atst_tools/external/ASE_interface/abacuslite/core.py:193-230` with:

```python
    def get_property_keywords(self,
                              parameters: Dict[str, str],
                              properties: List[str]) -> Dict[str, str]:
        '''Connect the relationship between the properties calculation and
        the ABACUS keywords. May be more complicated in the future, therefore
        it is better to have a seperate mapping function instead of
        implementing in some other functions.

        Parameters
        ----------
        parameters : dict
            The parameters used to perform the calculation.
        properties : list of str
            The list of properties to calculate
        '''
        def normalize_keyword_value(value):
            if isinstance(value, (list, tuple, set)):
                return ' '.join(str(i) for i in value)
            return str(value)

        param_cache_ = {
            key: normalize_keyword_value(value)
            for key, value in parameters.items()
            if value is not None
        }

        def counter(param_new: Dict[str, str]) -> Dict[str, str]:
            info = 'desired properties or explicit parameters required contradictory keywords'
            staged = {}
            for k, v in param_new.items():
                if v is None:
                    continue
                normalized_value = normalize_keyword_value(v)
                if k in param_cache_ and param_cache_[k] != normalized_value:
                    raise ValueError(f'{info}: {k}={v} (now), {param_cache_[k]} (before)')
                staged[k] = normalized_value
            param_cache_.update(staged)
            return param_new

        for p in properties:
            assert p in self.implemented_properties
            parameters.update(counter(getattr(self, f'get_{p}_keywords')(parameters)))

        self.suffix = parameters.get('suffix', 'ABACUS')
        self.calculation = parameters.get('calculation', 'scf')
        return parameters
```

- [ ] **Step 4: Run the conflict tests and verify they pass**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_property_keywords_raise_when_properties_disagree_on_same_keyword tests/unit/test_abacuslite_profile.py::test_property_keywords_raise_when_property_overwrites_user_keyword tests/unit/test_abacuslite_profile.py::test_property_keywords_accept_equivalent_user_keyword_values -q
```

Expected: PASS.

- [ ] **Step 5: Commit the conflict fix**

Run:

```bash
git add src/atst_tools/external/ASE_interface/abacuslite/core.py tests/unit/test_abacuslite_profile.py
git commit -m "fix: validate abacuslite property keyword conflicts"
```

### Task 3: Remove Unsupported Dipole Advertisement for Issue 7544

**Files:**
- Modify: `tests/unit/test_abacuslite_profile.py:250`
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/core.py:145-191`

Decision: remove `dipole` from `implemented_properties` until abacuslite has a real TDDFT write/read path. This is the conservative fix because the current backend rejects non-`ksdft` input and does not parse TDDFT dipole output. Adding TDDFT support should be a separate feature with ABACUS fixture outputs.

- [ ] **Step 1: Write failing tests for the unsupported dipole contract**

Append these tests after the property conflict tests in `tests/unit/test_abacuslite_profile.py`:

```python
def test_abacus_template_does_not_advertise_dipole_until_tddft_is_supported():
    """The ASE property list should not include a property the writer rejects."""
    assert "dipole" not in AbacusTemplate.implemented_properties


def test_abacus_template_rejects_dipole_property_keyword_request():
    """Direct keyword mapping should reject dipole after it is removed from support."""
    template = AbacusTemplate()

    with pytest.raises(AssertionError):
        template.get_property_keywords({"calculation": "scf"}, ["dipole"])
```

- [ ] **Step 2: Run the new dipole tests and verify they fail**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_abacus_template_does_not_advertise_dipole_until_tddft_is_supported tests/unit/test_abacuslite_profile.py::test_abacus_template_rejects_dipole_property_keyword_request -q
```

Expected: FAIL because `dipole` is currently advertised and `get_dipole_keywords()` currently accepts it.

- [ ] **Step 3: Remove `dipole` from the advertised property list**

Replace `src/atst_tools/external/ASE_interface/abacuslite/core.py:145-191` with:

```python
    implemented_properties = [
        'energy', 'forces', 'stress', 'free_energy', 'magmom'
    ]
    _label = 'abacus'

    def __init__(self):
        super().__init__(
            'abacus',
            self.implemented_properties
        )
        self.non_convergence_ok = False
        # the redirect stdout and stderr
        self.inputname  = 'INPUT' # hard-coded
        self.outputname = f'{self._label}.out'
        self.errorname  = f'{self._label}.err'

        # fix: inconsistent atoms order may induce bugs, here a list
        # is kept to swap the order of atoms
        self.atomorder  = None

    '''because it may be not one-to-one mapping between the property
    desired to calculate and the keywords used in the calculation,
    in the following a series of functions for mapping the property
    calculation to the keywords settings are implemented'''
    @staticmethod
    def get_energy_keywords(self) -> Dict[str, str]:
        return {}

    @staticmethod
    def get_forces_keywords(self) -> Dict[str, str]:
        return {'cal_force': '1'}

    @staticmethod
    def get_stress_keywords(self) -> Dict[str, str]:
        return {'cal_stress': '1'}

    @staticmethod
    def get_free_energy_keywords(self) -> Dict[str, str]:
        return {}

    @staticmethod
    def get_magmom_keywords(self) -> Dict[str, str]:
        return {'nspin': '2'}
```

- [ ] **Step 4: Run the dipole tests and verify they pass**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py::test_abacus_template_does_not_advertise_dipole_until_tddft_is_supported tests/unit/test_abacuslite_profile.py::test_abacus_template_rejects_dipole_property_keyword_request -q
```

Expected: PASS.

- [ ] **Step 5: Commit the dipole contract fix**

Run:

```bash
git add src/atst_tools/external/ASE_interface/abacuslite/core.py tests/unit/test_abacuslite_profile.py
git commit -m "fix: remove unsupported abacuslite dipole property"
```

### Task 4: Document the Vendored Backend Delta and Upstream Issue Fixes

**Files:**
- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md:22`
- Modify: `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md:104`

- [ ] **Step 1: Update the user wrapper guide**

Insert this section in `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` after the current integration-state paragraph ending with ``calculator.name: abacus``:

```markdown
## Tested Vendored Backend Fixes

ATST-Tools still resolves an independently installed `abacuslite` package before
the vendored fallback. The fixes below are tested in the vendored snapshot; an
external `abacuslite` package may differ until the same changes are released
upstream.

As of 2026-07-02, the vendored snapshot intentionally preserves these local
differences from `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite`:

- Relative imports so the package works under `atst_tools.external`.
- First-occurrence species grouping for generated STRU files.
- ASE `FixAtoms` and `FixCartesian` constraints written as ABACUS mobility flags.
- Tolerant legacy ABACUS band-row parsing.

The vendored snapshot also fixes three upstream issue paths: numbered backup
rotation preserves older backups, property-derived ABACUS keyword conflicts now
raise `ValueError`, and the unsupported TDDFT `dipole` ASE property is no longer
advertised until abacuslite has a complete TDDFT input and output path.
```

- [ ] **Step 2: Update the active abacuslite audit report**

Insert this section in `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md` immediately before `## 结论`:

```markdown
## 2026-07-02 上游 issue 复查

本次代码对比基于本地 `temp_repos/abacus-develop` 的 `develop`
checkout `33a7acdf4`；远端 `develop` 可能继续演进，后续向
`abacus-develop` 提交 PR 前需要重新 fetch/rebase 并复核
`ASE_interface` 差异。当前 vendored abacuslite 与该上游参考实现仍只有四个
Python 文件存在差异：`core.py`、`io/generalio.py`、`io/latestio.py` 和
`io/legacyio.py`。

已确认的 ATST-Tools 本地保留差异包括：

- vendored 包内使用相对导入，避免在 `atst_tools.external` 命名空间下误导入外部包。
- STRU writer 和 calculator template 按 ASE `Atoms` 中元素首次出现顺序分组，而不是按字母顺序排序。
- STRU writer 将 ASE `FixAtoms` / `FixCartesian` 转写为 ABACUS mobility flags。
- legacy 输出 reader 对 band energy / occupation 表有更宽容的行解析。

本次已在 vendored snapshot 中修复并由单元测试覆盖的上游 issue 是：

- `https://github.com/deepmodeling/abacus-develop/issues/7540`：
  `file_safe_backup()` 应按真实整数后缀倒序轮转，避免覆盖旧备份。
- `https://github.com/deepmodeling/abacus-develop/issues/7544`：
  在 TDDFT 写入和 dipole 输出读取完整支持前，不再向 ASE 宣称支持 `dipole`。
- `https://github.com/deepmodeling/abacus-develop/issues/7546`：
  `get_property_keywords()` 应同时检查 property-property 冲突和 property 覆盖用户显式关键词的冲突。

该修复集保持 ATST-Tools 当前边界：运行环境解析、MPI command 和 version probe
策略仍由 `ATSTAbacusProfile` / `AbacusFactory` 管理；vendored abacuslite
只承担 ASE calculator 与 ABACUS 输入输出转换。后续向 `abacus-develop` 提交
PR 时，需要把相同功能改动移植到上游绝对导入布局中，不应携带 ATST-Tools
命名空间相关改动。
```

- [ ] **Step 3: Run documentation checks**

Run:

```bash
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
```

Expected: both commands exit 0 and print no conflict markers.

- [ ] **Step 4: Commit the documentation update**

Run:

```bash
git add docs/user/ABACUSLITE_WRAPPER_GUIDE.md docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md
git commit -m "docs: record abacuslite upstream issue fixes"
```

### Task 5: Final Verification and Upstream-Port Readiness Check

**Files:**
- Verify: `src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py`
- Verify: `src/atst_tools/external/ASE_interface/abacuslite/core.py`
- Verify: `tests/unit/test_abacuslite_profile.py`
- Verify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`
- Verify: `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md`

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_abacuslite_profile.py tests/unit/test_abacus_io.py -q
```

Expected: PASS. `test_abacuslite_profile.py` should include backup rotation, conflict detection, dipole contract, first-occurrence species order, constraint mobility, and ATST version-probe coverage.

- [ ] **Step 2: Run calculator factory regression tests**

Run:

```bash
env PYTHONPATH=src pytest tests/unit/test_factory.py -q
```

Expected: PASS. This checks that the ATST `AbacusFactory` still creates calculators through the current backend resolver and profile adapter.

- [ ] **Step 3: Confirm the property contract from Python**

Run:

```bash
env PYTHONPATH=src python -c "from atst_tools.external.ASE_interface.abacuslite.core import AbacusTemplate; print(AbacusTemplate.implemented_properties)"
```

Expected output:

```text
['energy', 'forces', 'stress', 'free_energy', 'magmom']
```

- [ ] **Step 4: Run diff hygiene checks**

Run:

```bash
git diff --check -- src tests docs
rg -n "^<<<<<<<|^=======|^>>>>>>>" src tests docs
```

Expected: both commands exit 0 and print no conflict markers.

- [ ] **Step 5: Review the final diff for accidental loss of ATST local improvements**

Run:

```bash
git diff -- src/atst_tools/external/ASE_interface/abacuslite tests/unit/test_abacuslite_profile.py docs/user/ABACUSLITE_WRAPPER_GUIDE.md docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md
```

Expected review points:

- `species_group_indices()` remains present.
- `_constraint_mobility()` remains present.
- Relative imports in vendored `core.py` and `latestio.py` remain relative.
- The tolerant `legacyio.py` band parser remains unchanged.
- `file_safe_backup()` rotates integer backups by parsed index.
- `get_property_keywords()` updates its conflict cache and checks explicit user keywords.
- `AbacusTemplate.implemented_properties` no longer contains `dipole`.

- [ ] **Step 6: Commit final verification notes if any tracked file changed during review**

If the review step required a small correction, run:

```bash
git add src tests docs
git commit -m "test: verify abacuslite backend issue fixes"
```

If the review step required no corrections, do not create an empty commit.

## Self-Review

Spec coverage:

- Local vs upstream comparison is captured in the context and documentation tasks.
- Issue 7540 is covered by Task 1.
- Issue 7544 is covered by Task 3.
- Issue 7546 is covered by Task 2.
- ATST internal needs are protected by existing and new focused unit tests for species order, constraints, factory behavior, and profile behavior.
- Upstream PR readiness is covered by the documentation note that functional changes must be ported without ATST namespace import changes.

Placeholder scan:

- No task relies on unspecified code or deferred behavior.
- Every code-changing step includes the exact test or replacement code.
- Every verification step includes exact commands and expected outcomes.

Type consistency:

- Tests use the existing `AbacusTemplate`, `AbacusProfile`, `write_stru`, `read_stru`, and pytest imports.
- Synthetic property tests use `get_mock_a_keywords()` and `get_mock_b_keywords()` names that match `get_property_keywords()` lookup rules.
- Keyword normalization uses built-in `list`, `tuple`, and `set`, matching runtime `isinstance()` semantics.
