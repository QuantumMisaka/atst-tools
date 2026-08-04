# abacuslite 力读取一致性与跨仓维护 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 vendored abacuslite 力读取一致性问题（sella 2 步停根因），并建立"本仓为主 + 收敛后上游同步 + 阶段性拉取"的跨仓维护纪律，解锁 CI drift gate。

**Spec:** `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design.html`（含 `#core` 直白说明、R1-R8、D1-D8、P1-P8 审查补强）

**审查参考:** `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design-review.md`（§4 目标规划；全部结论已落入 spec）

**Architecture:** 帧选择上提到唯一汇聚点 `AbacusTemplate.read_results`（core.py）：scf-only 时从 `read_abacus_out` 返回的全部帧中选取"坐标与本次落盘 STRU 一致的最后一帧"，无匹配即 fail-closed；不改 `read_abacus_out` 签名，一次覆盖 legacyio/latestio 双后端。跨仓维护以 `ABACUSLITE_SNAPSHOT.md`（基线三段史 + 单一事实源）+ `PATCHES.md`（语义补丁清单）+ checker 白名单归一化 + CI push 触发构成。

**Tech Stack:** Python 3.10+，ASE 3.28，pytest，GitHub Actions；测试环境 `conda run -n abacus-env env PYTHONPATH=$PWD/src pytest`。

## Global Constraints

- 测试禁绝对路径（ABACUS 项目红线）；golden 夹具只放 `src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/` 与 `tests/unit/`。
- 提交信息 `type(scope): 中文主题`（atst-tools 惯例，如 `fix(abacuslite):` / `test(abacuslite):` / `ci:` / `docs:`）；本计划不 bump 版本号（收敛后才考虑 2.2.x patch）。
- 不改 `read_abacus_out`（legacyio/latestio 两个实现）的公共签名；帧选择只在 `core.py::read_results`。
- 帧选择仅对 `calculation == 'scf'` 启用；原生 relax/md 与 MD_dump 路径保持 `[-1]` 旧语义（spec R2/P2）。
- 坐标比较：统一排列（物种分组序 vs atomorder revmap）、统一 Cartesian Å、**绝对 Å 容差**（按 running log 打印精度推导，如 1e-4；相对 1e-5 对分数坐标无意义，spec P3 ③）。
- 语义补丁必须登记进 `PATCHES.md` 并归一化；未登记新 drift 保持 checker exit 1（spec R3/P1）。
- 上游基线 SHA 单一事实源 = `ABACUSLITE_SNAPSHOT.md`（spec R4/P6）；efermi 与 band parser 是既有语义补丁（band parser 已由 checker 归一化；efermi 需本次登记）。
- 回归基线：现有 `tests/unit/` 下 abacuslite 相关 17 项全绿（`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit -q`）。
- 外部依赖任务（Phase 0 SAI 取证、Phase 3 上游 PR）在执行时若环境不可达，标记 BLOCKED/待授权，不阻塞本地任务推进。
- **验收（用户明确要求，2026-08-04）**：本计划以"重新打 SIF 镜像 + $sai-local-e2e 本地测试"为端到端验收（spec R8）。验收（Task 9）前置：工作树已对齐 abacus-develop 分支基线（Task 6）。

---

### Task 1: efermi 补丁登记 + 基线/补丁清单 + CI push 触发（Phase 2a，解锁 CI）

**Files:**
- Create: `src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md`
- Create: `src/atst_tools/external/ASE_interface/PATCHES.md`
- Modify: `scripts/check_abacuslite_snapshot.py`（新增 efermi 归一化）
- Modify: `.github/workflows/abacuslite-ase-interface.yml`（补 push 触发）
- Modify: `tests/unit/test_abacuslite_snapshot_ci.py`（覆盖登记/未登记两侧 + push 触发）

**Test strategy:**
- Behavior boundary: checker 对钉扎基线 70f7ed69 在 efermi 登记后 exit 0；未登记新 drift exit 1；workflow 含 `push: branches: [main]`。
- Existing suite to extend: `tests/unit/test_abacuslite_snapshot_ci.py`（workflow 内容断言）+ 新增 `tests/unit/test_checker_efermi_whitelist.py`（归一化行为）。
- Temporary probes: none。

**Interfaces:**
- Consumes: 既有 `scripts/check_abacuslite_snapshot.py` 的 `_normalize_documented_atst_adaptations(relative_path, source)` 钩子（spec 决策 D3 先例：band parser 块级归一化）。
- Produces: `ABACUSLITE_SNAPSHOT.md`（R4 三段史 + 基线 SHA `70f7ed69b5677c447afdc78e05240e93da660e66`）；`PATCHES.md`（efermi 块级登记，供 Task 5/6 引用）。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_checker_efermi_whitelist.py` 中新增：构造"仅 efermi 一处语义 diff"的 vendored 树，断言归一化后与上游一致：

```python
"""checker 对 efermi 语义补丁的登记行为（spec R3/P1）。"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_abacuslite_snapshot.py"


def _make_tree(root: Path, upstream: Path) -> None:
    """拷贝上游树到 root，仅注入 efermi 语义补丁（ener['E_Fermi'] -> ener.get('E_Fermi')）。"""
    for rel in ["abacuslite/io/legacyio.py", "abacuslite/io/latestio.py"]:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = (upstream / rel).read_text(encoding="utf-8")
        text = text.replace("efermi=ener['E_Fermi']", "efermi=ener.get('E_Fermi')")
        dst.write_text(text, encoding="utf-8")


def test_checker_exits_zero_when_only_documented_efermi_patch(tmp_path, monkeypatch):
    """登记后的语义补丁（efermi）不产生 drift；未登记的新改动仍 exit 1。"""
    import os

    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    shutil.copytree(ROOT / "src/atst_tools/external/ASE_interface", upstream)
    shutil.copytree(ROOT / "src/atst_tools/external/ASE_interface", vendored)
    _make_tree(vendored, upstream)

    env = dict(os.environ)
    monkeypatch.setattr(sys, "argv", [str(CHECKER)])
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_abacuslite_snapshot", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.compare_snapshots(upstream, vendored) == 0

    # 未登记的 drift（改一行注释之外的代码）应返回 1
    target = vendored / "abacuslite/io/legacyio.py"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("efermi=ener.get('E_Fermi')", "efermi=None"), encoding="utf-8")
    assert mod.compare_snapshots(upstream, vendored) == 1
```

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_checker_efermi_whitelist.py -v`
预期：FAIL（checker 尚无 efermi 归一化，第一个断言 exit=1）。

- [ ] **Step 2: 扩展 checker 归一化（efermi 白名单）**

在 `scripts/check_abacuslite_snapshot.py` 的 `_normalize_documented_atst_adaptations` 前新增：

```python
def _normalize_efermi_tolerance(relative_path: Path, source: str) -> str:
    """efermi 容错语义补丁（spec PATCHES.md 登记）：ener['E_Fermi'] -> ener.get('E_Fermi')。
    仅作用于 SinglePointDFTCalculator 构造行的 efermi 关键字，不改变其他语义。"""
    if relative_path not in {
        Path("abacuslite/io/legacyio.py"),
        Path("abacuslite/io/latestio.py"),
    }:
        return source
    return source.replace("efermi=ener['E_Fermi']", "efermi=ener.get('E_Fermi')")
```

并在 `_normalize_documented_atst_adaptations` 中先调用它：

```python
def _normalize_documented_atst_adaptations(relative_path: Path, source: str) -> str:
    source = _normalize_efermi_tolerance(relative_path, source)
    if relative_path == Path("abacuslite/io/legacyio.py"):
        return _normalize_legacy_band_parser_adaptation(source)
    return source
```

- [ ] **Step 3: 运行测试验证通过**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_checker_efermi_whitelist.py -v`
预期：PASS（两个断言都过）。

- [ ] **Step 4: 真实基线核对（对钉扎基线 exit 0）**

运行：`python3 scripts/check_abacuslite_snapshot.py --upstream <上游 70f7ed69 树> --vendored src/atst_tools/external/ASE_interface`
预期：exit 0（efermi 已归一化；band parser 既有归一化）。
注：上游 70f7ed69 树需临时 clone：`git clone --depth 1 --branch <70f7ed69> https://github.com/deepmodeling/abacus-develop /tmp/abacus-70f7ed69 && <checker> --upstream /tmp/abacus-70f7ed69/interfaces/ASE_interface --vendored ...`。

- [ ] **Step 5: 创建 ABACUSLITE_SNAPSHOT.md 与 PATCHES.md**

`src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md`：

```markdown
# abacuslite vendored 快照基线

- 快照引入：2026-05-10（atst-tools `881a926`）
- drift-check CI 引入：2026-07-06（`7a04854`）钉扎 `762919f6`（= #7588 PR head）
- 当前基线：上游 `70f7ed69b5677c447afdc78e05240e93da660e66`（2026-07-22 commit；2026-07-23 `b8556c7` 写入 CI）
- 同步状态（2026-08-04 核对）：对上游 develop tip 零上游侧欠账；仅 fork 侧 efermi 语义补丁（见 PATCHES.md）
- 差异摘要：以 `scripts/check_abacuslite_snapshot.py --upstream <基线树> --vendored ...` 输出为准

## 同步流程

阶段拉取（发布 patch / 支持新 ABACUS / 上游新加固）后：更新本文件基线 SHA + 差异摘要；CI `ABACUS_DEVELOP_REF` 从本文件解析（单一事实源）。
```

`src/atst_tools/external/ASE_interface/PATCHES.md`：

```markdown
# vendored abacuslite 语义补丁清单

与上游逐字节差异的**语义补丁**（非结构适配：相对导入/删内嵌测试/注释 churn 由 checker 机械归一化）。每条登记后由 `scripts/check_abacuslite_snapshot.py` 归一化。

| 文件 | 位置 | 补丁 | 登记日期 | 上游状态 |
| --- | --- | --- | --- | --- |
| `abacuslite/io/legacyio.py` | SinglePointDFTCalculator 构造 | `efermi=ener['E_Fermi']` → `ener.get('E_Fermi')`（running log 缺 E_Fermi 容错） | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/latestio.py` | 同上 | 同上 | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/legacyio.py` | band parser | 容差块（`_legacy_band_parser_tolerant_block`） | 2026-05-10 | 已由 #7588 上游化（checker 归一化保留至基线推进后清理） |
```

- [ ] **Step 6: CI workflow 补 push 触发（P1）**

`.github/workflows/abacuslite-ase-interface.yml` 的 `on:` 增加：

```yaml
  push:
    branches: [main]
```

保留既有 `pull_request`（paths 过滤）与 `workflow_dispatch`。

- [ ] **Step 7: 更新 test_abacuslite_snapshot_ci.py 断言 push 触发**

在 `tests/unit/test_abacuslite_snapshot_ci.py` 增加：

```python
def test_abacuslite_ci_triggers_on_main_push():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "abacuslite-ase-interface.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "push:" in text and "branches: [main]" in text
```

- [ ] **Step 8: 运行 Task 1 全量测试并提交**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_checker_efermi_whitelist.py tests/unit/test_abacuslite_snapshot_ci.py tests/unit/test_abacuslite_ci.py -q`
预期：全 PASS。

```bash
git add scripts/check_abacuslite_snapshot.py .github/workflows/abacuslite-ase-interface.yml \
  src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md \
  src/atst_tools/external/ASE_interface/PATCHES.md \
  tests/unit/test_checker_efermi_whitelist.py tests/unit/test_abacuslite_snapshot_ci.py
git commit -m "fix(abacuslite)+ci: efermi 语义补丁登记与 checker 归一化（解锁 CI drift gate）；基线/补丁清单落盘（ABACUSLITE_SNAPSHOT/PATCHES）；workflow 补 main push 触发"
```

---

### Task 2: 多帧 golden 用例（RED，力读取帧选择）

**Files:**
- Create: `src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_scf_trial_last/running_scf.log`（legacyio 格式，多帧：INIT + 位移 + trial + P0 重算，末帧为试探结构）
- Create: 同目录 `STRU`（当前结构）与 `INPUT`（calculation=scf）
- Create: `tests/unit/test_abacuslite_frame_selection.py`（RED 测试）

**Test strategy:**
- Behavior boundary: `AbacusTemplate.read_results`（经 `Abacus` 计算器路径或直接 `read_abacus_out` 单测）在 scf 多帧累积下返回"当前结构"帧的力，而非无条件末帧。
- Existing suite: 无既有套件拥有帧选择行为 → 新建 `tests/unit/test_abacuslite_frame_selection.py`（新行为边界）。
- Temporary probes: none。

**Interfaces:**
- Consumes: `abacuslite/io/legacyio.py::read_abacus_out(fileobj, sort_atoms_with=...)`（签名不变，返回全部帧的 Atoms 列表）；`abacuslite/io/generalio.py::read_stru(fn)`（读取 STRU 坐标）。
- Produces: 多帧金样路径（Task 3/4 复用）；帧选择失败判定的测试基线（末帧力 ≠ 当前结构力）。

- [ ] **Step 1: 写失败测试**

```python
"""scf 多帧累积下 read_results 必须返回当前结构帧的力（spec R1/R2，legacyio 主路径）。"""
from pathlib import Path

import numpy as np
from ase.io import read

from atst_tools.external.ASE_interface.abacuslite.io.legacyio import read_abacus_out


TESTFILES = Path(__file__).resolve().parents[2] / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
LOG = TESTFILES / "multiframe_scf_trial_last" / "running_scf.log"


def test_multiframe_scf_reads_current_structure_force_not_last_frame():
    """末帧为试探结构时，返回的力必须属于 STRU 当前结构（绝对 Å 容差匹配）。"""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    last = frames[-1]
    current = read(LOG.parent / "STRU", format="abacus")

    # RED：当前实现 read_results 取 [-1]，此处断言"末帧就是当前结构"将失败（末帧是试探结构）
    assert np.allclose(last.positions, current.positions, atol=1e-4), (
        "末帧为试探结构，坐标与当前 STRU 不一致——read_results 必须按坐标选择帧"
    )
```

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_abacuslite_frame_selection.py -v`
预期：FAIL（末帧为试探结构，坐标断言不通过）。

- [ ] **Step 2: 构造多帧金样**

以 `io/testfiles/lcao-symm1-nspin1-multik-scf` 为模板，手工拼装 `running_scf.log`：4 个几何帧（INIT 坐标、位移 A、试探 trial 坐标、P0 重算坐标），每帧含对应 DIRECT 坐标头与 TOTAL-FORCE 块；**末帧（trial）坐标与 `STRU` 的当前结构不同**，当前结构坐标帧为第 1 帧；保证 `len(trajectory)==len(forces)==len(energies)`。`STRU` 为当前结构（第 1 帧坐标）。注释记录帧序与对应结构。

- [ ] **Step 3: 提交 RED 测试与金样**

```bash
git add src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_scf_trial_last \
  tests/unit/test_abacuslite_frame_selection.py
git commit -m "test(abacuslite): 多帧 scf 金样与帧选择 RED 用例（末帧为试探结构，当前实现返回错误力）"
```

---

### Task 3: read_results scf-only 帧选择实现（GREEN）

**Files:**
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/core.py`（`AbacusTemplate.read_results`，约 358-374 行）
- Modify: `src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py`（如需新增坐标辅助函数；优先内联 core.py）

**Test strategy:**
- Behavior boundary: scf 下返回当前结构帧的力（fail-closed 无匹配报错）；非 scf（calculation=relax/md）保持 `[-1]`。
- Existing suite: `tests/unit/test_abacuslite_frame_selection.py`（RED 转 GREEN）+ `tests/unit/test_abacuslite_profile.py`（回归）。
- Temporary probes: none。

**Interfaces:**
- Consumes: Task 2 金样；`read_stru(fn)` 坐标；`self.atomorder`（物种分组序 revmap，spec P3 ①）。
- Produces: `read_results` 的新行为（Task 4 依赖）；fail-closed 异常含 log 路径/帧数/坐标差异摘要。

- [ ] **Step 1: 实现帧选择**

在 `core.py::read_results` 内，将 `atoms = read_abacus_out(...)[-1]` 替换为：

```python
frames = read_abacus_out(outdir / f'running_{self.calculation}.log', sort_atoms_with=self.atomorder)
if not frames:
    raise RuntimeError(f"no ABACUS running-log frames in {outdir / f'running_{self.calculation}.log'}")
if self.calculation != 'scf':
    atoms = frames[-1]  # 原生 relax/md：既有末帧语义（spec R2/P2）
else:
    atoms = _select_scf_frame_for_structure(frames, directory, self.atomorder)
```

模块级辅助（`core.py` 内）：

```python
def _stru_positions_in_ase_order(directory, stru_file, atomorder):
    """读取本次 write_input 落盘 STRU 的坐标，统一到与帧相同的 ASE 原子序（spec P3 ①）。"""
    from .io.generalio import read_stru

    stru = read_stru(Path(directory) / (stru_file or 'STRU'))
    lat = stru['lat']
    # species 分组序坐标（species[i]['atom'][k]['coord']）→ ASE 序（atomorder 是 revmap）
    species_xyz = np.concatenate(
        [np.asarray(a['coord'], dtype=float) for sp in stru['species'] for a in sp['atom']]
    )
    ase_xyz = np.empty_like(species_xyz)
    for ase_idx, species_idx in enumerate(atomorder):
        ase_xyz[ase_idx] = species_xyz[species_idx]
    # DIRECT -> Cartesian（lat['vec'] 格矢 * lat['const'] 缩放），CARTESIAN 仅缩放
    if str(stru['coord_type']).lower().startswith('d'):
        cell = np.asarray(lat['vec'], dtype=float) * lat['const']
        return ase_xyz @ cell
    return ase_xyz * lat['const']


def _select_scf_frame_for_structure(frames, directory, atomorder, atol=1e-4):
    """返回坐标与当前 STRU 一致（绝对 Å 容差）的最后一帧；无匹配 fail-closed。"""
    stru_file = getattr(Path(directory), 'name', None)
    expected = _stru_positions_in_ase_order(directory, 'STRU', atomorder)
    for frame in reversed(frames):
        if np.allclose(frame.positions, expected, atol=atol):
            return frame
    raise RuntimeError(
        f"scf running log 无与当前结构匹配的帧（{len(frames)} 帧；STRU 坐标与末帧差异见诊断）——"
        f"force 读取不一致，fail-closed"
    )
```

注：`read_stru` 返回结构已核实——`species[i]['atom'][k]['coord']` 为坐标、`stru['coord_type']` 为 Direct/Cartesian、`lat['vec']`（a0 单位格矢）× `lat['const']` = Å 格矢；`read_abacus_out` 帧坐标已是 Cartesian Å，故统一换算到 Cartesian Å 比较。

- [ ] **Step 2: 运行 RED 用例转 GREEN**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_abacuslite_frame_selection.py -v`
预期：PASS（现在按坐标选择了当前结构帧）。

- [ ] **Step 3: 非 scf 保持末帧语义的回归用例**

在 `tests/unit/test_abacuslite_frame_selection.py` 增加：`calculation='relax'`（或复用既有 relax 金样）断言 `read_results` 走 `[-1]`（不触发坐标匹配）。运行同上，预期 PASS。

- [ ] **Step 4: 全量单测回归并提交**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit -q`
预期：全绿（既有 17 项 + 新增）。

```bash
git add src/atst_tools/external/ASE_interface/abacuslite/core.py tests/unit/test_abacuslite_frame_selection.py
git commit -m "fix(abacuslite): read_results scf-only 坐标帧选择（末帧非当前结构 fail-closed，不改 read_abacus_out 签名）"
```

---

### Task 4: 四/五路径回归扩展（双后端、容差、排列、eig_occ 一次性消费）

**Files:**
- Modify: `tests/unit/test_abacuslite_frame_selection.py`（扩充）
- Create（如无既有夹具）: `src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_md_latest/`、`multiframe_md_legacy/`（md 路径金样，按 R2/P5）

**Test strategy:**
- Behavior boundary: md（MD_dump latestio）/ md（legacy 原生）/ relax（ASE 驱动）/ sella（试探步模式）/ ccqn（自循环）五条路径帧选择；容差两侧；DIRECT/CARTESIAN；排列一致性；latestio eig_occ.txt 一次性消费。
- Existing suite: 扩充 `tests/unit/test_abacuslite_frame_selection.py`；`tests/unit/test_abacuslite_io_reorder.py` 既有排列用例对齐。
- Temporary probes: none。

**Interfaces:**
- Consumes: Task 3 `read_results` 行为；legacyio/latestio 双后端金样；`eig_occ.txt` 一次性消费语义（P5）。
- Produces: 覆盖矩阵回归基线（Task 8 SAI 实证的本地对照）。

- [ ] **Step 1: 容差两侧用例**

```python
def test_frame_selection_tolerance_both_sides():
    """绝对 Å 容差（如 1e-4）：容差内通过、容差外 fail-closed。"""
    import numpy as np
    from pathlib import Path

    from atst_tools.external.ASE_interface.abacuslite.core import _select_scf_frame_for_structure
    from ase import Atoms

    def _frame(xyz):
        atoms = Atoms(positions=xyz)
        return atoms

    current = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    frames = [_frame(current + 1e-5), _frame(current + 1e-3)]  # 近帧（容差内）、远帧（容差外）
    directory = Path(".")

    # 容差内：取与 current 匹配的最后一帧（近帧）
    selected = _select_scf_frame_for_structure(frames, directory, [0, 1], atol=1e-4)
    assert selected.positions[0, 0] == 0.0  # 或按实现断言 np.allclose(selected.positions, current, atol=1e-4)

    # 容差外：无匹配帧 → fail-closed
    try:
        _select_scf_frame_for_structure([_frame(current + 1e-3)], directory, [0, 1], atol=1e-4)
    except RuntimeError as exc:
        assert "fail-closed" in str(exc)
    else:
        raise AssertionError("无匹配帧必须 fail-closed")
```

- [ ] **Step 2: md / relax / sella / ccqn 路径用例**

`read_results` 层按 `calculation` 值驱动：`md`（latestio MD_dump 与 legacy 原生各一条，断言走 `[-1]` 不触发坐标匹配）；`relax`（ASE 驱动逐步 scf 视为 scf 校验 + 原生多帧单次调用走 `[-1]` 各一条）；sella/ccqn 复用 scf 语义（无专门分支，各一条冒烟）。

- [ ] **Step 3: latestio eig_occ.txt 一次性消费（P5）**

latestio 金样用例：`read_abacus_out` 完整读取后 `eig_occ.txt` 被 `unlink`；重复读取前须重建文件（测试内 `touch`/`write_text` 重建）。

- [ ] **Step 4: 运行全量并提交**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit -q`
预期：全绿。

```bash
git add tests/unit/test_abacuslite_frame_selection.py \
  src/atst_tools/external/ASE_interface/abacuslite/io/testfiles
git commit -m "test(abacuslite): 五路径/双后端/容差两侧/排列/eig_occ 一次性消费回归矩阵"
```

---

### Task 5: CI 基线单一事实源（P6）与账本登记

**Files:**
- Modify: `.github/workflows/abacuslite-ase-interface.yml`（`ABACUS_DEVELOP_REF` 从 `ABACUSLITE_SNAPSHOT.md` 解析）
- Modify: `tests/unit/test_abacuslite_ci.py`（断言单一事实源）
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`（本 plan/spec 登记，P8）

**Test strategy:**
- Behavior boundary: CI 中 `ABACUS_DEVELOP_REF` 与 `ABACUSLITE_SNAPSHOT.md` 的基线 SHA 一致；账本含本 plan 条目。
- Existing suite: `tests/unit/test_abacuslite_ci.py`。
- Temporary probes: none。

**Interfaces:**
- Consumes: Task 1 的 `ABACUSLITE_SNAPSHOT.md`。
- Produces: CI 单一事实源（无双写）；账本登记（P8）。

- [ ] **Step 1: workflow 从 SNAPSHOT.md 解析 SHA**

在 workflow 中替换硬编码 `ABACUS_DEVELOP_REF` env：

```yaml
env:
  ABACUS_DEVELOP_REF: ${{ steps.resolve-base.outputs.sha }}

jobs:
  resolve-base:
    runs-on: ubuntu-latest
    outputs:
      sha: ${{ steps.sha.outputs.value }}
    steps:
      - uses: actions/checkout@v4
      - id: sha
        run: |
          SHA=$(grep -oP '(?<=当前基线：上游 `)[0-9a-f]{40}' \
            src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md)
          echo "value=$SHA" >> "$GITHUB_OUTPUT"
```

并将 abacuslite-unit job 的 checkout upstream 步骤改为依赖 resolve-base 的输出（或简化为同 job 内 shell 解析 + env 注入；实现以最小改动、单一事实源为准）。

- [ ] **Step 2: 更新 test_abacuslite_ci.py 断言**

在 `test_abacuslite_ci_runs_snapshot_drift_checker` 中，将"workflow 含硬编码 SHA"断言改为"workflow 引用 SNAPSHOT.md 解析 + SNAPSHOT.md 含基线 SHA"。

- [ ] **Step 3: 账本登记（P8）**

`docs/reports/DOCUMENTATION_STATUS_REPORT.md` 登记：spec `2026-08-04-abacuslite-cross-repo-and-force-read-design.html`、review `...-review.md`、plan `2026-08-04-abacuslite-force-read-and-cross-repo-plan.md`。

- [ ] **Step 4: 运行测试并提交**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_abacuslite_ci.py tests/unit/test_abacuslite_snapshot_ci.py -q`
预期：全 PASS。

```bash
git add .github/workflows/abacuslite-ase-interface.yml tests/unit/test_abacuslite_ci.py \
  docs/reports/DOCUMENTATION_STATUS_REPORT.md
git commit -m "ci(abacuslite): ABACUS_DEVELOP_REF 从 ABACUSLITE_SNAPSHOT.md 解析（单一事实源）；账本登记 spec/plan"
```

---

### Task 6: 工作树对齐 abacus-develop 分支基线（drift gate 对齐，验收前置）

**Files:**
- Modify: `scripts/check_abacuslite_snapshot.py`（`VENDORED_ONLY_FILES` 登记 atst 自有文件）
- Modify: `scripts/check_abacuslite_snapshot.py`（core.py 帧选择语义补丁归一化）
- Modify: `src/atst_tools/external/ASE_interface/PATCHES.md`（登记 core.py 帧选择语义补丁）
- Modify: `tests/unit/test_abacuslite_snapshot_ci.py` / `tests/unit/test_checker_efermi_whitelist.py`（对齐场景用例）
- Modify（如有必要）: `src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md`（同步状态核对）

**Test strategy:**
- Behavior boundary: checker 对 abacus-develop develop 分支基线（tip）exit 0——实现零 drift、自有文件（`ABACUSLITE_SNAPSHOT.md`/`PATCHES.md`/`multiframe_*` 金样）不再报 vendored-only；未登记新文件仍 exit 1。
- Existing suite: `tests/unit/test_checker_efermi_whitelist.py`、`tests/unit/test_abacuslite_snapshot_ci.py`。
- Temporary probes: none。

**Interfaces:**
- Consumes: Task 1 的 `ABACUSLITE_SNAPSHOT.md`/`PATCHES.md`；Task 2 的 `multiframe_scf_trial_last/` 金样。
- Produces: 对齐验收前置（Task 9 验收的 precondition）；checker 对 develop tip exit 0 的实证。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_checker_efermi_whitelist.py` 增加：构造"upstream 树 + vendored 树含自有文件（ABACUSLITE_SNAPSHOT.md/PATCHES.md/金样）且实现零 drift"场景，断言 `compare_snapshots` 返回 0。
当前实现（`VENDORED_ONLY_FILES = {Path("__init__.py")}`）会把这些自有文件报为 "Unexpected vendored-only files" → 返回 1 → 测试 FAIL。

- [ ] **Step 2: 登记自有文件**

`scripts/check_abacuslite_snapshot.py` 的 `VENDORED_ONLY_FILES` 扩展为登记 atst 自有文件：

```python
VENDORED_ONLY_FILES = {
    Path("__init__.py"),
    Path("ABACUSLITE_SNAPSHOT.md"),
    Path("PATCHES.md"),
}

def _is_vendored_only(relative_path: Path) -> bool:
    """atst 自有文件：顶层基线/补丁文档，以及 curated 多帧金样目录（upstream 无此夹具）。"""
    if relative_path in VENDORED_ONLY_FILES:
        return True
    return relative_path.parts[:4] == ("abacuslite", "io", "testfiles", "multiframe_")
```

并在 `compare_snapshots` 的 `extra` 计算中改用 `_is_vendored_only`：

```python
extra = {p for p in (vendored_files - upstream_files) if not _is_vendored_only(p)}
```

（保留 `VENDORED_ONLY_FILES` 作为精确路径集合；`multiframe_*` 前缀规则覆盖 Task 2/4 的 curated 金样，防 Task 4 新增夹具时再漏。）

- [ ] **Step 3: 登记 core.py 帧选择语义补丁（Task 3 产出，PATCHES.md + checker 归一化）**

`PATCHES.md` 增加一行：`abacuslite/core.py` 帧选择（`read_results` scf-only 坐标匹配，Task 3 产出）——未上游化（待 PR）。
`check_abacuslite_snapshot.py` 新增 `_normalize_frame_selection`（AST 或标记归一化）：移除两个模块级辅助函数（`_stru_positions_in_ase_order`、`_select_scf_frame_for_structure`），并把 `read_results` 的 scf/non-scf 分支还原为上游 `[-1]` 单行——使归一化后 core.py 与上游一致。在 `_normalize_documented_atst_adaptations` 对 `abacuslite/core.py` 调用。
测试：`test_checker_efermi_whitelist.py` 增加"core.py 含帧选择补丁 → checker exit 0"用例。

- [ ] **Step 4: 对齐核对（验收前置实证）**

对 abacus-develop develop 分支基线（tip）跑 checker：
`python3 scripts/check_abacuslite_snapshot.py --upstream <develop tip 树>/interfaces/ASE_interface --vendored src/atst_tools/external/ASE_interface`
预期：exit 0（无 drift、无 vendored-only 报警）。
同时对钉扎基线 70f7ed69 复核 exit 0。

- [ ] **Step 5: 全量测试并提交**

运行：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest tests/unit/test_checker_efermi_whitelist.py tests/unit/test_abacuslite_snapshot_ci.py -q`
预期：全 PASS。

```bash
git add scripts/check_abacuslite_snapshot.py tests/unit/test_checker_efermi_whitelist.py
git commit -m "fix(abacuslite): checker 登记 atst 自有文件（SNAPSHOT/PATCHES/multiframe 金样），对齐 abacus-develop 分支基线 exit 0"
```

> **执行注记**：Task 1 报告"checker 对 70f7ed69 基线 exit 0"未考虑自有文件导致 gate exit 1（管道/工具实测掩盖）；本任务修正该缺口并作为 Task 9 验收前置。

---

### Task 7: Phase 0 SAI 取证（外部依赖：SAI 节点访问）

**Files:**
- Create（本仓可交付物）: `tools/abacuslite_phase0_diagnosis.py`（在 SAI 节点运行的取证脚本：逐帧坐标头/帧数/TOTAL-FORCE 块计数/INPUT calculation/时间线）

**Test strategy:**
- Behavior boundary: 脚本在 SAI 上对 `sella_repro` 运行目录输出 (a)/(b')/(c) 判定证据；本地仅静态自检（`bash -n` / 无副作用 import）。
- Existing suite: 无（外部取证脚本）；本地只做语法/导入自检。
- Temporary probes: none。

**Interfaces:**
- Consumes: `read_forces_from_running_log` / `read_traj_from_running_log`（abacuslite.io.legacyio/latestio）。
- Produces: 诊断纪要（写入 `docs/reports/` 并登记账本）→ 验证/校准 Task 3 的容差与 fail-closed 行为。

- [ ] **Step 1: 编写取证脚本**（输出帧数、逐帧坐标头、力块计数、末帧坐标 vs STRU、INPUT calculation、调用时间线）
- [ ] **Step 2: 本地自检**（`python3 -m py_compile`；`bash -n`；无 SAI 路径硬编码，路径作 CLI 参数）
- [ ] **Step 3: 提交脚本**

```bash
git add tools/abacuslite_phase0_diagnosis.py
git commit -m "tools(abacuslite): Phase 0 SAI 取证脚本（帧数/坐标头/力块计数/时间线，判定 a/b'/c 子机制）"
```

> **执行注记**：SAI 节点运行与 running log 取回需要 SAI 访问（本会话不可达时标记 BLOCKED-外部；不阻塞 Task 1-5 本地推进）。取证结果用于校准容差与确认子机制，不改变 Task 3 的坐标帧选择设计（对 (a)/(b')/(c) 均稳健）。

---

### Task 8: 上游 PR 与文档对齐（Phase 3，外部依赖：abacus-develop 推送授权）

**Files:**
- Modify: `docs/index.md`、`AGENTS.md`、`docs/developer/HANDOVER.md`（D6/R7）
- Modify: `src/atst_tools/external/ASE_interface/PATCHES.md`（上游合入后更新状态）
- Modify: `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design.html`（如上游合入后基线推进标注）

**Test strategy:**
- Behavior boundary: 文档措辞与 D6 一致（"本仓为主 + 定期同步 + 长期退位 vendored"）；HANDOVER backend 小节含基线/补丁清单条目；PATCHES.md 上游状态更新。
- Existing suite: `tests/unit/test_docs_api.py`（如涉及 docs 引用）；`make docs-check`（若 atst-tools 有）。
- Temporary probes: none。

**Interfaces:**
- Consumes: Task 1 基线/补丁清单；Task 3 修复。
- Produces: 文档治理闭环（R7/P8）；上游 PR 清单（力读取修复 + efermi，band parser 不重复）。

- [ ] **Step 1: 本地文档对齐**（`docs/index.md` Backend Policy、`AGENTS.md`、`HANDOVER.md` backend 小节、`PATCHES.md` 上游状态列）
- [ ] **Step 2: 运行 docs/测试自检并提交**

```bash
git add docs/ src/atst_tools/external/ASE_interface/PATCHES.md
git commit -m "docs(abacuslite): 后端策略/维护指引/账本对齐（本仓为主 + 定期同步 + 长期退位 vendored）"
```

- [ ] **Step 3: 上游 PR 准备**（力读取修复 + efermi 合并为一个 PR 提交 abacus-develop `interfaces/ASE_interface`）

> **执行注记**：PR 推送 abacus-develop 需授权（外部）；合入后更新 `ABACUSLITE_SNAPSHOT.md` 基线并再同步 vendored（作为 follow-up，不阻塞本计划本地任务）。

---

### Task 9: 验收——重新打 SIF 镜像 + sai-local-e2e 本地测试（R8，用户明确要求的验收门）

**Files:**
- Modify（如构建配置需随修复更新）: `container/2.0/sai/`（ABACUS toolbox 侧 SIF 构建；atst-tools 以 deps 子模块指针/源码打进镜像）
- Create（e2e 产物，不提交）: `.adam-sai-runs/<run_id>/` 下的验收证据（sai-local-e2e 输出）

**Test strategy:**
- Behavior boundary（spec R8）: 修复后的 Sella 不再 2 步停（多步收敛）；md/relax/sella/ccqn 四条路径端到端 exit 0；GPU 证据（cusolver）在作业内确认；drift checker 对钉扎基线 exit 0。
- Existing suite: `sai-local-e2e` skill（本机 Adam CLI + OpenCode 在 SAI 上运行非交互式 e2e）+ `validate_adam_sif.py`（SIF 内安装验证）。
- Temporary probes: e2e 运行目录（`.adam-sai-runs/`，gitignore）；无提交产物。

**Interfaces:**
- Consumes: Task 3 修复 + Task 5 CI/账本（验收对象为 Task 1-5 收敛后的 atst-tools 状态）。
- Produces: 验收证据（sella 多步收敛 + 四路径 exit 0 + GPU cusolver 证据 + SIF 内 atst-tools 版本/依赖确认）→ 支撑 follow-up（Task 6/7 与发布）。

- [ ] **Step 0: 前置——工作树已对齐 abacus-develop 分支基线（Task 6 完成、checker 对 develop tip exit 0）**

- [ ] **Step 1: 重新打 SIF 镜像（local 模式）**

在 ABACUS toolbox `container/2.0/sai/` 构建目录执行（沿用本会话已建立的 local 模式流程）：Layer 1（abacus-sai.sif）→ Layer 2（`abacus-adam-sai.sif`，`SOURCE_MODE=local` 从本地 atst-tools 源码 pip 安装，即本计划 Tasks 1-5 的修复后状态）。确认 SIF 内 `atst-tools` 版本与依赖为修复后 commit。

```bash
# 以实际构建脚本为准（container/2.0/sai/ 下；构建授权已在本会话确认 local 模式）
cd ~/sif-build/container/2.0/sai   # 或实际构建工作目录
make layer1 && make layer2         # 或构建脚本实际入口
```

- [ ] **Step 2: SIF 内安装验证（validate_adam_sif.py）**

运行 SIF 验证脚本，确认 SIF 内 atst-tools 2.2.x（含修复）可导入、NEB 链路产物完整（neb.traj + neb_energy_profile.png + evidence）。

- [ ] **Step 3: sai-local-e2e 本地测试（验收核心）**

按 `$sai-local-e2e` skill（本机 Adam CLI + OpenCode，不经 AsterFire 平台、不 bump 版本号）提交 GPU 作业（4V100，LTS 3.10.1，INPUT `ks_solver cusolver`），覆盖：
- **sella**：从"2 步停"验证为"多步收敛"（fmax 单调下降或正常收敛，`3fa98bf` 的提前返回警告不出现）；
- **ccqn**：真实收敛（对照历史 11 步 fmax 0.0467）；
- **NEB / AutoNEB image-parallel**：image_0xx 并行目录 + GPU cusolver 证据 + 链推进；
- 每条路径 exit 0，产物（traj/PNG/evidence）齐全。

- [ ] **Step 4: 验收证据落盘并登记账本**

将验收结果（sella 多步收敛、四路径 exit 0、GPU 证据、SIF 版本）写入验收报告（`docs/reports/` 或既有验证报告追加），并登记 `DOCUMENTATION_STATUS_REPORT.md`。

> **执行注记**：本任务需要 SAI 作业提交（sai-local-e2e 链路）与 SIF 构建环境；验收是"本地任务收敛后"的端到端门（R8）。若 SAI/构建环境在会话内不可达，标记 BLOCKED-外部并保留为发布前强制门。

---
