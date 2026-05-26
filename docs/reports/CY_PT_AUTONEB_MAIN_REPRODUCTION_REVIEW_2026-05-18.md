# Cy-Pt AutoNEB Main-Branch Reproduction Review

**Date**: 2026-05-18  
**Case**: `examples/03_autoneb_Cy-Pt`  
**Question**: Can the current ATST-Tools branch perfectly reproduce the committed `main` branch Cy-Pt AutoNEB result when using the same settings?  
**Answer**: No. Strictly identical main-branch ABACUS input parameters do not run on the current SAI ABACUS 3.10.1 environment, and the nearest compatible probe already differs at the first real force evaluation.

## 2026-05-18 放宽复现标准后的完整实操更新

本轮按新的放宽标准重新验证：除 ABACUS 3.10.1 明确不接受的 `xc pbe` 外，其余输入尽量保持与 `main` 分支 `examples/Cy-Pt@graphene/autoneb/autoneb_run.py` 一致，包括：

- `fmax: [0.20, 0.05]`；
- `optimizer: FIRE`；
- 不显式设置 `downhill_check: true`；
- 不显式设置 `maxstep: 0.05`；
- `algorism: improvedtangent`；
- `climb: true`；
- `n_simul: 4`，`n_max: 10`；
- ABACUS 输入中保留 `ks_solver: genelpa`、`smearing_method: gaussian`、`scf_nmax: 100`、`init_wfc: atomic`、`init_chg: atomic`、`out_chg: -1` 等 main-like 参数。

实算工作区：

- `temp_sai_main_repro_validation/main_like_no_xc_full/`

提交任务：

| 项目 | 值 |
|---|---:|
| Slurm job | `423926` |
| SAI 分区 | `4V100` |
| ABACUS 模块 | `abacus/LTSv3.10.1-sm70-auto` |
| Python 环境 | `atst-dev` |
| 最终状态 | `CANCELLED`，手动停止 |
| 运行时长 | `01:56:36` |
| 停止原因 | iteration 001 内已出现持续、不可恢复的失稳趋势，继续运行只会消耗 GPU，不能形成正常收敛 AutoNEB 结果 |

该 run 没有进入正常 AutoNEB 加图阶段，最终只保持初始 6 个图像，没有得到 10 图像最终路径，因此不存在可用于和 main 分支比较的一位小数最终能垒。

iteration 001 的关键对比如下：

| Step | main energy/eV | main fmax/eV/Ang | current no-`xc` energy/eV | current no-`xc` fmax/eV/Ang |
|---:|---:|---:|---:|---:|
| 0 | -11864.578532 | 3.642360 | -11864.580888 | 3.666328 |
| 1 | -11864.782954 | 2.870872 | -11864.676929 | 3.636056 |
| 2 | -11865.029191 | 2.407401 | -11864.595118 | 5.468056 |
| 3 | -11865.183575 | 3.420662 | -11863.848133 | 8.958482 |
| 4 | -11865.149576 | 4.842759 | -11862.676794 | 11.684594 |
| 5 | -11865.185455 | 3.786428 | -11861.023906 | 13.730909 |
| 10 | -11865.304529 | 1.941274 | -11843.857635 | 22.169295 |
| 15 | -11865.405953 | 1.863983 | -11803.727789 | 75.613744 |
| 16 | -11865.411933 | 1.196430 | -11789.219298 | 105.380115 |

结论：

- 在当前 SAI `atst-dev` + ABACUS 3.10.1 + abacuslite/ASE-native ATST-Tools 环境中，放宽到“去掉非法 `xc pbe`，其他 main-like 输入保持一致”后，该 AutoNEB 案例仍不能正常收敛。
- 因为没有得到完整 10 图像最终路径，无法满足“最终能垒至少小数点后一位与 main 保持一致”的验收条件。
- 这不是普通的中间能量/fmax 小幅波动；当前 run 在第一轮 FIRE 中从 step 0 到 step 16 持续上坡，`fmax` 从 `3.666328` 增长到 `105.380115 eV/Ang`，而 main 同步阶段已降至 `1.196430 eV/Ang`。
- 这表明 main 历史结果依赖旧执行栈的组合行为：旧 ABACUS、旧 wrapper、旧运行模型以及对应输入解释。当前 ASE-native + abacuslite 环境若不使用已经验证有效的稳定化参数（例如 `downhill_check`/更小 `maxstep`），不能复现 main 的正常收敛路径。

因此，放宽“完美复现”后，本案例仍不能在当前项目框架下以 main-like 参数完成可接受的一位小数能垒复现。当前分支已经能通过 safer issue #25 设置稳定跑完该例子，但该设置不再是 main-like 输入。

## Deliverables

This report covers:

1. Code-level comparison of the `main` workflow and the current ASE-native workflow.
2. Real SAI calculations using strict and adapted main-like settings.
3. Quantitative comparison against the committed `main` branch AutoNEB trajectories.
4. Systematic source analysis for why perfect reproduction is not achievable in the current environment.

## Baseline Artifacts

The committed `main` result was extracted from:

- `main:examples/Cy-Pt@graphene/autoneb/run_autoneb000.traj` through `run_autoneb009.traj`
- `main:examples/Cy-Pt@graphene/autoneb/AutoNEB_iter/run_autoneb_log_iter*.log`

Local extracted baseline:

- `temp_sai_issue25_validation/main_baseline/`
- Analysis JSON: `temp_sai_issue25_validation/main_baseline/analysis.json`

Main baseline metrics:

| Metric | Value |
|---|---:|
| Image count | 10 |
| Highest-energy image | 5 |
| Forward barrier | 1.327886 eV |
| Max final-image force | 0.233195 eV/Ang |
| Iteration 001, step 0 energy | -11864.578532 eV |
| Iteration 001, step 0 fmax | 3.642360 eV/Ang |

## Main-Branch Settings

The legacy main script `examples/Cy-Pt@graphene/autoneb/autoneb_run.py` used:

```python
mpi = 16
omp = 4
neb_optimizer = FIRE
algorism = "improvedtangent"
climb = True
fmax = [0.20, 0.05]
n_simul = world.size
n_images = 10
```

ABACUS parameters included:

```python
{
    'calculation': 'scf',
    'nspin': 2,
    'xc': 'pbe',
    'ecutwfc': 100,
    'ks_solver': 'genelpa',
    'symmetry': 0,
    'vdw_method': 'd3_bj',
    'smearing_method': 'gaussian',
    'smearing_sigma': 0.001,
    'basis_type': 'lcao',
    'mixing_type': 'broyden',
    'scf_thr': 1e-6,
    'scf_nmax': 100,
    'cal_force': 1,
    'cal_stress': 1,
    'init_wfc': 'atomic',
    'init_chg': 'atomic',
    'out_stru': 1,
    'out_chg': -1,
    'out_mul': 0,
    'out_bandgap': 0,
    'out_wfc_lcao': 0,
    'efield_flag': 1,
    'dip_cor_flag': 1,
    'efield_dir': 1,
}
```

The main Slurm script launched Python under MPI:

```bash
mpirun -np $NSIMUL -machinefile slurm.hosts gpaw python autoneb_run.py
```

So `n_simul = world.size` was an MPI Python setting, not just a YAML integer.

## Current Workflow Differences

The current branch uses the ASE-native refactor around `ase.mep.AutoNEB` plus ATST's `AbacusNEB` compatibility class. Important differences are:

| Area | `main` branch | Current branch / SAI validation |
|---|---|---|
| Python workflow | legacy `abacus_autoneb.AbacusAutoNEB` script | `atst run config.yaml` through `AutoNEBRunner` |
| ABACUS interface | legacy `ase-abacus` style wrapper | vendored/environment `abacuslite` wrapper |
| ASE baseline | historical environment | ASE 3.28.0 in `atst-dev` |
| ABACUS version | main submit script says ABACUS 3.4.2 | SAI module `ABACUS v3.10.1` |
| Python parallelism | MPI-launched Python, `world.size = NSIMUL` | ordinary CLI is serial unless `atst run` itself is MPI-launched |
| Current example defaults | not applicable | current YAML uses `fmax: [1.00, 0.05]`, `maxsteps: 1`, `downhill_check: true`, `maxstep: 0.05` |

These differences mean the current repository can be tested against main, but it cannot be assumed to be bitwise or trajectory-identical by construction.

## SAI Runtime Tests

### Test 1: Current Example As-Is

Previously completed SAI validation:

| Item | Value |
|---|---:|
| Directory | `temp_sai_issue25_validation/current_example_run3` |
| Slurm job | `422164` |
| State | `COMPLETED 0:0` |
| Runtime | `01:10:10` |
| Result | `=== AutoNEB Calculation Finished ===` |

Current as-is metrics:

| Metric | Main committed result | Current as-is run | Difference |
|---|---:|---:|---:|
| Image count | 10 | 10 | 0 |
| Highest-energy image | 5 | 5 | 0 |
| Forward barrier | 1.327886 eV | 2.336211 eV | +1.008325 eV |
| Max final-image force | 0.233195 eV/Ang | 5.097634 eV/Ang | +4.864439 eV/Ang |
| Max image RMSD vs main | n/a | 0.211342 Ang | n/a |

This run proves the current example can finish, but it does not reproduce the main result because its YAML is intentionally a short-step stability example.

### Test 2: Strict Main-Parameter Probe

Workspace:

- `temp_sai_main_repro_validation/main_equiv_probe/`

This probe used main-like AutoNEB and ABACUS parameters, including `xc: pbe`, `ks_solver: genelpa`, `fmax: [0.20, 0.05]`, no `downhill_check`, and `maxsteps: 100`.

Slurm result:

| Item | Value |
|---|---:|
| Job | `423207` |
| State | `FAILED 1:0` |
| Runtime | `00:00:06` |

Failure evidence from ABACUS 3.10.1:

```text
THE PARAMETER NAME 'xc' IS NOT USED!
Bad parameter, please check the input parameters in file INPUT
```

Conclusion: strict main-branch ABACUS parameters are not accepted by the current production ABACUS environment. Therefore perfect reproduction under literally identical settings is impossible in this environment before any AutoNEB numerical question is reached.

### Test 3: Compatible Main-Like Probe Without `xc`

Workspace:

- `temp_sai_main_repro_validation/main_equiv_probe_no_xc/`

This probe removed only the ABACUS 3.10.1-incompatible `xc` key while preserving the other main-like AutoNEB and ABACUS settings. It was stopped after the first real FIRE force evaluation because the first logged value was already non-identical to the main baseline.

Slurm result:

| Item | Value |
|---|---:|
| Job | `423218` |
| State | `CANCELLED` after evidence capture |
| Runtime | `00:07:44` |

First FIRE record comparison:

| Quantity | Main baseline | Compatible probe | Difference |
|---|---:|---:|---:|
| Iteration 001 step 0 energy | -11864.578532 eV | -11864.580888 eV | -0.002356 eV |
| Iteration 001 step 0 fmax | 3.642360 eV/Ang | 3.666328 eV/Ang | +0.023968 eV/Ang |

Conclusion: even after applying the minimal compatibility edit required by ABACUS 3.10.1, the first real force evaluation is already not identical. Continuing the expensive full AutoNEB run cannot restore perfect reproduction because deterministic trajectory equality requires the initial evaluated energy/force state to match.

## Problem Source Analysis

### 1. Strict main input is not valid for current ABACUS

The main script's `xc: pbe` input is rejected by SAI ABACUS 3.10.1. This is an environment/API evolution issue, not an AutoNEB optimizer issue.

Impact:

- A literal same-parameter replay fails before SCF starts.
- Any runnable current-environment replay must modify at least one main parameter.
- Once a parameter is modified, the run is no longer a strict perfect reproduction test.

### 2. ABACUS executable and numerical backend changed

Main used an older ABACUS environment from its submit script (`abacus/3.4.2-icx`). Current SAI validation used `ABACUS v3.10.1`. Even with nominally equivalent physical settings, ABACUS version changes can alter defaults, parser behavior, SCF details, output precision, and force values.

The compatible probe shows a small but real first-step difference:

- energy differs by `2.356 meV`;
- fmax differs by `0.023968 eV/Ang`.

That is enough to rule out exact reproduction.

### 3. ABACUS interface changed

Main used a legacy `ase-abacus`/`abacus_autoneb` style interface. Current ATST-Tools uses abacuslite through an ASE-native calculator factory. The wrappers differ in:

- accepted key names and translation (`pp`/`basis` vs `pseudopotentials`/`basissets`);
- version handling;
- generated `INPUT`, `STRU`, and directory structure;
- calculator command construction.

The current wrapper is the intended project direction, but it is not a byte-for-byte replay of the legacy main branch wrapper.

### 4. Parallel execution model is different

Main launched Python itself under MPI, so `n_simul = world.size` was active. Current `atst run config.yaml` is serial unless the CLI is also MPI-launched. In ordinary SAI submissions current ATST prints:

```text
Notice: image-level AutoNEB parallelism requires MPI-launched atst run; running images serially.
```

This affects wall time and can affect file write ordering and calculator directory behavior. It is not the dominant source of the first force-evaluation mismatch, but it prevents claiming exact workflow equivalence.

### 5. Current example YAML is not configured as a main-result reproduction case

The committed current example intentionally uses safer issue #25 settings:

```yaml
fmax: [1.00, 0.05]
maxsteps: 1
optimizer_kwargs:
  downhill_check: true
  maxstep: 0.05
```

These are not the main branch settings. The as-is current example is a stability/smoke example, not a converged historical-result reproduction input.

## Final Conclusion

`examples/03_autoneb_Cy-Pt` cannot perfectly reproduce the committed `main` branch AutoNEB result in the current SAI `atst-dev` / ABACUS 3.10.1 / abacuslite environment.

The strongest evidence is:

1. Strict main parameters fail immediately because ABACUS 3.10.1 rejects `xc pbe`.
2. The minimally compatible main-like probe without `xc` runs, but its first real FIRE force evaluation already differs from the main baseline.
3. The full current example finishes, but its final barrier and forces differ substantially from main because its YAML is not a reproduction configuration.

Therefore the correct project interpretation is:

- current ATST-Tools resolves the issue #25 crash/stability problem for this case;
- current ATST-Tools should not claim numerical identity with the historical main branch Cy-Pt result;
- if exact historical reproducibility is required, it must be performed in the historical stack: legacy wrapper, old ABACUS version, old MPI launch model, and original input semantics.

## Reproduction Artifacts

- Main baseline: `temp_sai_issue25_validation/main_baseline/analysis.json`
- Current as-is SAI result: `temp_sai_issue25_validation/current_example_run3/analysis.json`
- Strict main-parameter failed probe: `temp_sai_main_repro_validation/main_equiv_probe/`
- Compatible no-`xc` probe: `temp_sai_main_repro_validation/main_equiv_probe_no_xc/`
- Main-compatible probe first log: `temp_sai_main_repro_validation/main_equiv_probe_no_xc/AutoNEB_iter/run_autoneb_log_iter001.log`
