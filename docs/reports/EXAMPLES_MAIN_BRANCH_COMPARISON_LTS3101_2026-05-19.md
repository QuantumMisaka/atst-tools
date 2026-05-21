# Examples vs Main Branch Validation - 2026-05-19

## 中文摘要

本报告是当前 `examples/` 与 `main` branch 已有过渡态案例结果的比对和
ABACUS LTS 3.10.1 实算验证记录。当前结论是部分正验证：`03_autoneb_Cy-Pt`
已在严格 main-like 参数下基于 ABACUS LTS 3.10.1、`cusolver` 和本服务器
`4V100` 全节点资源完整跑完，能垒与结构均与 main 结果可比；`08_d2s_Cy-Pt`
在修复 in-repository Fast IDPP 以复现 main/pymatgen IDPP 路径后，也已在
`4V100` 上完整跑完 rough NEB + Sella，rough NEB 与 main 结果可比。

关键严格复算结果：

- `03_autoneb_Cy-Pt`：`fmax: [0.20, 0.05]`、无稳定化 optimizer kwargs、
  `maxsteps: 10000`、`dft_functional: pbe`、`mpi: 16`、`omp: 2`、
  `ks_solver: cusolver`。作业 `433962` 在 `4V100` 节点 `4v100n35` 上完整
  完成，耗时 `20:53:59`。最终势垒为 `1.330070` eV，main 为 `1.327886`
  eV，偏差 `+0.002184` eV；TS image 同为 `5`，TS fmax 为 `0.041272`
  eV/Ang，TS-to-main-TS RMSD 为 `0.004433` Ang，结果可比。
- `08_d2s_Cy-Pt`：切换为 main-like `method: sella`，legacy `xc` 改为
  `dft_functional`，legacy `gau` 改为 LTS 支持的 `gauss`，`ks_solver:
  cusolver`。早期作业 `428893`/`429068` 显示 rough NEB 跑飞。离线几何
  对比确认根因是 `Fast_IDPPSolver` 未复现 main 的
  `pymatgen.IDPPSolver(sort_tol=0.5)` NEB-like IDPP 路径；修复后，作业
  `429504` 在 `4V100` 上完成，first-band rough barrier `2.678812` eV
  （main `2.678795` eV，差 `+0.000017` eV），最后 rough band barrier
  `1.714806` eV（main 约 `1.715682` eV，差 `-0.000876` eV），Sella
  最终 fmax `0.039662` eV/Ang。

因此，本报告交付的是部分正验证与剩余问题记录：`03_autoneb_Cy-Pt` 已完成
main-like AutoNEB 实算并满足 main branch 可比性；`08_d2s_Cy-Pt` 的 D2S
路径已可复现 main rough NEB 并完成 Sella。更广义 examples 审计中的剩余
不可比案例仍集中在 `01/02/04/05`。

## Status

This is a completed comparison report with a partial positive reproduction result. The
examples were traversed, comparable main branch baselines were measured, key
parameters were aligned as far as ABACUS LTS 3.10.1 supports, strict `4V100`
reruns were submitted, and the resulting trajectories were analyzed. The
`03_autoneb_Cy-Pt` AutoNEB case now completes under ABACUS LTS 3.10.1 with
`cusolver` and is comparable to main. The `08_d2s_Cy-Pt` rough NEB path also
reproduces main after the Fast IDPP fix and the workflow completed through
Sella. The full examples audit still has non-comparable evidence for
`01/02/04/05`.

Goal status decision for the broader all-examples audit: do not mark the active
goal complete. The immediate `03_autoneb_Cy-Pt` acceptance condition is now
satisfied, and `08` is reproduced, but the broader audit still records
non-comparable results for `01/02/04/05`.

## Scope

This report records the comparison between the current curated `examples/` and
the committed `main` branch transition-state examples. The validation target was
SAI `4V100`, `atst-dev`, and `abacus/LTSv3.10.1-sm70-auto`. For GPU runs, LCAO
ABACUS inputs used `ks_solver: cusolver`.

Repository state used for this report:

- Current working branch: `develop`
- Current HEAD: `335d84ee107a69e7098b16618fa536cd9924bd40`
- Main baseline commit: `47c513f691dabc71ac3604e1917e174b71a372ae`
- Main artifacts extracted under `temp_examples_main_20260519/examples`

## Main Baselines

The `main` branch artifacts were extracted under
`temp_examples_main_20260519/examples`. The comparable transition-state cases
are:

| Current case | Main baseline | Main metric |
| --- | --- | --- |
| `01_neb_Li-Si` | `Li-diffu-Si/neb/neb_latest.traj` | forward barrier `0.618327` eV; TS fmax `0.047675` eV/Ang |
| `02_neb_H2-Au` | `H2-Au111/neb/neb_latest.traj` | forward barrier `1.120780` eV; TS fmax `0.019972` eV/Ang |
| `03_autoneb_Cy-Pt` | `Cy-Pt@graphene/autoneb/run_autoneb000-009.traj` | forward barrier `1.327886` eV; TS image `5` |
| `04_dimer_CO-Pt` | `CO-Pt111/dimer/run_dimer.traj` | converged Dimer trajectory, final fmax `0.048175` eV/Ang |
| `05_sella_H2-Au` | `H2-Au111/sella/run_sella.traj` | converged Sella trajectory, final fmax `0.048256` eV/Ang |
| `08_d2s_Cy-Pt` | `Cy-Pt@graphene/neb2sella/*` | rough NEB plus Sella refinement |

Non-TS examples (`06_relax`, `07_vibration`, `11_vibration_ideal_gas`) and the
current gas-phase `10_irc_H2` do not have a like-for-like main-branch
barrier/TS baseline.

Current `examples/` inventory:

| Current case | Current workflow type | Main TS/barrier baseline | Re-run trigger/status |
| --- | --- | --- | --- |
| `01_neb_Li-Si` | NEB | `Li-diffu-Si/neb/neb_latest.traj` | Triggered by `>0.1` eV mismatch; production and stabilized reruns diverged or stagnated. |
| `02_neb_H2-Au` | NEB | `H2-Au111/neb/neb_latest.traj` | Triggered by `>0.1` eV mismatch; production convergence was not reached. |
| `03_autoneb_Cy-Pt` | AutoNEB | `Cy-Pt@graphene/autoneb/run_autoneb000-009.traj` | Triggered and rerun strictly with main-like settings in job `433962`; completed and comparable. |
| `04_dimer_CO-Pt` | Dimer | `CO-Pt111/dimer/run_dimer.traj` | Triggered because current smoke output is not a converged TS; full rerun `426978` did not yield readable comparable energy/force trajectory data. |
| `05_sella_H2-Au` | Sella | `H2-Au111/sella/run_sella.traj` | Triggered because current smoke output is far above main fmax; full rerun `426977` remained non-converged. |
| `06_relax_H2-Au` | Relaxation | None for TS/barrier comparison | Out of scope for the `>0.1` eV barrier/TS trigger; config was still traversed and schema-load checked. |
| `07_vibration_H2-Au` | Vibration/thermochemistry | None for TS/barrier comparison | Out of scope for the `>0.1` eV barrier/TS trigger; config was still traversed and schema-load checked. |
| `08_d2s_Cy-Pt` | NEB-to-Sella | `Cy-Pt@graphene/neb2sella/*` | Triggered and rerun strictly with main-like rough NEB/Sella settings in job `428893`; rerun again in clean retry job `429068` after D2S `scale_fmax/idpp_*` alignment. Rough NEB ran away and remained non-comparable. |
| `10_irc_H2` | IRC | No like-for-like gas-phase main case | Out of scope for the barrier/TS trigger; config was still traversed and schema-load checked. |
| `11_vibration_ideal_gas_H2` | Vibration/ideal gas thermochemistry | None for TS/barrier comparison | Out of scope for the `>0.1` eV barrier/TS trigger; config was still traversed and schema-load checked. |

## Parameter Alignment

Applied in current configs:

- `02_neb_H2-Au`: changed `fmax` from smoke `0.80` to main-like `0.05`; added `dft_functional: pbe`.
- `03_autoneb_Cy-Pt`: kept required `fmax: [0.20, 0.05]`; replaced legacy `xc` semantics with `dft_functional: pbe`; restored GPU `ks_solver: cusolver`; removed stabilization-only optimizer kwargs from the strict run; restored the ASE AutoNEB default-scale `maxsteps: 10000`. The completed `4V100` validation used `mpi: 16` and `omp: 2`; main used `omp: 4`, but on the SAI `4V100` node that would oversubscribe the available CPU threads for `mpi: 16`. A diagnostic `mpi: 16`, `omp: 4` launch emitted ABACUS' correctness warning that total threads exceeded hardware availability, so the completed validation used `omp: 2` while keeping the scientific AutoNEB and ABACUS inputs aligned.
- `01/02/04/05/08`: replaced smoke `max_steps: 1` with production limits.
- `08_d2s_Cy-Pt`: changed `method: sella` to match the main Cy-Pt `neb2sella` baseline; mapped legacy unsupported `xc: pbe` to `dft_functional: pbe`; kept LTS-supported `smearing_method: gauss` for legacy `gau`; aligned `scf_thr`, stress, initialization, and output switches with the main script where supported. A later audit found additional ASE rough-path settings: main's `scale_fmax=1.0` and IDPP controls comparable to `maxiter=5000`, `gtol=1e-3`. The D2S schema/runner now exposes `neb.scale_fmax`, `neb.idpp_maxiter`, and `neb.idpp_tol`, and the current example config sets them to `1.0`, `5000`, and `1e-3`. The first strict `428893` trajectory predates this final rough-path alignment; clean retry job `429068` was launched from a stale-output-free directory with these settings and still ran away over ten rough NEB bands.
- Added governed `optimizer_kwargs` support for ordinary NEB, AutoNEB, and D2S rough NEB so stabilization can be expressed in YAML instead of code patches. Added governed `scale_fmax`, `idpp_maxiter`, and `idpp_tol` support for D2S rough DyNEB/path generation to match legacy scripts where the refactored in-repository IDPP path can express equivalent controls.

Pseudopotential/orbital names are consistent with main for the compared systems:
`Li/Si`, `H/Au`, `C/H/Pt`, and `C/O/Pt` use the same ONCV PBE UPF and numerical
orbital filenames.

The strict run data directory contains the required files used by the comparable
examples: `Li_ONCV_PBE-1.2.upf`, `Si_ONCV_PBE-1.2.upf`,
`H_ONCV_PBE-1.0.upf`, `C_ONCV_PBE-1.0.upf`, `O_ONCV_PBE-1.0.upf`,
`Au_ONCV_PBE-1.0.upf`, `Pt_ONCV_PBE-1.0.upf`, and the matching
`*_gga_*_100Ry_*.orb` files. The strict Cy-Pt configs reference the same
`C/H/Pt` pseudo/orbital filenames as `main` branch `autoneb_run.py` and
`neb2sella_abacus.py`.

Actual generated `INPUT` files were checked for the strict Cy-Pt reruns:

- `03_autoneb_Cy-Pt`: `temp_examples_strict_mainlike_runs_20260520_retry11/03_autoneb_Cy-Pt/autoneb_run/image_001/INPUT` matches the main `autoneb_run.py` SCF settings for `nspin`, `ecutwfc`, `basis_type`, `vdw_method`, `symmetry`, `scf_thr`, `scf_nmax`, `smearing_method`, force/stress flags, initialization, output switches, dipole correction, pseudo files, and orbital files. Intentional differences are `ks_solver: cusolver` for GPU and `dft_functional: pbe` replacing legacy `xc: pbe`.
- `08_d2s_Cy-Pt`: `temp_examples_strict_mainlike_runs_20260519_retry3/08_d2s_Cy-Pt/run_d2s/NEB/image_001/INPUT` matches the main `neb2sella_abacus.py` SCF settings for rough NEB, with intentional replacements `ks_solver: cusolver`, `dft_functional: pbe`, and LTS-supported `smearing_method: gauss` for the legacy `gau` spelling.

## Real-Run Evidence

| Attempt | Jobs | Result |
| --- | --- | --- |
| 4-GPU script submission | `426575-426580` | Cancelled immediately by Slurm before user script; no calculation evidence. |
| Single-GPU wrap, main-like long settings | `426607-426612` | Started real ABACUS work; cancelled after `00:32:39` because `01_neb_Li-Si` had diverged badly. |
| NEB with `FIRE(downhill_check=True, maxstep=0.05)` | `426778`, `426779` | `01_neb_Li-Si` did not diverge but stagnated near the initial path: barrier `0.757774` eV and fmax about `0.95` eV/Ang after 42 bands; cancelled. |
| NEB with `FIRE(maxstep=0.05)` only | `426919` | `01_neb_Li-Si` diverged again: barrier `4.221144` eV and fmax `3-4` eV/Ang after 15 minutes; cancelled. |
| Full Sella rerun for `05_sella_H2-Au` | `426977` | Ran on `4V100` for `02:02:46`; `sella.traj` reached 53 frames but stayed near fmax `0.299` eV/Ang, far from the main final fmax `0.048` eV/Ang; cancelled as non-convergent. |
| Full Dimer rerun for `04_dimer_CO-Pt` | `426978` | Ran on `4V100` for `04:03:45`; `dimer.traj` reached 7 frames but still exposed no ASE-readable energy/force results. The job was cancelled because it could not reach a comparable main Dimer TS in a reasonable validation window. |
| Main-aligned AutoNEB rerun for `03_autoneb_Cy-Pt` | `428493` | Ran on `4V100` for `00:36:13`; with `fmax: [0.20, 0.05]`, `dft_functional: pbe`, `ks_solver: cusolver`, and conservative FIRE kwargs, the six-image stage remained at barrier `2.124448` eV with TS fmax `4.740` eV/Ang. Main is `1.327886` eV with TS fmax `0.041975` eV/Ang. Cancelled as non-comparable. |
| Main-aligned D2S Sella rerun for `08_d2s_Cy-Pt` | `428494` | Ran on `4V100` for `00:36:10`; endpoint optimization completed immediately, but rough NEB stayed at barrier `5.656523` eV with TS fmax `4.246` eV/Ang after two bands. Main rough NEB baseline is about `2.678795` eV. No Sella refinement was reached before cancellation as non-comparable. |
| Strict main-like AutoNEB launch diagnostics | `428760`, `428816`, `428878` | These failed before useful optimization because strict `mpi: 4` exposed launcher/setup issues: empty `mpirun ... --version` stdout in abacuslite, Slurm `--ntasks=1` slot mismatch, and a temporary run directory missing `examples/data`. These were corrected before the final strict run. |
| Strict main-like AutoNEB rerun for `03_autoneb_Cy-Pt` | `428892` | Ran on `4V100` for `00:47:12` with no optimizer kwargs, `maxsteps: 10000`, `mpi: 4`, copied pseudo/orbital data, `dft_functional: pbe`, and `ks_solver: cusolver`. After at least two internal image updates, the six-image stage was still at barrier `2.229768` eV with TS fmax `5.573` eV/Ang. Main is `1.327886` eV with TS fmax `0.041975` eV/Ang. Cancelled as non-comparable. |
| Completed full-node AutoNEB rerun for `03_autoneb_Cy-Pt` | `433962` | Completed on `4V100` node `4v100n35` in `20:53:59` from `temp_examples_strict_mainlike_runs_20260520_retry11/03_autoneb_Cy-Pt`. The run used `fmax: [0.20, 0.05]`, no optimizer kwargs, `maxsteps: 10000`, `mpi: 16`, `omp: 2`, matching pseudo/orbital files, `dft_functional: pbe`, and `ks_solver: cusolver`. ABACUS output identified `ABACUS v3.10.1`, GPU execution on `Tesla V100-SXM2-32GB`, and `DiagoCusolver`, with no CPU oversubscription warning. Final barrier is `1.330070` eV vs main `1.327886` eV (`+0.002184` eV), TS image is `5`, TS fmax is `0.041272` eV/Ang vs main `0.041975`, and TS-to-main-TS RMSD is `0.004433` Ang. |
| Strict main-like D2S launch diagnostics | `428761`, `428817`, `428879` | These failed before useful optimization for the same launcher/setup class plus direct use of legacy `smearing_method: gau`, which ABACUS LTS 3.10.1 rejects. The strict rerun used the LTS-supported synonym `gauss`. |
| Strict main-like D2S Sella rerun for `08_d2s_Cy-Pt` | `428893` | Ran on `4V100` for `01:07:59` with `mpi: 4`, `method: sella`, main-like ABACUS parameters, `dft_functional: pbe`, `smearing_method: gauss`, and `ks_solver: cusolver`. The newly written rough NEB trajectory had barrier `5.655415` eV and TS fmax `4.367` eV/Ang, versus main rough NEB about `2.678795` eV. Cancelled before Sella refinement because the rough path was already non-comparable. |
| Clean strict D2S retry after `scale_fmax/idpp_*` alignment | `429068` | Ran on `4V100` node `4v100n09` for `03:32:23` from `temp_examples_strict_mainlike_runs_20260519_retry5/08_d2s_Cy-Pt`, a clean directory containing only config, inputs, submit script, and copied data. Endpoint optimizations completed immediately (`IS` fmax `0.0441`, `FS` fmax `0.0487` eV/Ang). After `scale_fmax=1.0` and IDPP `5000/1e-3` alignment, rough NEB still diverged: ten bands were written by `23:03:03`, with barrier rising from `5.655415` to `23.248852` eV and TS fmax rising to `26.143` eV/Ang. The latest checkpoint is `+20.570057` eV above the main rough NEB baseline. The job was cancelled after this runaway trend was clear; no Sella trajectory was produced. |
| Clean strict D2S retry after Fast IDPP parity fix | `429504` | Completed on `4V100` node `4v100n07` in `06:00:52` from `temp_examples_strict_mainlike_runs_20260520_retry7/08_d2s_Cy-Pt`. Endpoint optimizations completed immediately (`IS` fmax `0.0441`, `FS` fmax `0.0487` eV/Ang). The first rough NEB band reproduced main: barrier `2.678812` eV, TS image `6`, TS fmax `3.531348` eV/Ang. The final rough NEB band reached barrier `1.714806` eV, TS image `6`, TS fmax `0.874700` eV/Ang, close to the main last-band rough barrier about `1.715682` eV. Sella then converged with final fmax `0.039662` eV/Ang and final TS energy `-11865.557601` eV. |

The first full-alignment long run showed the severity of the mismatch for
`01_neb_Li-Si`: after 180 frames the latest band had a barrier of about
`231.323` eV and internal-image fmax values above `70` and `120` eV/Ang. This
was stopped to avoid wasting GPU time.

Key Slurm accounting records were checked directly with:

```bash
sacct -j 426607,426608,426609,426610,426611,426612,426778,426779,426919,426977,426978,428493,428494,428892,428893,429068,429504,433962 \
  --format=JobID,JobName%28,Partition,State,ExitCode,Elapsed,NodeList -P
```

The primary jobs above all ran in partition `4V100`; representative strict and
long-run records were:

| JobID | JobName | State | Elapsed | Node |
| --- | --- | --- | --- | --- |
| `426607` | `atst-01_neb_Li-Si-align` | `CANCELLED by 1478400036` | `00:32:40` | `4v100n34` |
| `426977` | `atst-05-sella-align` | `CANCELLED by 1478400036` | `02:02:46` | `4v100n34` |
| `426978` | `atst-04-dimer-align` | `CANCELLED by 1478400036` | `04:03:45` | `4v100n33` |
| `428892` | `atst-03-autoneb-strict4` | `CANCELLED by 1478400036` | `00:47:12` | `4v100n09` |
| `428893` | `atst-08-d2s-strict4` | `CANCELLED by 1478400036` | `01:07:59` | `4v100n20` |
| `429068` | `atst-08-d2s-clean5` | `CANCELLED by 1478400036` | `03:32:23` | `4v100n09` |
| `429435` | `atst-08-order-sp` | `COMPLETED` | `00:03:26` | `4v100n07` |
| `429445` | `atst-main-img-sp` | `COMPLETED` | `00:03:18` | `4v100n07` |
| `429504` | `atst-08-d2s-idpp7` | `COMPLETED` | `06:00:52` | `4v100n07` |
| `433962` | `atst-03-autoneb-r11` | `COMPLETED` | `20:53:59` | `4v100n35` |

These states confirm which strict reruns were stopped after quantitative
non-comparability checks and which completed naturally. Job `429504` is the
successful D2S confirmation after the IDPP parity fix.

For `08_d2s_Cy-Pt`, stale `dimer.traj` and `run_d2s/DIMER` files were present in
the reused diagnostic directory from earlier May 10-12 runs. They are not part
of the May 19 strict `method: sella` result: `neb_rough.traj` was freshly written
at `2026-05-19 18:34`, while `dimer.traj` and `run_d2s/DIMER/INPUT` were dated
`2026-05-12` and `2026-05-10`, respectively. No new Sella trajectory was produced
before job `428893` was cancelled.

An additional image-level MPI diagnostic was submitted as job `429055` on
partition `4V100`. It ran for one second on `4v100n33` and executed
`mpirun -np 4 python -c 'from ase.parallel import world; print(...)'`. The output
was four lines of `rank=0 size=1`, and `conda run -n atst-dev python -c
"import importlib.util; print(importlib.util.find_spec('mpi4py'))"` returned
`None`. This means the current `atst-dev` environment does not expose ASE MPI
world parallelism through plain `mpirun python`. The main AutoNEB script used
`mpirun -np $NSIMUL gpaw python autoneb_run.py`, so its image-level AutoNEB
parallelism was not fully reproduced by the current single-process `atst-run`
strict jobs. This is an ASE execution-stack difference, separate from the ABACUS
`INPUT` parameter alignment documented above.

## Comparison

| Case | Current evidence | Difference vs main |
| --- | --- | --- |
| `01_neb_Li-Si` | Smoke run barrier about `0.7539` eV; production long run diverged; conservative FIRE stagnated at `0.7578` eV. | At least `+0.135` eV for the best available current run; production path not comparable. |
| `02_neb_H2-Au` | Smoke run stopped after one step; latest complete band barrier about `2.848` eV; first stabilized band still near `2.896` eV. | About `+1.73` eV from smoke artifact; production convergence not reached. |
| `03_autoneb_Cy-Pt` | Completed rerun `433962` used `fmax: [0.20, 0.05]`, no optimizer kwargs, `maxsteps: 10000`, `dft_functional: pbe`, matching pseudo/orbital files, `mpi: 16`, `omp: 2`, and `ks_solver: cusolver`; the full AutoNEB run finished on `4V100`. | Barrier `1.330070` eV vs main `1.327886` eV (`+0.002184` eV); TS image `5` in both; TS fmax `0.041272` vs main `0.041975` eV/Ang; TS RMSD `0.004433` Ang. Comparable. |
| `04_dimer_CO-Pt` | Current smoke `max_steps: 1` trajectory has no readable ASE energy/force results; main has a converged Dimer trajectory. Full rerun `426978` ran for `04:03:45` and reached 7 frames, still without readable trajectory energies/forces. | Not comparable as a converged Dimer TS. |
| `05_sella_H2-Au` | Current smoke result final fmax about `0.372` eV/Ang; full rerun `426977` remained near fmax `0.299` eV/Ang after `02:02:46`. Main final fmax is `0.048` eV/Ang. | Not comparable as a converged TS. |
| `08_d2s_Cy-Pt` | Config was switched to main-like `method: sella`; strict reruns `428893` and `429068` first exposed a non-comparable rough path. After replacing the in-repository Fast IDPP L-BFGS approximation with a pymatgen-compatible NEB-like IDPP update, clean retry `429504` completed rough NEB and Sella. | First rough band barrier `2.678812` eV vs main `2.678795` eV (`+0.000017` eV). Final rough band barrier `1.714806` eV vs main last-band rough barrier about `1.715682` eV (`-0.000876` eV). Sella converged to fmax `0.039662` eV/Ang. Comparable for the rough NEB path and complete through Sella. |

For `03_autoneb_Cy-Pt`, earlier short strict runs such as job `428892` were not
acceptance evidence because they were cancelled while AutoNEB was still building
the band. The completed full-node run `433962` changes that conclusion: the
final 10-image band has relative energies and forces very close to the main
band. The largest internal-image fmax is `0.234444` eV/Ang, matching the main
band-level force scale (`0.233195` eV/Ang) and reflecting the main/AutoNEB final
stage behavior, while the TS image itself is converged below the final `0.05`
eV/Ang target.

For `08_d2s_Cy-Pt`, an additional post-cancellation diagnostic compared the
main `neb_images.traj` band with clean retry `429068`. The clean retry first
band is geometrically close to the main NEB band: same-index coordinate RMSDs
against the main first band average about `0.097` Ang, with endpoint RMSD zero.
Despite this, its first-band relative energies are already much higher:

- Main first band relative energies, eV:
  `[0.000, 0.236, 0.765, 1.376, 1.989, 2.463, 2.679, 2.545, 2.090, 1.425, 0.747, 0.395]`
- Clean retry `429068` first band relative energies, eV:
  `[0.000, 3.055, 3.627, 4.346, 5.070, 5.343, 5.439, 5.655, 5.125, 4.546, 4.143, 0.395]`

At this stage, this suggested either a geometry/path difference or a
calculator/execution-stack difference on similar images. A later single-image
diagnostic resolved this ambiguity for the exact main geometry: job `429445`
reran main first-band TS image `6` with ABACUS LTS 3.10.1, `cusolver`, and the
patched abacuslite writer. The stored main energy was `-11864.151250632500` eV
and the LTS recalc energy was `-11864.151272551300` eV, a difference of only
`-2.19e-5` eV; fmax changed from `3.531432` to `3.531366` eV/Ang. Therefore the
remaining D2S mismatch was not a multi-eV calculator error on the exact main
geometry. It was concentrated in how the current path geometry was generated
before entering rough NEB.
The endpoint structures themselves also match closely: comparing current
`examples/08_d2s_Cy-Pt/inputs/init.stru` and `final.stru` to main
`STRU_IS`/`STRU_FS` gives identical atom ordering and formulas, with initial
endpoint RMSD `0.00054` Ang and final endpoint RMSD `4e-6` Ang. The current
`atst-dev` environment does not have `pymatgen` installed, so main's exact
`IDPPSolver.from_endpoints(..., sort_tol=0.5)` implementation cannot be invoked
directly without changing the environment. A separate `atst` environment was
used only for an offline geometry diagnostic: pymatgen IDPP generated images
matched main `neb_images.traj` first-band images within about `5e-6` to
`1.3e-5` Ang, while the old `Fast_IDPPSolver` differed by about `0.17-0.21`
Ang on intermediate images. The in-repository `Fast_IDPPSolver` was therefore
rewritten to use the same NEB-like IDPP update scheme and nearest-image
translation handling as pymatgen, without adding a runtime pymatgen dependency.
After this fix, the same offline comparison gave zero RMSD between pymatgen IDPP
and `Fast_IDPPSolver` images at printed precision.

One generated-file difference was identified in the `429068` inputs and fixed
for future runs: vendored `abacuslite` had been sorting atoms/species
alphabetically when writing `STRU`, so clean retry `429068` wrote species blocks
as `C,H,Pt`, while main's saved `STRU_IS`/`STRU_FS` order is `C,Pt,H`.
The vendored writer/template now preserves first-occurrence species order from
the ASE `Atoms` object, so a Cy-Pt `C...Pt,H...` structure writes `C,Pt,H`.
This change aligns generated files more closely with main. A single-image
`4V100` diagnostic job (`429435`) then reran the clean retry first-band TS image
with the patched `C,Pt,H` writer order. It reproduced the pre-fix `C,H,Pt`
result exactly within printed precision: energy `-11861.174648320401` eV and
fmax `4.367015476685` eV/Ang. Therefore species block order is not the source of
the D2S multi-eV barrier mismatch.

Key strict-vs-main metrics:

```json
{
  "03_autoneb_Cy-Pt": {
    "main_forward_barrier_eV": 1.327886,
    "strict_forward_barrier_eV": 1.330070,
    "barrier_delta_eV": 0.002184,
    "main_ts_index": 5,
    "strict_ts_index": 5,
    "strict_ts_fmax_eV_per_A": 0.041272,
    "strict_band_fmax_eV_per_A": 0.234444,
    "main_ts_fmax_eV_per_A": 0.041975,
    "main_band_fmax_eV_per_A": 0.233195,
    "strict_ts_to_main_ts_rmsd_A": 0.004433,
    "strict_job_id": 433962,
    "strict_elapsed": "20:53:59",
    "comparable": true
  },
  "08_d2s_Cy-Pt_rough_neb": {
    "main_forward_barrier_eV": 2.678795,
    "strict_forward_barrier_eV": 5.655415,
    "barrier_delta_eV": 2.976620,
    "strict_ts_index": 7,
    "strict_ts_fmax_eV_per_A": 4.367015,
    "clean_retry_429068_first_band_forward_barrier_eV": 5.655415,
    "clean_retry_429068_first_band_ts_index": 7,
    "clean_retry_429068_first_band_ts_fmax_eV_per_A": 4.367015,
    "clean_retry_429068_band2_forward_barrier_eV": 5.793211,
    "clean_retry_429068_band2_ts_index": 7,
    "clean_retry_429068_band2_ts_fmax_eV_per_A": 3.910769,
    "clean_retry_429068_band3_forward_barrier_eV": 6.268313,
    "clean_retry_429068_band3_ts_index": 7,
    "clean_retry_429068_band3_ts_fmax_eV_per_A": 4.582207,
    "clean_retry_429068_band4_forward_barrier_eV": 7.112310,
    "clean_retry_429068_band4_ts_index": 7,
    "clean_retry_429068_band4_ts_fmax_eV_per_A": 5.605073,
    "clean_retry_429068_band5_forward_barrier_eV": 8.366226,
    "clean_retry_429068_band5_ts_index": 7,
    "clean_retry_429068_band5_ts_fmax_eV_per_A": 7.036022,
    "clean_retry_429068_band6_forward_barrier_eV": 10.081971,
    "clean_retry_429068_band6_ts_index": 7,
    "clean_retry_429068_band6_ts_fmax_eV_per_A": 9.135216,
    "clean_retry_429068_band10_forward_barrier_eV": 23.248852,
    "clean_retry_429068_band10_ts_index": 7,
    "clean_retry_429068_band10_ts_fmax_eV_per_A": 26.143183,
    "clean_retry_429068_first_band_mean_rmsd_to_main_first_band_A": 0.097231,
    "current_vs_main_init_endpoint_rmsd_A": 0.000539,
    "current_vs_main_final_endpoint_rmsd_A": 0.000004,
    "species_order_single_image_job": 429435,
    "species_order_single_image_energy_delta_eV": 0.0,
    "species_order_single_image_fmax_delta_eV_per_A": 0.0,
    "main_image6_lts_recalc_job": 429445,
    "main_image6_lts_recalc_energy_delta_eV": -0.0000219188,
    "main_image6_lts_recalc_fmax_delta_eV_per_A": -0.0000663593,
    "idpp_fixed_job": 429504,
    "idpp_fixed_state": "COMPLETED",
    "idpp_fixed_elapsed": "06:00:52",
    "idpp_fixed_first_band_forward_barrier_eV": 2.678812,
    "idpp_fixed_first_band_barrier_delta_eV": 0.000017,
    "idpp_fixed_first_band_ts_index": 6,
    "idpp_fixed_first_band_ts_fmax_eV_per_A": 3.531348,
    "idpp_fixed_last_band_forward_barrier_eV": 1.714806,
    "idpp_fixed_last_band_barrier_delta_eV": -0.000876,
    "idpp_fixed_last_band_ts_index": 6,
    "idpp_fixed_last_band_ts_fmax_eV_per_A": 0.874700,
    "idpp_fixed_sella_frames": 73,
    "idpp_fixed_sella_final_energy_eV": -11865.557601,
    "idpp_fixed_sella_final_fmax_eV_per_A": 0.039662,
    "comparable": true
  }
}
```

## Completion Audit

| Requirement | Evidence | Status |
| --- | --- | --- |
| Traverse current `examples/` | Current configs found for `01`-`08`, `10`, and `11`; the inventory table classifies each case and identifies which have like-for-like TS/barrier baselines. | Covered. |
| Compare to main branch existing results | Main trajectories extracted under `temp_examples_main_20260519/examples`; metrics listed above. | Covered for comparable cases. |
| Align ASE and ABACUS parameters where differences exceed `0.1` eV | `03` and `08` strict runs remove stabilization-only kwargs, use main-like fmax/method/maxsteps/SCF settings, and use supported replacements for legacy `xc`/`gau`. | Covered as far as ABACUS LTS 3.10.1 supports. |
| Use ABACUS LTS 3.10.1 on SAI `4V100` with GPU `cusolver` | Slurm jobs loaded `abacus/LTSv3.10.1-sm70-auto`; LCAO runs used `ks_solver: cusolver`; `03` job `433962` used full-node `mpi: 16`, `omp: 2`, and 4 V100 GPUs. | Covered. |
| Ensure calculations complete and obtain comparable results | Multiple production/strict runs were launched. `03_autoneb_Cy-Pt` job `433962` completed AutoNEB and reproduced the main barrier/TS structure. `08_d2s_Cy-Pt` job `429504` completed rough NEB + Sella and reproduced the main rough NEB barriers. `04` and `05` still do not have comparable completed TS results under the current strict validation evidence. | Partially achieved for the whole audit; achieved for `03` and `08`. |
| Deliver Markdown comparison/test report | This file records configs, Slurm jobs, metrics, failures, and verification. | Covered. |

Prompt-to-artifact checklist:

| Prompt item | Concrete artifact or command | Evidence |
| --- | --- | --- |
| "逐个遍历 examples 中的案例" | `find examples -maxdepth 2 -name config.yaml` | Current examples include `01`-`08`, `10`, and `11`; non-TS/no-like-for-like cases are explicitly identified in this report. |
| "与 main branch 已有案例计算结果比较" | `temp_examples_main_20260519/examples` plus ASE trajectory analysis | Main metrics for `01`-`05` and `08` are listed in the Main Baselines table. |
| "能垒差别大于 0.1 eV 时对齐参数" | Current `examples/*/config.yaml`; generated strict-run `INPUT` files | Parameter Alignment and actual generated `INPUT` checks document ASE/ABACUS alignment and supported legacy replacements. |
| "ks_solver 采用 cusolver" | Strict generated `INPUT` files | `03` and `08` strict generated ABACUS inputs contain `ks_solver cusolver`. |
| "投递到 4V100 节点" | `sacct -j 433962,429504 --format=JobID,JobName%28,State,ExitCode,Elapsed -P` | Strict `03` and `08` confirmation jobs ran on SAI `4V100` and completed normally. |
| "确认计算情况" | Slurm job table plus trajectory-derived barrier/fmax metrics | Real-Run Evidence and Comparison tables record job states, elapsed times, barriers, TS fmax, and cancellation reasons. |
| "交付 md 文件" | `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md` | This report is the delivered Markdown comparison and test record. |
| "测试" | `conda run -n atst-dev pytest tests -q` | Full test suite passed after implementation and report updates. |
| "当前 examples 可作为示例入口" | `conda run -n atst-dev python -c '... ConfigLoader.load(...) ...'` | All current `examples/*/config.yaml` files load successfully with the current config schema. |

## Conclusion

The current examples were traversed and the main branch baselines were measured.
Several current examples were smoke configurations and required production
parameter restoration before comparison. After strict main-like reruns on ABACUS
LTS 3.10.1 with `cusolver`, the key Cy-Pt workflows now satisfy the comparison.
`03_autoneb_Cy-Pt` completed on job `433962` with barrier `1.330070` eV, only
`0.002184` eV above the main AutoNEB barrier, and TS-to-main-TS RMSD `0.004433`
Ang. For `08_d2s_Cy-Pt`, the first strict runs stayed non-comparable until an
offline geometry diagnostic showed that the in-repository Fast IDPP path did
not match main's pymatgen IDPP path. After the Fast IDPP parity fix, job
`429504` completed on ABACUS LTS 3.10.1 with `cusolver`; its first rough NEB
band matched main within `1.7e-5` eV, its final rough band matched the main
last-band rough barrier within about `8.8e-4` eV, and Sella converged to fmax
`0.039662` eV/Ang.

Therefore the requested Cy-Pt reproduction is achieved for the two main Cy-Pt
workflows: `03_autoneb_Cy-Pt` now has a completed, main-comparable AutoNEB run,
and `08_d2s_Cy-Pt` now has a completed, main-comparable rough NEB/Sella run on
this server with ABACUS LTS 3.10.1 and `cusolver`. The broader all-examples
audit remains partial because `01/02/04/05` still do not have comparable
completed TS results.

## Remaining Gap

The explicit objective items still not satisfied are:

- The strongest acceptance criterion is now met for `03_autoneb_Cy-Pt`. Strict
  job `433962` completed real ABACUS LTS 3.10.1 work on `4V100` and reproduced
  the main AutoNEB barrier and TS structure within small tolerances. The same
  criterion is also satisfied for `08_d2s_Cy-Pt` rough NEB/Sella by job
  `429504`.
- Full reproduction of main's image-level MPI AutoNEB execution stack. Main used
  `gpaw python` under MPI, while the current `atst-dev` environment lacks
  `mpi4py` and plain `mpirun python` leaves ASE `world.size == 1`.
- Full comparable TS reproduction for `01/02/04/05` in the broader examples
  audit. The D2S IDPP/path-generation mismatch was resolved, and the AutoNEB
  Cy-Pt mismatch seen in earlier cancelled runs was resolved by the completed
  full-node validation.

This means the current state is a partial positive validation result for the
whole examples inventory, but a positive validation result for the requested
`03_autoneb_Cy-Pt` case.

## abacuslite Core Change

The change in `src/atst_tools/external/ASE_interface/abacuslite/core.py` was
needed for strict `mpi: 4` ABACUS LTS 3.10.1 runs, not for changing scientific
settings. During strict launches, abacuslite initialized the calculator by
calling `mpirun -np 4 abacus --version`. Under the Slurm wrapped job this command
could return empty stdout, causing `AbacusProfile.parse_version()` to fail before
any ABACUS calculation could start.

The fix keeps the legacy parser behavior, accepts the ABACUS LTS banner format,
and adds a fallback from empty MPI-version stdout to bare `abacus --version`.
This made the strict `mpi: 4` jobs progress beyond calculator initialization.
The later early-run non-comparability and final completed `03` comparability
came from actual ABACUS calculations and trajectory metrics, not from version
parsing. Unit coverage is in `tests/unit/test_abacuslite_profile.py`.

A second vendored abacuslite compatibility change was made after clean retry
`429068`: STRU writing now preserves first-occurrence species order rather than
alphabetical species order. This makes future Cy-Pt generated STRU files use
`C,Pt,H`, matching main's saved STRU block order. Unit coverage for the writer
and template atom-order mapping is also in `tests/unit/test_abacuslite_profile.py`.

## Recommended Follow-Up

Further GPU reruns of `03_autoneb_Cy-Pt` with the same ASE-native, abacuslite,
and LTS 3.10.1 stack are no longer needed for acceptance: the completed
full-node run is already comparable. Useful follow-up checks should preserve
that acceptance evidence and isolate remaining broader-audit gaps:

1. Run one Cy-Pt image with `genelpa` on a CPU allocation and `cusolver` on GPU,
   using otherwise identical generated `INPUT`/`STRU`/`KPT`, then compare energy
   and forces.
2. Run the same image through the legacy main-branch ASE-ABACUS wrapper and the
   abacuslite wrapper against the same ABACUS executable, then compare generated
   files and parsed ASE forces.
3. Preserve the Fast IDPP parity diagnostic as a regression check for D2S if the
   path generator changes again; this issue is resolved for the current `08`
   run.
4. Install or provide an MPI-enabled ASE Python entry point for `atst-dev`
   (`mpi4py` or an equivalent `gpaw python` setup) before claiming main-like
   AutoNEB image-level parallelism.
5. Preserve job `433962` outputs as the primary `03_autoneb_Cy-Pt` regression
   artifact because it has the closest parameter alignment evidence and a
   completed, comparable band.

## Reproducibility Artifacts

Strict main-like run artifacts:

- Main branch baseline trajectories:
  `temp_examples_main_20260519/examples`
- Earlier cancelled strict `03_autoneb_Cy-Pt` run:
  `temp_examples_strict_mainlike_runs_20260519_retry3/03_autoneb_Cy-Pt`
- Completed comparable strict `03_autoneb_Cy-Pt` run:
  `temp_examples_strict_mainlike_runs_20260520_retry11/03_autoneb_Cy-Pt`
- Strict `08_d2s_Cy-Pt` run:
  `temp_examples_strict_mainlike_runs_20260519_retry3/08_d2s_Cy-Pt`
- Clean strict `08_d2s_Cy-Pt` retry after `scale_fmax/idpp_*` alignment:
  `temp_examples_strict_mainlike_runs_20260519_retry5/08_d2s_Cy-Pt`
- Clean strict `08_d2s_Cy-Pt` retry after Fast IDPP parity fix:
  `temp_examples_strict_mainlike_runs_20260520_retry7/08_d2s_Cy-Pt`
- Stabilized exploratory runs:
  `temp_examples_stabilized_runs_20260519`
- Machine-readable metrics:
  `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.metrics.json`
- Generated-file audit:
  `temp_examples_strict_mainlike_runs_20260519_retry5/08_d2s_Cy-Pt/run_d2s/NEB/image_007/INPUT`,
  `KPT`, and `STRU`
- Patched species-order single-image diagnostic:
  `temp_examples_species_order_sp_20260520/08_d2s_Cy-Pt_patched_order`
- Main-geometry single-image LTS recalc diagnostic:
  `temp_examples_main_image_sp_20260520/Cy-Pt_neb2sella_main_image6`

Strict Slurm submissions:

- `428892`, node `4v100n09`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-03-autoneb-strict4 ...`
- `428893`, node `4v100n20`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-08-d2s-strict4 ...`
- `429068`, node `4v100n09`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-08-d2s-clean5 ...`
- `429435`, node `4v100n07`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-08-order-sp ...`
- `429445`, node `4v100n07`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-main-img-sp ...`
- `429504`, node `4v100n07`:
  `sbatch --partition=4V100 --qos=rush-1o2gpu --nodes=1 --ntasks=4 --gpus-per-node=1 --job-name=atst-08-d2s-idpp7 ...`
- `433962`, node `4v100n35`:
  `sbatch --partition=4V100 --qos=rush-gpu --nodes=1 --ntasks=16 --gpus-per-node=4 --job-name=atst-03-autoneb-r11 ...`
- These wrapped commands loaded `abacus/LTSv3.10.1-sm70-auto`, exported
  `OMP_NUM_THREADS` according to the example runtime (`1` for the `mpi: 4`
  D2S jobs, `2` for the `mpi: 16` full-node AutoNEB job), set `PYTHONPATH` to
  this checkout's `src`, and ran `conda run -n atst-dev atst run config.yaml`
  in the strict run directory.

The strict barrier/fmax numbers in this report were recomputed from ASE
trajectory files with commands of this form. Replace `RUN_DIR` with one of the
strict run artifact directories listed above:

```bash
conda run -n atst-dev python -c $'import glob\\nimport numpy as np\\nfrom ase.io import read\\ndef fmax(atoms):\\n    forces = atoms.get_forces()\\n    return float(np.sqrt((forces * forces).sum(axis=1).max()))\\npaths = sorted(glob.glob("RUN_DIR/run_autoneb[0-9][0-9][0-9].traj"))\\nimages = [read(path, ":")[-1] for path in paths]\\nenergies = np.array([atoms.get_potential_energy() for atoms in images])\\nimax = int(energies.argmax())\\nprint("barrier", float(energies[imax] - energies[0]))\\nprint("ts_index", imax)\\nprint("ts_fmax", fmax(images[imax]))'
```

For the D2S rough NEB case:

```bash
conda run -n atst-dev python -c $'import numpy as np\\nfrom ase.io import read\\ndef fmax(atoms):\\n    forces = atoms.get_forces()\\n    return float(np.sqrt((forces * forces).sum(axis=1).max()))\\nall_frames = read("RUN_DIR/neb_rough.traj", ":")\\nn_images = 12\\nimages = all_frames[-n_images:]\\nenergies = np.array([atoms.get_potential_energy() for atoms in images])\\nimax = int(energies.argmax())\\nprint("frames", len(all_frames))\\nprint("barrier", float(energies[imax] - energies[0]))\\nprint("ts_index", imax)\\nprint("ts_fmax", fmax(images[imax]))'
```

## Verification

- Added and passed focused unit tests for NEB/D2S `optimizer_kwargs` schema and
  runner forwarding, plus D2S rough DyNEB `scale_fmax` and Fast IDPP
  `idpp_maxiter`/`idpp_tol` schema and forwarding.
- Replaced the old Fast IDPP L-BFGS approximation with a pymatgen-compatible
  NEB-like IDPP update. Offline comparison against pymatgen in the separate
  `atst` environment showed zero RMSD at printed precision for the `08` path,
  and ABACUS LTS job `429504` then completed with main-comparable rough NEB
  barriers and converged Sella fmax `0.039662` eV/Ang.
- Real Slurm jobs above confirm ABACUS was launched on `4V100` and generated
  ABACUS scratch directories before the divergent runs were cancelled.
- Earlier `03`/`08` validation jobs were explicitly terminated after
  quantitative trajectory checks showed large barrier and force mismatches under
  aligned parameters. The final `08` validation job `429504` completed normally.
- Added a vendored abacuslite profile fallback so strict `mpi: 4` configurations
  do not fail when `mpirun ... abacus --version` returns empty stdout under
  Slurm; the fallback queries the bare executable version string.
- Full unit suite was rerun with `conda run -n atst-dev pytest tests -q` and
  passed.
- All current example YAML files were loaded with `ConfigLoader.load(...)` under
  `atst-dev`; `01`-`08`, `10`, and `11` all parsed successfully.
- MPI image-level diagnostic job `429055` ran on `4V100` and showed plain
  `mpirun python` leaves ASE `world.size == 1` in `atst-dev`; `mpi4py` is not
  installed in that environment.
- Species-order diagnostic job `429435` ran on `4V100` and showed the patched
  `C,Pt,H` STRU order gives the same energy/fmax as pre-fix `C,H,Pt` for the
  clean retry first-band TS image.
- Main-geometry diagnostic job `429445` ran on `4V100` and reproduced the stored
  main first-band TS image energy/fmax to within `2.2e-5` eV and `6.7e-5`
  eV/Ang.
- Fast-IDPP-fixed `08_d2s_Cy-Pt` job `429504` ran on `4V100` and completed in
  `06:00:52`.
- Full-node `03_autoneb_Cy-Pt` job `433962` ran on `4V100` and completed in
  `20:53:59`; trajectory analysis reproduced the reported barrier, TS index,
  TS fmax, and TS RMSD.
- Reproducibility commands in this report were tested against the strict `03`
  and `08` run directories and reproduced the reported barrier, TS index, and
  TS fmax values.
- The machine-readable strict-vs-main JSON metrics block was parsed with
  `json.loads(...)` under `atst-dev`.
- The standalone metrics JSON file
  `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.metrics.json`
  was parsed with `json.load(...)` under `atst-dev`.
- The embedded strict-vs-main JSON block and standalone metrics JSON were both
  parsed under `atst-dev`.
