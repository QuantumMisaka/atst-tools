# ATST-Tools 用户指南

## 1. 项目定位

ATST-Tools 是面向 ABACUS 和 DeePMD-kit 后端的 ASE 过渡态工作流工具。
当前 2.1.3 版本把原 main branch 的脚本集合整理为可安装 Python package，
统一通过 `atst` 命令和 YAML 配置运行 NEB、AutoNEB、Dimer、Sella、CCQN、
D2S、结构优化、振动分析、IRC、MD，以及实验性的 DMF 候选路径任务。

ATST-Tools 的边界是工作流编排、配置校验、calculator 构造、轨迹命名、
重启辅助、ABACUS 常见前后处理和示例文档。ABACUS、DeePMD-kit、ASE、Sella
仍然负责各自的数值计算和核心算法。

## 2. 安装与环境检查

开发环境推荐使用项目约定的 `atst-dev` conda 环境：

```bash
conda activate atst-dev
pip install -e ".[dev]"
atst --version
```

普通本地安装：

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install .
```

ATST-Tools 需要 Python 3.10 或更新版本。默认安装包含轻量工作流层和
Sella 2.5+；绘图、DP 和 MPI 并行栈按需安装：

```bash
pip install "atst-tools[plot]"      # NEB plotting helpers
pip install "atst-tools[dp]"        # DeePMD-kit calculator workflows
pip install "atst-tools[parallel]"  # MPI image-level NEB/AutoNEB
```

ATST-Tools 只安装 Python 工作流层。真实计算还需要后端运行时：

- ABACUS 工作流需要可执行的 `abacus`、赝势、数值轨道和可用计算资源。
- DP 工作流需要 `atst-tools[dp]` 或等价的 DeePMD-kit Python 环境，以及
  外部模型文件。
- MPI image-level NEB/AutoNEB 需要 `atst-tools[parallel]` 或等价的
  `mpi4py` 环境，且 `mpi4py` 需要匹配站点 MPI 栈。
- DMF 工作流 vendored 了 PyDMF 源码，但运行时仍需要 `cyipopt` 和 IPOPT。
- SAI GPU 节点上的 ABACUS LCAO 示例通常需要在 `calculator.abacus.parameters`
  中设置 `ks_solver: cusolver`。

## 3. 10 分钟快速上手

第一步：确认命令可用并查看支持的 workflow：

```bash
atst --version
atst run --list-types
```

第二步：先校验配置，不启动计算：

```bash
atst run --dry-run examples/06_relax_H2-Au/config.yaml
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
```

第三步：运行一个小型 YAML 工作流：

```bash
cd examples/06_relax_H2-Au
atst run config.yaml
```

第四步：按目标 workflow 生成模板或切换示例：

```bash
atst run --show-template neb --calculator abacus
atst run --show-template ccqn --calculator abacus
atst run --show-template d2s --calculator dp
atst run --show-template md --calculator abacus
atst run --show-template dmf --calculator dp
```

更多示例学习路径见 [examples/README.md](../../examples/README.md)。完整功能状态见
[FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md)。

## 4. 支持的工作流

`calculation.type` 当前支持：

| 类型 | 用途 | 入口 |
| :--- | :--- | :--- |
| `neb` | NEB / DyNEB 路径优化 | `atst run config.yaml` |
| `autoneb` | 自动插点 NEB | `atst run config.yaml` |
| `d2s` | 粗 NEB 到 Dimer/Sella/CCQN 单端 TS 搜索 | `atst run config.yaml` |
| `dimer` | Dimer 单端鞍点搜索 | `atst run config.yaml` |
| `sella` | Sella 鞍点搜索 | `atst run config.yaml` |
| `ccqn` | CCQN 单端鞍点搜索 | `atst run config.yaml` |
| `relax` | 结构优化 | `atst run config.yaml` |
| `vibration` | 振动频率和热化学校正 | `atst run config.yaml` |
| `irc` | Sella IRC 正向、反向或双向路径 | `atst run config.yaml` |
| `md` | 分子动力学；支持 ASE 驱动和 ABACUS 原生 MD | `atst run config.yaml` |
| `dmf` | Direct MaxFlux 实验性 TS candidate / path optimizer | `atst run config.yaml` |

DMF 当前是 experimental：默认只面向非周期基线，输出 `tmax` TS candidate，
不能表述为已验证 TS；周期输入默认拒绝，只有显式设置
`pbc_mode: cartesian_unwrapped`、`initial_path: linear`、确认风险并关闭
rotation/translation removal 时才进入实验路径。D2S 默认仍使用 rough NEB；
`rough_method: dmf` 可作为实验性 rough stage 生成候选后接 Dimer/Sella/CCQN，
但在 refinement、vibration/IRC runtime 验收完成前不能视为 supported 生产路径。
D2S、CCQN 和 IRC 已纳入 2.0.x schema 与示例，不再是待集成状态。功能支持状态、
验证边界和暂不支持项目以
[FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md) 为准。

## 5. ABACUS / abacuslite 集成

ABACUS calculator 通过 `abacuslite` 集成。ATST-Tools 优先导入环境中安装的
`abacuslite`，如果不可用，则回退到仓库内 vendored snapshot。

典型 ABACUS 配置：

```yaml
calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_abacus
    kpts: [1, 1, 1]
    parameters:
      calculation: scf
      basis_type: lcao
      ks_solver: cusolver
      pseudo_dir: ../data
      orbital_dir: ../data
      pseudopotentials:
        H: H_ONCV_PBE-1.0.upf
      basissets:
        H: H_gga_6au_100Ry_2s1p.orb
```

ATST-Tools 是分层 wrapper：

- 复杂工作流通过 `atst run CONFIG.yaml` 使用 abacuslite 作为 ASE calculator
  backend，例如 NEB、D2S、CCQN、Relax、Vibration、IRC。
- 简单前处理通过 `atst abacus prepare` 生成 `INPUT`、`KPT`、`STRU`。
- 简单后处理通过 `atst abacus collect` 生成只读 JSON 摘要，并在文件齐全时
  解析最终结构。
- ATST-Tools 不替代 ABACUS CLI，不负责 Slurm 提交策略，不承诺覆盖全部
  abacuslite IO API。

## 6. 常用轻量命令

这些命令不创建 calculator，不运行 ABACUS/DP：

```bash
atst neb make inputs/init.xyz inputs/final.xyz 5 -o inputs/init_neb_chain.traj --method linear
atst neb post neb.traj --n-max 5 --vib-analysis --write-latest neb_latest
atst neb summary neb.traj --n-max 5 --tail 5
atst dimer make-from-neb neb.traj --n-max 5 --output-traj dimer_init.traj
atst dimer summary dimer.traj --tail 5
atst relax post relax.traj --output-format traj --output restart.traj
atst relax summary relax.traj --tail 5
atst vibration post config.yaml --output vibration_results.json
atst vibration summary config.yaml
atst d2s summary config.yaml --format json --output d2s_summary.json
atst traj collect frames/*.xyz -o collection.traj --no-calc
atst traj transform collection.traj --format extxyz --output-prefix collection
```

`atst neb make --method` 可选 `IDPP`（默认）或 `linear`。
`summary` 子命令只读已有轨迹、cache 或阶段输出，可用于 Slurm 任务监控和最终结果摘要；
不会创建 calculator，也不会运行 ABACUS/DP。

ABACUS 前后处理：

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
atst abacus collect run_abacus --output abacus_results.json
```

更多命令见 [CLI_REFERENCE.md](CLI_REFERENCE.md)。

## 7. 参数文档入口

- 手写语义参考：[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)。用于理解常见配置组合、
  workflow 语义、ABACUS/DP calculator 配置和运行边界。
- 参数总表：[YAML_INPUT_VARIABLES.md](YAML_INPUT_VARIABLES.md)。该文件由
  `src/atst_tools/utils/config_schema.py` 生成，是非 calculator YAML 字段的主入口。
- 快速检查：

```bash
atst run --dry-run config.yaml
atst config validate config.yaml --print-normalized
atst run --show-template neb --calculator abacus
```

## 8. 示例路径

- 入门：`examples/06_relax_H2-Au/config.yaml`
- NEB：`examples/01_neb_Li-Si/config.yaml` 或 `examples/02_neb_H2-Au/config.yaml`
- AutoNEB：`examples/03_autoneb_Cy-Pt/config.yaml`
- Dimer：`examples/04_dimer_CO-Pt/config.yaml`
- Sella：`examples/05_sella_H2-Au/config.yaml`
- CCQN：`examples/12_ccqn_H2-Au/config.yaml`
- Vibration：`examples/07_vibration_H2-Au/config.yaml`
- D2S：`examples/08_d2s_Cy-Pt/config.yaml`
- IRC：`examples/10_irc_H2/config.yaml`
- 轻量 CLI：`examples/09_lightweight_cli/README.md`

## 9. 开发与验证

常用验证命令：

```bash
conda activate atst-dev
pytest tests -q
atst --help
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
```

开发新工作流或配置字段时，先更新 `src/atst_tools/utils/config_schema.py`，
再同步 `docs/user/CONFIG_REFERENCE.md`、示例配置和测试。
