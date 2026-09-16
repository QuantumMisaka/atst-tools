# 周期性镜像感知的 abacuslite SCF 帧校验修复与 2.2.5 发布实施计划

**Goal:** 修复 `abacuslite` 在周期性体系和过渡态跨胞移动场景下误拒绝合法 SCF 帧的问题，同时保留对真正错帧、错胞、错序和坏输出的 fail-closed 保护，并将修复发布为 `atst-tools` 2.2.5。
**Spec:** `none - requirements supplied directly`；既有 `docs/superpowers/plans/2026-08-04-abacuslite-force-read-and-cross-repo-plan.md` 仅作为 SCF 帧选择的历史背景，本计划补充其未覆盖的周期性等价、过渡态跨胞和发布边界。
**Authorization:** 2026-09-16 用户明确要求完善本计划，以 `superpowers:subagent-driven-development` 分发开发，完成 atst-tools 优化及对应 Paimon 新版本更新发布。范围包括 atst-tools main/PyPI 发布、Paimon 依赖 gitlink/版本/发布文档与发布包；运行时部署按现有 SIF 发布机制落实，具体有副作用的容器/计算操作须核对本次授权边界。Gitee 不在本轮范围。
**Architecture:** 以 `origin/main` 已发布的 2.2.4 为基线，在 `src/atst_tools/external/ASE_interface/abacuslite/core.py` 保留一个唯一的 SCF 帧选择器。它把 STRU 和 running log 帧统一为 ASE 原子序、Cartesian Å 和同一 3×3 晶胞，先检查形状/数量/有限值/元素顺序/晶胞，再用分数坐标下的整数晶格平移判定周期性等价；反向选择最新匹配帧，失败时保留完整诊断。非 SCF 原生 relax/md 继续使用末帧语义，不新增用户开关或上层重复校验。
**Verification:** 先在批准的开发环境完成预检；按 TDD 扩展现有帧选择测试覆盖 legacy/latest、Direct/Cartesian、正交/三斜晶胞、单原子及多原子整数平移、真实错配、错胞/错序/数量错误和不变性；运行快照 drift、上游风格 parser、全量 pytest、文档治理、构建/Twine、wheel API 和精确 tag readiness；发布后以干净环境安装 2.2.5 并核对 CLI/API 版本和 PyPI 元数据。

## 范围、约束与责任边界

### 变更组件

| 组件 | 责任 |
| --- | --- |
| `src/atst_tools/external/ASE_interface/abacuslite/core.py` | 唯一的 STRU/帧身份匹配和 fail-closed 诊断；不改变 `read_abacus_out` 公共签名。 |
| `tests/unit/test_abacuslite_frame_selection.py` | 以可观察的 `read_results`/选择器行为保护周期性和跨后端回归；复用现有多帧金样，新增最小合成夹具。 |
| `scripts/check_abacuslite_snapshot.py`、`PATCHES.md`、`ABACUSLITE_SNAPSHOT.md` | 记录并机械允许本仓 vendored 语义补丁，仍拒绝未登记 drift；基线 SHA 不因本修复而推进。 |
| `README.md`、用户/开发者文档、reports、release note、版本元数据 | 说明自动校验语义、兼容边界和 2.2.5 发布证据；不新增 YAML 字段。 |
| `.github/workflows/abacuslite-ase-interface.yml`、`.github/workflows/publish-pypi.yml` | 复用现有 abacuslite 回归和精确 tag 发布管线，不增加第二套业务校验。 |

### 设计不变量与非目标

- 不删除 SCF 帧校验，也不通过放宽 `atol`、全局 `wrap` 或取末帧来掩盖问题；`atol=1e-4 Å` 继续只代表日志打印精度。
- 周期性等价只用于“当前 STRU 与候选帧是否为同一结构”的选择，不修改 `Atoms.positions`、STRU、轨迹或 TS/NEB 插值路径；过渡态跨胞的连续坐标由上层工作流保留。
- 不新增 `pbc_mode`、容差或用户配置开关；不在 workflow、runner、SIF 外再复制一份检查。
- 只对 `calculation == 'scf'` 选择匹配帧；原生 `relax`、原生 `md`/`MD_dump` 保持既有 `frames[-1]` 行为。
- Sella、CCQN、Dimer、NEB/AutoNEB 等逐点调用 SCF 的路径自然复用该唯一选择器；不为每个工作流增加专门分支。
- 复用现有 parser 的语法/帧数检查；新增边界只负责跨工件身份一致性。若现有 `stru_file` 参数已被 `write_input` 支持，读取时必须使用同一实际文件名，但不引入新参数。
- Paimon 依赖更新与新版本发布纳入 Task 8；PyPI 发布不会自动改变已构建容器中的 vendored 代码，不能以 ZIP metadata 更新冒充运行时修复生效。

## 2026-09-16 审阅裁决与执行记录

- 工作流 L3 / SDD；atst 基线 `9318177798d1d087a061e298523b58a6f758cbd7`（2.2.4），父仓基线 `949119c9b`（Paimon 1.2.51）。隔离工作区为 app-tools `.worktrees/atst-periodic-225` 与 `.worktrees/paimon-atst-1252`；原始 detached 子模块与未提交计划保留。
- Ruling: 测试显式使用 `conda run -n abacus-env env PYTHONPATH=<candidate>/src python ...`，并核验 `atst_tools.__file__` 与 core 模块路径均位于候选目录；当前环境安装的是 2.2.3，单有 conda 预检不足以绑定源码。wheel 检查使用实际构建的 `--wheel`，在无源码 PYTHONPATH 的独立进程中进行。
- Ruling: 有效但结构/晶胞不同的帧是候选不匹配，可继续反向查找；非有限值、非法 shape、奇异 cell、非法映射等损坏数据使整次 SCF 读取 fail-closed，不因较早帧匹配而隐瞒坏输出。先校验全部候选的可解释性，再选择最新匹配；覆盖混合有效/损坏帧。映射需在 parser 重排前校验，或在边界捕获可定位的解析错误，避免裸 IndexError。
- Ruling: `write_input` 已支持 `stru_file`，文件名传递及非默认文件名回归是必做；保留未调用 write_input 时默认 STRU 的行为。
- Ruling: snapshot checker 对登记的语义补丁先精确核验 AST/内容，再允许剥离 helper；不得只按函数名无条件忽略函数体。内容核验只用于登记补丁身份，行为正确性仍由回归测试与独立审查证明。
- Ruling: 推送 main 后等待同一 commit 的 Tests 与 abacuslite CI 成功，再推送 tag。远端 tag 不移动：基础设施瞬时失败可原 commit 重跑；需要修改源码则使用下一可用 patch 版本并同步元数据。
- Ruling: 发布后的证据回填作为单独文档提交；readiness 的 tag==HEAD 仅在候选/tag checkout 核验，不要求后续文档提交仍等于 release tag。
- 状态：计划修订和隔离工作区准备完成，环境预检通过。matcher、advisory 兼容移植、文档和 snapshot checker 已实现；候选回归在 `conda run -n abacus-env env PYTHONPATH=<candidate>/src python ...` 环境下完成全量 666 passed、19 conditional skipped（685 total），package-mode parser 28 项运行、2 项跳过，真实上游基线 snapshot checker exit 0，文档治理和 metadata 通过；build、Twine、clean-wheel API 首次通过。针对 STRU 末组声明原子数可能被底层 parser 静默截断的修订已冻结，core 新测试 32 passed，最终 core 重建验证与独立终审已通过。ATST 2.2.5 已从 release commit `4c966915c6f40984fc85806869f4766ecdd6ffc9` 推送并发布；官方无缓存 PyPI clean-install、CLI/API、依赖及 site-packages 身份核验均通过。SIF/SAI/platform runtime 和 Paimon 真实运行时部署仍未执行。
- 审计分工：matcher 与测试、advisory 兼容、发布文档分别由子代理实现；controller 集成 AST 精确快照检查，独立 reviewer 检查冻结候选。子代理不并发操作 Git index、不自行推送或发版。

## 执行顺序

### Task 1: 对齐 2.2.4 `main` 基线并完成环境预检

**Files:** 无业务文件；操作范围为 `deps/atst-tools` 独立 Git 仓库。

**Behavior / artifact:** 独立工作副本从 `origin/main` 的 2.2.4（`9318177`）开始；原始工作区保持不变，父仓候选在 Task 8 更新 gitlink。当前 detached 独有提交 `fd7c8da` 的功能是否已被 main 等价实现须在依赖集成时核验，不能仅因 SHA 不在 main 就丢弃必要行为。

**Dependencies:** 无。后续所有任务依赖本任务的基线和环境事实。

**Verification:**

- 检查 `git status --short --branch`、`git log -1`、`git show origin/main:pyproject.toml`，确认版本为 2.2.4 且 `v2.2.4` 已发布；不得把 2.2.4 当作新版本目标。
- 在当前 ABACUS 工作区按父仓库规则执行 `conda run -n abacus-env python -c "import sys, adam_community, ase, docstring_parser; print(sys.executable)"` 和 `conda run -n abacus-env adam-cli --help`。若在独立 `atst-tools` checkout 执行 release 门禁，则先核验其项目规定的 `atst-dev` 环境和同等 imports；环境失败不得静默回退到裸 `python`/`pytest`。
- 建立本地 `main` 工作状态后再开始修改；不重置或覆盖用户已有的其他工作树。

- [x] 将执行副本对齐 `origin/main`，记录基线 commit、版本和工作树状态。
- [x] 完成环境预检；若失败，停止执行代码任务并记录阻塞原因。

### Task 2: 先写周期性等价的 RED 回归矩阵

**Files:** `tests/unit/test_abacuslite_frame_selection.py`；必要时在同文件内添加最小 STRU/log/`Atoms` 夹具辅助，不新增重复的 workflow 测试文件。

**Behavior:** 现有绝对坐标匹配测试继续通过，并新增以下可观察边界：

1. running log 为 Direct、Cartesian 两种坐标系时，单个原子跨一个或多个晶格向量仍命中当前结构；多个原子可有不同的整数平移，正负方向都覆盖。
2. 非正交（三斜）晶胞使用分数坐标整数平移也能命中，不能用逐 Cartesian 轴取模的伪实现通过测试。
3. 同一晶胞下的非整数/超过容差残差 fail-closed；晶胞矩阵不同、奇异、形状错误、原子数错误、有限值错误或元素/`atomorder` 不一致均 fail-closed。
4. 匹配过程不修改候选 `Atoms` 的 positions、cell、forces 或 STRU 解析结果；仍反向选择“最后一个匹配帧”。
5. legacyio 与 latestio 均覆盖；现有 Sella/CCQN 复用冒烟测试保留一次即可，不为每个 TS 算法复制同一断言；native relax/md 末帧语义和无 STRU 的 MD 测试继续通过。
6. 传递既有 `stru_file` 文件名，增加非默认文件名回归，确认检查的是本次写入的文件而非硬编码 `STRU`。

**Dependencies:** Task 1。

**Verification:** 按 TDD 先运行新增 focused tests，预期周期性用例在当前 raw `np.allclose` 实现上失败；保留失败输出作为 RED 证据。测试只断言行为和稳定错误类别/诊断关键词，不锁定不必要的内部函数拆分或完整错误文案。

- [x] 复用现有 `multiframe_scf_trial_last`，构造单/多整数晶格平移的 Direct 与 Cartesian 变体。
- [x] 构造最小三斜晶胞夹具，并加入错胞、错序、数量/shape/finite 和真实残差过大分支。
- [x] 加入输入不变性和 legacy/latest 后端回归；确认 native relax/md 既有测试仍表达原语义。
- [x] 在批准环境中运行 focused suite，确认新增用例按预期 RED，再进入实现。

### Task 3: 实现唯一的 PBC-aware SCF 帧选择器

**Files:** `src/atst_tools/external/ASE_interface/abacuslite/core.py`；如确有必要，调整同一 vendored 模块内的内部辅助，不改变 `io/legacyio.py`、`io/latestio.py` 的公开读取签名。

**Behavior:** 将当前 STRU 和每个候选帧正规化后再比较：

1. 读取 STRU 的 species 分组坐标，按既有 `atomorder` 映射到 ASE 序；Direct/Cartesian 均转换为 Cartesian Å，并同时保留期望晶胞和元素序列。
2. 从 running log 的实际坐标头决定帧坐标系；帧 cell 已是 Å。先检查两个 3×3 cell 的形状、有限值和 `np.allclose(..., atol=atol, rtol=0)`，再检查原子数量、形状、有限值、元素序列和映射完整性。
3. 对通过前置检查的 frame，使用行向量约定的分数残差：

   `delta_frac = (frame_cart - stru_cart) @ solve(cell, I)`

   等价实现可使用稳定的线性求解；匹配残差为

   `(delta_frac - rint(delta_frac)) @ cell`

   的最大绝对 Cartesian Å 分量。仅当该值不超过 `atol` 时视为同一周期性结构。cell 奇异或无法正规化必须转换为带路径/帧号的 fail-closed `RuntimeError`，不能泄漏裸线性代数异常。
4. 反向扫描并返回最新匹配的原始 `Atoms` 对象；不对返回对象做 wrap 或坐标写回。无匹配时诊断至少包含 log 路径、帧数、最后帧 raw Cartesian 差异、周期性残差/晶胞差异摘要和 `atol`。
5. `read_results` 只在 `scf` 调用该选择器；`relax`/`md`/`MD_dump` 继续读取最后一帧。将 write_input 的实际 `stru_file` 文件名以既有内部状态或参数链路传给选择器，并保持默认 `STRU` 行为。

**Dependencies:** Task 2 RED tests；现有 `_stru_positions_in_ase_order`、`_frame_coordinate_is_direct`、`_select_scf_frame_for_structure` 和 `read_results` 是实现入口。

**Verification:** 先运行 focused tests 使周期性矩阵 GREEN，再运行现有 `tests/unit/test_abacuslite_frame_selection.py` 全文件，确认旧的容差、atomorder、Direct/Cartesian、Sella/CCQN 复用及 native relax/md 语义不回归。

- [x] 在一个内部规范化记录中统一 positions/cell/symbols；避免在 workflow 层新增第二个 matcher。
- [x] 以 fractional lattice translation 判定周期等价；禁止全局 wrap、逐轴 modulo 或修改输入/输出结构。
- [x] 实现完整 fail-closed 前置检查和可行动诊断。
- [x] 使用 focused + owning suite 完成 GREEN，并清理临时夹具/调试输出。

### Task 4: 更新 vendored snapshot 账本和 drift checker

**Files:**

- `src/atst_tools/external/ASE_interface/PATCHES.md`
- `src/atst_tools/external/ASE_interface/ABACUSLITE_SNAPSHOT.md`
- `scripts/check_abacuslite_snapshot.py`
- `tests/unit/test_abacuslite_snapshot_ci.py`（必要时同文件补 checker fixture）

**Behavior / artifact:** 将 core.py 帧选择补丁从“无 PBC 的防御性改进”更新为“PBC-aware 的 SCF 工件身份校验/bug fix”，登记日期、适用范围和未上游化状态；保持基线 `70f7ed69b5677c447afdc78e05240e93da660e66` 不变。checker 只归一化已登记的 helper/read_results 语义差异，任何改坏 fractional 判定或无关代码仍返回 exit 1。

**Dependencies:** Task 3 的最终函数边界；不得先随意放宽 `_FRAME_SELECTION_BLOCK` 正则。

**Verification:**

- 用固定上游基线运行 `scripts/check_abacuslite_snapshot.py --upstream <baseline>/interfaces/ASE_interface --vendored src/atst_tools/external/ASE_interface`，预期 exit 0。
- 测试一个只含登记补丁的 vendored tree，预期 exit 0；再分别改变 fractional rounding、cell/元素校验和无关实现，预期 exit 1 且输出具体 drift。
- 运行快照 CI 测试和 `.github/workflows/abacuslite-ase-interface.yml` 覆盖的 ATST/parser 测试清单；不要直接运行会绕过包上下文的上游 `xtest.sh`。

- [x] 让 checker 的归一化块精确覆盖新的 helper/分支，并以失配报警作为 fail-safe。
- [x] 更新 `PATCHES.md` 与快照差异摘要；不把本修复误写成上游已合入。
- [x] 运行 snapshot checker、checker 单测、abacuslite 回归和 package-mode parser 单测。

### Task 5: 同步用户边界、状态账本和 2.2.5 release candidate

**Files:**

- `pyproject.toml`：`2.2.4` → `2.2.5`
- `README.md`：版本 badge、At-a-Glance 当前状态和发布范围
- `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`：SCF 帧身份检查的 PBC-aware 语义、fail-closed 边界和 native relax/md 例外
- `docs/user/CONFIG_REFERENCE.md`、`docs/user/USER_GUIDE_CN.md`：仅增加必要的“自动执行、无配置开关、跨胞合法”说明；不新增 schema 字段或生成冗余表格
- `docs/index.md`：当前 release 导航切换到 2.2.5
- `docs/reports/FEATURE_STATUS_MATRIX.md`、`docs/reports/DOCUMENTATION_STATUS_REPORT.md`：版本/日期、abacuslite backend 事实和当前 release 入口
- Create `docs/releases/RELEASE_NOTES_2.2.5.md`

**Behavior / artifact:** 用户能明确知道该检查接受周期性镜像和过渡态跨胞移动，但仍拒绝不同结构；没有新的 `pbc_mode` 或容差参数。release note 必须包含以下精确行，并区分“代码已发布”与“SIF/SAI 尚未更新”的事实：

```text
- Package version: `2.2.5`.
```

**Dependencies:** Tasks 3–4；版本只在行为和快照检查通过后 bump。

**Verification:** `python scripts/check_docs_governance.py`、`git diff --check`、冲突标记扫描；`tests/unit/test_package_metadata.py`；核对 release note、README、reports 和 docs index 不再把 2.2.4 作为当前 release。无需为纯文档段落增加合成代码测试。

- [x] 写 2.2.5 release note，包含修复范围、兼容性、验证矩阵和待填充的 tag/CI/PyPI 证据字段。
- [x] 更新 backend/用户边界文档和两个状态 reports；确认没有声称修改 SIF 或完成新的科学收敛。
- [x] bump 版本并运行 metadata/docs checks；清除临时 build/dist 产物或将其留在受控临时目录。

### Task 6: 发布前全量门禁与独立终审

**Files:** 影响 Task 1–5 的冻结 diff；不再引入新功能。

**Behavior / artifact:** 形成可直接推送 `main` 和打 `v2.2.5` 的单一候选 commit。当前模型家族独立 reviewer 完成正常终审；跨家族审阅仅作为维护者按需采用的 advisory evidence，不是发布硬门。

**Dependencies:** Tasks 1–5 全部 GREEN。

**Verification:** 在发布 checkout 依次运行：

```bash
conda run -n <approved-atst-env> python -m pytest tests -q
conda run -n <approved-atst-env> python scripts/check_docs_governance.py
conda run -n <approved-atst-env> python -m build
conda run -n <approved-atst-env> python -m twine check --strict dist/*
conda run -n <approved-atst-env> python scripts/verify_wheel_api.py --wheel dist/<actual-candidate-wheel>.whl
```

其中 `<approved-atst-env>` 在本 ABACUS 工作区按父规则取 `abacus-env`；独立 atst-tools checkout 按其已核验的 `atst-dev` 取值，不能用未核验的裸环境冒充证据。确认 `git diff --check`、`git status`、全量 pytest、快照 checker、abacuslite CI 清单和构建产物都干净；确认 release note 的版本行存在。

- [x] 固定最终 diff，完成 reviewer 对核心 matcher、错误诊断、非 SCF 兼容性和测试充分性的审阅。
- [x] 运行全量 pytest、文档治理、构建、Twine、wheel API 和 snapshot/package-mode gates。
- [x] 记录每条门禁的命令、环境和结果；失败项修复后从所属门禁重新运行，不用旧结果覆盖新代码。

当前候选状态（2026-09-16）：全量测试 666 passed、19 conditional skipped（685 total）；
真实上游基线 snapshot checker exit 0；core 新测试 32 passed；package-mode parser 28 项运行、
2 项跳过；文档治理和 metadata 通过；build、Twine、clean-wheel API 首次通过，最终 core
重建验证与独立终审已通过。Task 6 本地发布前 gate 全部完成；Task 7/8 仍待执行。

### Task 7: 直接更新 `main`、发布 2.2.5 并核验外部结果

**Files / external boundary:** `QuantumMisaka/atst-tools` `main`、精确 tag `v2.2.5`、GitHub Actions、PyPI；父 ABACUS 仓库和 SIF 不在操作范围。

**Behavior / artifact:** 只有候选 commit 通过所有本地门禁后才进入 main/release。PyPI workflow 从精确 tag 构建，不接受任意 branch/commit；发布后的包必须包含 PBC-aware matcher。

**Dependencies:** Task 6 的冻结 commit 和证据；用户已经提供直接 main/发布授权。

**Verification / rollout:**

1. 在本地候选 commit 创建精确 `v2.2.5` tag；运行 `python scripts/check_release_readiness.py --tag v2.2.5`，确认 tag peeled commit == `HEAD`、`pyproject.toml` 版本和 release note 一致。
2. 推送已核验的 `main` commit，等待同 SHA 的 Tests 与 abacuslite CI 成功，再推送 `v2.2.5`；由现有 `publish-pypi.yml` 执行 release-preflight（readiness → pytest → docs governance → build → Twine → wheel API）后才进入 PyPI publish job。
3. 记录 GitHub abacuslite/Tests/Publish run；若任一 preflight 失败，停止发布后续动作。原 commit 的瞬时基础设施失败可重跑；若远端 tag 已存在且必须改源码，使用下一可用 patch 版本，不能移动 tag 指向。
4. 用干净环境执行 `python -m pip install --no-cache-dir atst-tools==2.2.5`、`pip check`、`python -c "import atst_tools; print(atst_tools.package_version())"` 和 `atst --version`；核对 PyPI JSON/项目页的 2.2.5 wheel 与 sdist。
5. 回写 release note、`DOCUMENTATION_STATUS_REPORT.md`、`FEATURE_STATUS_MATRIX.md` 的实际 tag/CI/PyPI 证据，并运行最终 docs governance。Gitee 镜像、父仓库 gitlink、SIF 重建和 SAI 重跑另行记录，不把未执行事项写成发布验收。

- [x] 创建并本地验证 `v2.2.5`，再按顺序推送 main 和 tag。
- [x] 监控并记录 GitHub Actions 与 PyPI 发布结果。
- [x] 完成 clean-install/CLI/API/PyPI 核验和发布文档结案。

Task 7 当前事实（2026-09-16）：release commit 已推送，远端 `v2.2.5` 已创建；Tests、
abacuslite 和 Publish workflow 均成功，PyPI 发布成功。官方 `https://pypi.org/simple`
无缓存 clean-install 在全新虚拟环境中通过；CLI 与 `package_version()` 均报告 2.2.5，
`pip check`、六个 root API 导入及 runner help 通过。安装位置为该环境的
site-packages，matcher `core.py` 已与受审 release source 做逐字节核验（SHA256
`30c11b06623e4850b27a2882f19b14c1bad1d3756780d9c5655d3a2b6d70d7ad`）。

### Task 8: Paimon 依赖集成与新版本发布

**Files:** 父仓 `toolbox/ABACUS/deps/atst-tools` gitlink、`config/configure.json`、双语 `config/long_description*.md`、`docs/guides/version-changelog.md`、既有 container/2.0 依赖与运行时发布记录、发布报告及分类入口。

**Behavior:** 以当前 1.2.51 后的下一未占用版本（预期 1.2.52）消费已发布 ATST。同步 source pin、依赖声明、实际 SIF 中安装版本及平台制品；确认原 fd7c8da 的 nonconvergence advisory 行为保留。禁止仅修改版本声明就声称平台已使用新 matcher。

**Dependencies:** 可并行调查与准备 metadata；最终 gitlink、容器验收、构建和发布依赖 Tasks 3–7。先核对 SIF 发布路径与必要授权；不能在未知运行时身份下上传宣称修复生效的包。

当前状态（2026-09-16）：Paimon 本地候选集成与发布前复核已完成：父仓 unit
`5964 passed, 1 skipped`，provenance `9 span` 无 drift，focused integration
`1 passed`，source-replay `550 records` 无 unresolved；完整 integration `57 passed,
1 skipped`（638 秒），local governance、build 和同一 ZIP 检查通过。Paimon 保留
`fd7c8da` 已有的 Sella、CCQN、Sella IRC 及最终 NEB nonconvergence advisory 行为。
SIF/SAI/platform runtime 与平台发布尚未执行，等待具体范围和授权确认。
候选分支 `release/paimon-atst-1252` 已推送：实现提交 `28ff0351b`、交接记录提交
`2643073e8`；Codeup MR 尚未创建/合入，父仓 main 未改动。

**Verification:** 遵循 `docs/guides/release-and-platform-validation.md`：abacus-env 预检、dependency check、local governance、unit、integration、make build、同一实际 ZIP 包检查；运行时变更按既有 SIF/SAI 验证入口核验实际 ATST 导入身份、API 和相应回归；平台发布使用同一 artifact 并回读版本。Agent/Flow 和科学计算验证分别记录，不以 metadata 可见性代替运行证据。

- [x] 确认 Paimon 集成文件、运行时交付路径及发布端点。
- [x] 更新依赖 pin、版本和双语 changelog，登记开发累积区并核验 advisory 兼容性。
- [ ] 完成 SIF/SAI 适用验证、本地门禁和独立终审；无法执行的外部环节明确记录 blocked。
- [ ] 完成已授权 Git/平台发布，回读制品身份并更新报告、分类入口和计划结案。

## 联合验收与完成判据

- PBC-aware matcher 在 Direct/Cartesian、正交/三斜晶胞和单/多原子整数平移下命中最新正确帧；真实错配、错胞、错序、数量/shape/finite 和奇异 cell fail-closed，诊断可定位。
- native relax/md 末帧语义、`read_abacus_out` 接口、atomorder、约束/RAW 力口径及现有 workflow 复用行为未改变；输入和候选帧未被隐式 wrap 或修改。
- snapshot ledger/checker、双后端 parser tests、全量测试、文档治理、构建和 wheel API 均通过；2.2.5 readiness 与 tag-to-HEAD 绑定通过。
- `main` 和 ATST release tag 发布事实、PyPI clean install 和限制项已记录；Paimon 新版本依赖、真实运行时与平台制品发布证据分别成立，不把旧 2.2.3 SIF 误报为本 release 的运行时验收。

## 计划自审与交接

本计划已逐项核对目标、授权、非目标、唯一 matcher 边界、既有消费者、测试依赖、快照治理和发布后的事实核验。执行时按任务依赖推进；代码实现完成后冻结 diff，再进入 Task 6 的终审和 Task 7 的 main/tag/PyPI 操作。新增配置、改变 native relax/md 语义或推进上游基线须重新确认。SIF 更新属于 Task 8 的既定必要范围，但具体 SAI 作业、新镜像槽位及 dev/prod 发布须取得明确授权；等待授权期间继续完成本地候选和 ATST 发布，不以旧 SIF 冒充修复落地。
