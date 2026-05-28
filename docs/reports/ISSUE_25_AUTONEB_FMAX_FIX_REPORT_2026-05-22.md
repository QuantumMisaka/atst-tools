# Issue #25 AutoNEB fmax 修复报告

**Date**: 2026-05-22  
**Issue**: https://github.com/QuantumMisaka/atst-tools/issues/25  
**Case**: `examples/03_autoneb_Cy-Pt`  
**Final status**: resolved; ready to close

## 1. Issue 现象

Issue #25 报告 `03_autoneb_Cy-Pt` 在 ATST-Tools 2.0 的 AutoNEB 示例中，
使用串行设置运行时出现异常大的 `fmax` 增长，最终 ABACUS 因结构不合理而
崩溃。用户给出的关键设置是：

```yaml
calculation:
  type: autoneb
  prefix: run_autoneb
  init_chain: inputs/init_neb_chain.traj
  n_simul: 1
  n_max: 10
  algorism: improvedtangent
  parallel: false
  optimizer: FIRE
  fmax: [1.00, 0.05]
  climb: true
  maxsteps: 10
  iter_folder: AutoNEB_iter
```

日志中的 `fmax` 不是 YAML 中的收敛阈值，而是 ASE optimizer 每一步报告的
实际最大力。问题本质是 FIRE 子优化过程中实际力持续升高，随后结构进入
ABACUS 无法处理的区域。

## 2. 最终结论

Issue #25 已解决，可以关闭。理由分为两层：

1. ATST-Tools 的 AutoNEB wrapper 已恢复 ASE-native 语义，修复了 refactor
   过程中可能影响 AutoNEB 稳定性和结果读取的实现问题。
2. `03_autoneb_Cy-Pt` 已用 main-like 生产参数在 SAI `4V100`、ABACUS LTS
   3.10.1、`ks_solver: cusolver` 上完成最终复算，并与 main branch 已提交
   AutoNEB 结果高度一致。

最终确认作业是 Slurm job `433962`：

| Metric | Main branch | Fixed current run | Delta |
| --- | ---: | ---: | ---: |
| Forward barrier | `1.327886` eV | `1.330070` eV | `+0.002184` eV |
| TS image | `5` | `5` | `0` |
| TS fmax | `0.041975` eV/Ang | `0.041272` eV/Ang | `-0.000703` eV/Ang |
| TS RMSD vs main | n/a | `0.004433` Ang | n/a |

该作业完整完成，运行环境为 `4V100` node `4v100n35`，耗时 `20:53:59`。
最终结果证明当前 `03_autoneb_Cy-Pt` 不再复现 issue #25 的失稳/崩溃问题，
并且不是只做 smoke run，而是可以回到 main branch 可比的 AutoNEB 结果。

## 3. 根因回溯

### 3.1 用户报告中的直接触发因素

Issue #25 的输入使用 `n_simul: 1`、`parallel: false`、`fmax: [1.00, 0.05]`
和 `maxsteps: 10`。这组参数会让单次 FIRE 子优化在每个 AutoNEB iteration
内走多步，且第一阶段阈值较松。如果 FIRE 迈入上坡方向，力会快速放大。

早期诊断确认：

- 日志中的 `fmax` 是实际最大力，不是 schema 或 YAML 参数被误解析。
- 该现象是 FIRE 子优化失稳，不是 ABACUS 单点计算在初始结构上直接错误。
- `downhill_check` 和较小 `maxstep` 对这类上坡/大步失稳有效，真实 ABACUS
  运行中能触发 ASE FIRE reset callback。

因此，用户报告的直接原因是当前 AutoNEB/FIRE 数值面上的优化失稳。

### 3.2 Refactor 后 AutoNEB wrapper 暴露的实现风险

代码审查和单元测试覆盖显示，ATST 的 ASE-native AutoNEB wrapper 在重构过程
中需要恢复几项 ASE 行为，否则会放大或制造 AutoNEB 运行风险：

- list-valued `fmax` / `maxsteps` 必须按 ASE AutoNEB 的 `many_steps` 语义
  调度，不能简单折叠成单个值。
- AutoNEB 子 NEB 结束后必须恢复 `store_E_and_F_in_spc` / `neb.distribute()`
  的 result-freezing 生命周期，保证 trajectory 中保存可读的能量和力。
- 串行、非共享 calculator 不能让多个 image 共用同一个 ABACUS 运行目录；
  否则文件后端 calculator 会互相覆盖。
- AutoNEB 子运行后不能激进删除 calculator 目录；失败诊断和后续读回需要
  保留输出。
- `iter_folder` 需要在写 history trajectory 前创建。

这些问题不是 issue #25 中每个失稳步的唯一原因，但它们属于 refactor 后
AutoNEB 稳定性和可复现性的必要修复项。

### 3.3 执行栈和参数差异造成的早期误判

2026-05-18 的中间报告曾判断当前分支不能 main-like 复现 main 历史结果。
这个判断来自当时的受限复算条件：旧 `xc: pbe` 在 ABACUS LTS 3.10.1 中不可
直接使用、部分 launcher/abacuslite 版本探测问题尚未修复、严格复算还未使用
最终的 full-node `mpi: 16`/`omp: 2` 配置跑完。

2026-05-19 的最终 examples-vs-main 报告覆盖了该中间结论。最终 run 使用：

- `fmax: [0.20, 0.05]`
- `maxsteps: 10000`
- 无稳定化 `optimizer_kwargs`
- `dft_functional: pbe` 替代 legacy `xc: pbe`
- `ks_solver: cusolver`
- `mpi: 16`
- `omp: 2`
- main-like SCF/output 参数和相同 pseudo/orbital 文件

在该条件下，job `433962` 完成并复现 main barrier、TS image、TS fmax 和 TS
结构。因此，早期“不能复现”是未完成最终参数/运行资源对齐前的阶段性结论，
不是最终根因。

## 4. 修复过程

### 4.1 AutoNEB 代码语义修复

相关实现集中在 `src/atst_tools/mep/autoneb.py`：

- `AbacusAutoNEB._execute_one_neb()` 保留 ASE 3.28.0 AutoNEB control flow，
  仅将内部 NEB 替换为 ATST 的 `AbacusNEB`。
- `fmax` 和 `maxsteps` 支持标量或两段 schedule：
  - 普通阶段使用第一个值；
  - climbing / `many_steps` 阶段使用第二个值。
- 子 NEB run 后重新绑定 `store_E_and_F_in_spc` 并执行 `neb.distribute()`，
  使 optimizer 结果冻结到 ASE `Atoms` 的 single-point calculator 中。
- 串行 ABACUS AutoNEB 按 image index 使用
  `autoneb_run/image_###` 目录，避免共享目录冲突。
- `restart: false` 时只清理 AutoNEB 自身 trajectory 和 iteration folder，
  不再在子运行后破坏 calculator 输出目录。

### 4.2 YAML 和 optimizer 配置治理

项目增加了受 schema 管控的 AutoNEB `optimizer_kwargs`：

```yaml
calculation:
  optimizer_kwargs:
    downhill_check: true
    maxstep: 0.05
```

这使用户可以在 YAML 中显式启用 ASE FIRE 的稳定化选项，而不需要在代码里
临时 patch。该选项适用于 issue #25 这类串行、多步 FIRE 子优化容易上坡的
调试/稳定性场景。

最终生产复算没有依赖这些稳定化 kwargs，而是回到 main-like 的
`fmax: [0.20, 0.05]` 和 `maxsteps: 10000`，这说明代码语义和运行参数对齐后
当前分支可以得到与 main 可比的 AutoNEB 结果。

### 4.3 ABACUS LTS 兼容性修复

严格 SAI 运行还暴露了 vendored `abacuslite` 的兼容性问题：

- ABACUS LTS 3.10.1 输出 `ABACUS v3.10.1` 风格版本 banner，旧 parser 只
  接受 legacy `ABACUS version ...`。
- Slurm 包装下 `mpirun ... abacus --version` 可能返回空 stdout。

项目已修复 `AbacusProfile.parse_version()` 和版本探测 fallback，使严格
`mpi` 运行能进入真实 ABACUS 计算阶段。这个修复本身不改变科学参数，但它是
完成 issue #25 复算验证的前置条件。

## 5. 验证证据

### 5.1 单元测试

相关单元测试覆盖：

- AutoNEB `optimizer_kwargs` schema/default 和 runner forwarding；
- issue #25 串行 AutoNEB schedule 语义：
  `n_simul=1`、`parallel=false`、`fmax=[1.00, 0.05]`、`maxsteps=10`；
- AutoNEB list-valued `fmax/maxsteps` 的普通阶段和 many-steps 阶段选择；
- 串行 ABACUS AutoNEB image 目录隔离；
- abacuslite ABACUS LTS version parser/fallback。

主要测试位置：

- `tests/unit/test_config.py`
- `tests/unit/test_workflows.py`
- `tests/unit/test_abacuslite_profile.py`

### 5.2 SAI issue #25 稳定性验证

早期 SAI validation 已确认当前示例 as-is 可以完成：

| Purpose | Job | Result |
| --- | ---: | --- |
| current example, unmodified config | `422164` | `COMPLETED 0:0`, reached `=== AutoNEB Calculation Finished ===` |
| `downhill_check` diagnostic | `422165` | captured 21 FIRE reset callback events, then cancelled after evidence capture |

这证明项目已经解决“示例直接 crash / 无法完成”的工程稳定性问题，也证明
`downhill_check` 在真实 ABACUS AutoNEB 中确实生效。

### 5.3 最终 main-like 复算验证

最终验收来自 `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md`。

`03_autoneb_Cy-Pt` final run:

| Item | Value |
| --- | --- |
| Job | `433962` |
| Partition/node | `4V100` / `4v100n35` |
| Runtime | `20:53:59` |
| ABACUS | LTS 3.10.1 |
| GPU solver | `ks_solver: cusolver` |
| AutoNEB fmax schedule | `[0.20, 0.05]` |
| Maxsteps | `10000` |
| Optimizer kwargs | none |
| Final barrier | `1.330070` eV |
| Main barrier | `1.327886` eV |
| TS fmax | `0.041272` eV/Ang |
| TS RMSD vs main | `0.004433` Ang |

该 run 是 issue #25 的最终关闭依据：它说明当前 AutoNEB 实现不只是能完成
smoke 示例，而且能在 main-like 生产设置下复现 main 分支 Cy-Pt AutoNEB
基线。

## 6. 残余说明

Issue #25 可以关闭，但以下边界需要保留在文档中：

- 如果用户刻意使用非常松的 `fmax: [1.00, 0.05]`、串行 `n_simul: 1`、多步
  FIRE 子优化且不启用稳定化 kwargs，复杂势能面上仍可能发生 optimizer
  失稳。这属于输入/优化器策略风险，不是当前已修复 wrapper 语义问题。
- main branch 历史脚本使用 MPI-launched Python；当前 `atst-dev` 环境中普通
  `mpirun python` 不暴露 ASE MPI world parallelism。最终 job `433962` 通过
  full-node ABACUS 并行完成科学结果验证，但不能据此宣称当前普通 CLI 已完全
  复刻 main 的 Python image-level scheduling 模型。
- ABACUS LTS 3.10.1 不接受部分 legacy 参数拼写，因此最终复算使用
  `dft_functional: pbe` 替代 `xc: pbe`，使用 GPU `cusolver` 替代 legacy CPU
  `genelpa` 路径。这些是当前 SAI 验证环境的合理兼容替换。

## 7. 建议 close response

```markdown
This has been resolved and validated.

The reported `fmax` growth was the actual ASE/FIRE maximum force during the
AutoNEB sub-optimization, not a YAML parsing issue. The failure mode was an
optimizer instability exposed by the serial `03_autoneb_Cy-Pt` settings.

During the fix we restored the ASE-native AutoNEB semantics in ATST-Tools:

- list-valued `fmax` / `maxsteps` schedules are now preserved;
- AutoNEB result freezing through `store_E_and_F_in_spc` / `neb.distribute()` is restored;
- serial non-shared ABACUS image calculations use isolated image directories;
- aggressive calculator directory cleanup was removed;
- `optimizer_kwargs` such as `downhill_check: true` and `maxstep: 0.05` are governed by YAML and forwarded to ASE FIRE.

The final strict validation for `03_autoneb_Cy-Pt` completed on SAI `4V100`
with ABACUS LTS 3.10.1 and `ks_solver: cusolver`:

- job: `433962`
- barrier: `1.330070` eV vs main `1.327886` eV, delta `+0.002184` eV
- TS image: `5`, same as main
- TS fmax: `0.041272` eV/Ang vs main `0.041975` eV/Ang
- TS RMSD vs main TS: `0.004433` Ang

So the current AutoNEB implementation no longer reproduces the issue #25
failure mode, and the current `03_autoneb_Cy-Pt` example reproduces the
main-branch AutoNEB result within a small numerical tolerance. Closing this as
fixed.
```

## 8. Reference artifacts

- Main issue: https://github.com/QuantumMisaka/atst-tools/issues/25
- Initial code/source assessment:
  `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md`
- SAI stability validation:
  `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md`
- ASE/ATST AutoNEB comparison:
  `docs/reports/ATST_TOOLS_NEB_ASE_COMPARISON_REVIEW_2026-05-18.md`
- Final examples-vs-main validation:
  `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md`
- Final strict run artifact:
  `temp_examples_strict_mainlike_runs_20260520_retry11/03_autoneb_Cy-Pt`
