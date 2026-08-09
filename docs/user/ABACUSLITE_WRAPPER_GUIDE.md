# ABACUSLite Wrapper Guide

## Current Integration State

ATST-Tools integrates ABACUS through `abacuslite`. Runtime resolution is:

1. Import an independently installed `abacuslite` package.
2. If unavailable, fall back to the vendored snapshot under
   `src/atst_tools/external/ASE_interface/abacuslite`.

This means ABACUS-backed workflows can run through ASE calculators without
requiring users to write Python calculator boilerplate. The supported workflow
entry point remains:

```bash
atst run CONFIG.yaml
```

`neb`, `autoneb`, `d2s`, `dimer`, `sella`, `relax`, `vibration`, `irc`, and
`md` can all use `calculator.name: abacus`.

## Vendored Backend Notes

ATST-Tools still resolves an independently installed `abacuslite` package before
the vendored fallback. An external `abacuslite` package may differ from the
vendored snapshot.

As of 2026-07-23, the vendored snapshot is synchronized with upstream
`deepmodeling/abacus-develop` commit `70f7ed69b5677c447afdc78e05240e93da660e66`
after normalizing ATST package-layout differences. It intentionally preserves these local
differences from `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite`:

- Relative imports so the package works under `atst_tools.external`.
- First-occurrence species grouping for generated STRU files.
- ASE `FixAtoms` and `FixCartesian` constraints written as ABACUS mobility flags.
- Tolerant legacy ABACUS band-row parsing.
- SCF coordinate frame selection（防御性改进）：`read_results` 在 `calculation=scf`
  下按"帧坐标 == 本次落盘 STRU（绝对 Å 容差）"选择当前结构帧并 fail-closed，不再
  依赖"末帧即当前结构"的假设；原生 relax/md 保持末帧语义。此为防御性改进（多帧累积
  running log 下消除帧歧义），不改变投影/收敛语义，也不改 `read_abacus_out` 公共签名。

The synchronized snapshot accepts both dotted and undotted prerelease banners
such as `v3.11.0-beta.1` and `v3.11.0-beta1`; its fixed-density helper also
uses `OUT.ABACUS` as the explicit charge-file directory expected by current
upstream behavior.

ATST workflow YAML already defaults NEB, AutoNEB, and the D2S rough DyNEB path
to ASE's recommended `improvedtangent` method. Direct `AbacusNEB(...)`
construction now pins the same default explicitly, so its behavior does not
depend on an ASE release's implicit default.

The vendored snapshot also carries upstream-sync fixes for numbered backup
rotation, property-derived ABACUS keyword conflict detection, unsupported TDDFT
`dipole` de-advertising, and `read_abacus_out` calculator `magmoms` reordering
when atoms are sorted during result parsing.

### Force / fmax 口径（RAW vs 投影，2026-08-04 确认）

ABACUS 的 `running_*.log` 中 `TOTAL-FORCE` 输出的是**全原子原始力（RAW）**，包含
STRU 中 `m 0 0 0` 固定原子——这是期望行为（与 VASP OUTCAR 等 DFT 惯例一致），
固定原子由驱动层约束处理。下游消费口径：

- **计算器层（vendored backend）**：返回 RAW 全原子力，不做预投影；约束投影由 ASE
  `Atoms.get_forces()`（默认 `apply_constraint=True`，按 `FixAtoms`）执行。
- **优化器层（sella/ASE）**：收敛判据使用**投影后自由原子力**；不要把 RAW 全原子
  fmax 直接与收敛阈值比较。
- **汇总/报告层（transition summary 等）**：报告 fmax 须明确口径（投影后自由原子力
  与 RAW 全原子力），约束体系收敛以投影后为准。
- **诊断/取证**：比较力必须同口径（投影后 vs 投影后，或仅自由原子原始力）；禁止把
  ASE 投影后值与 running log RAW 全原子值直接对比下结论。

该口径是"固定 Au 上 sella 提前收敛"曾被误诊为力读取 bug 的根因（约束投影被误读为
陈旧缓存），已按此修正。

## Wrapper Boundary

ATST-Tools is a layered wrapper around abacuslite:

- It owns YAML validation, schema defaults, workflow dispatch, restart helpers,
  trajectory naming, and common pre/post-processing.
- It uses abacuslite as the ASE calculator backend for ABACUS calculations.
- It exposes conservative ABACUS input/output helpers for repeated user tasks.
- It does not replace ABACUS, abacuslite, a scheduler, or site-specific
  launchers.

## Common Commands

Inspect the normalized config before launching a run:

```bash
atst config validate config.yaml --print-normalized
```

Prepare ABACUS input files from the ABACUS calculator block:

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
```

This writes:

- `INPUT` from `calculator.abacus.parameters`.
- `KPT` from `calculator.abacus.kpts` or `parameters.kpts`.
- `STRU` from the supplied structure and `pseudopotentials` / `basissets`.

Collect a conservative output summary:

```bash
atst abacus collect run_abacus --output abacus_results.json
```

The summary records detected `INPUT`, `KPT`, `STRU`, and `running*.log` files.
When the directory contains the files required by the active abacuslite reader,
the command parses the final frame and can export it:

```bash
atst abacus collect run_abacus --output abacus_results.json --structure final.extxyz
```

The collector copies parse inputs into a temporary directory before invoking
abacuslite readers, so original ABACUS outputs are not modified.

## Complex Workflows

Complex workflows are still launched with `atst run`:

```bash
atst run examples/01_neb_Li-Si/config.yaml
atst run examples/08_d2s_Cy-Pt/config.yaml
atst run examples/10_irc_H2/config.yaml
```

For D2S, ATST-Tools uses the same ABACUS calculator backend through rough NEB
and the selected single-ended method. For NEB and AutoNEB, endpoint
single-point governance repairs missing, placeholder, or unmarked (e.g.
uploaded-chain/foreign) endpoint results before ASE NEB construction when
configured with `endpoint_singlepoint: auto`, and recomputes both endpoints under
`always`; `never` preserves user-provided readable endpoint results.

## NEB Image-Level MPI

The vendored abacuslite tree includes a working NEB pattern in
`src/atst_tools/external/ASE_interface/examples/neb.py`: each image receives an
independent `Abacus` calculator directory, and ASE runs `NEB(...,
parallel=True)`. ATST-Tools follows this image-isolated directory model for
ABACUS-backed NEB and AutoNEB.

Use an MPI-enabled Python environment compatible with the site launcher and
the installed ABACUS runtime. For ordinary NEB, the outer MPI world size must
equal the number of interior images; for AutoNEB, it must equal
`calculation.n_simul`. Start with `calculator.abacus.mpi: 1`; increasing it
adds a second, inner MPI layer for each ABACUS image calculation.

The outer launcher remains outside ATST-Tools. Configure the ABACUS subprocess
separately with `calculator.abacus.command`. When a bare single-process
`abacus` command runs inside an image-level MPI workflow, ATST-Tools clears the
outer MPI launcher environment for the ABACUS subprocess so it remains a
one-image calculation.

For site setup, example validation, and maintainer operations, use the
[developer handover](../developer/HANDOVER.md) and the
[example validation operations guide](../developer/EXAMPLE_VALIDATION_OPERATIONS.md).

## Non-Goals

- No scheduler submission command is provided in this layer.
- No site-specific environment setup is encoded in YAML.
- No complete ABACUS output database is built from run directories.
- No guarantee is made that every abacuslite IO function is exposed at the CLI.

Future expansion should keep this boundary: add helpers only when they reduce a
repeated ATST workflow step and can be tested without launching expensive
calculations.
