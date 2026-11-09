# ATST-Tools 用户指南

项目主文档使用英文，本指南提供从安装、首次运行到结果读取和常见问题排查的
完整中文入门路径。详细参数、CLI 和 Python API 契约统一维护在英文参考文档中；
下文在对应步骤提供链接，全部入口见 [文档索引](../index.md)。

## 1. 项目定位

ATST-Tools 是面向 ABACUS 和 DeePMD-kit 后端的 ASE 过渡态工作流工具。
本指南对应 [2.3.3](../releases/RELEASE_NOTES_2.3.3.md)，ABACUS 通过独立安装的
abacuslite 接入。使用 `atst` 命令和 YAML 配置可运行 NEB、AutoNEB、Dimer、Sella、
CCQN、D2S、结构优化、振动分析、IRC、MD、恒电势工作流，以及实验性的 DMF。
各方法的适用范围见下文「支持的工作流」。

ATST-Tools 的边界是工作流编排、配置校验、calculator 构造、轨迹命名、
重启辅助、ABACUS 常见前后处理和示例文档。ABACUS、DeePMD-kit、ASE、Sella
仍然负责各自的数值计算和核心算法。

### CLI/YAML 与 Python API 的选择

日常交互、站点调度提交和可复现配置可使用 CLI + YAML；Agent 或已有 Python 程序需要
复用同一 schema、取得结构化结果，或向 ATST 的 CCQN 传入已创建的 ASE
calculator 时，使用 `atst_tools.api`。两条路径共享科学 workflow；API 不申请资源或
启动外层 Python MPI，但 YAML 中配置的 calculator 命令可以启动 ABACUS MPI 子进程，且
API 不重建传入 CCQN 的 calculator。详见
[Python API reference](PYTHON_API_REFERENCE.md)。

若外部 Python 软件或任务编排器需要独立进程、稳定退出码和 JSON 文件交接，可安装
后调用：

```bash
python -m atst_tools.api.runner --config config.yaml --workdir run --result-json atst_api_result.json
```

runner 只在其进程内进入 `--workdir`；成功时仅 root rank 以原子替换写入
`atst-api-result-v1`，其中的 `artifact_manifest` 为绝对路径。退出码 `0` 为成功，
`2` 为 ATST API 错误，`1` 为意外 runner 错误。调度和外层 MPI 由调用方负责。

## 2. 安装与环境检查

从 PyPI 安装已发布版本：

```bash
pip install atst-tools
atst --version
```

从源代码安装当前 checkout：

```bash
git clone https://github.com/QuantumMisaka/atst-tools.git
cd atst-tools
pip install .
```

ATST-Tools 需要 Python 3.10 或更新版本。默认安装包含轻量工作流层和
Sella 2.5+；按需选择以下安装 profile：

- **Serial（默认）**：`pip install atst-tools`；不安装也不需要 `mpi4py`，可运行全部非 image-parallel 工作流和串行 NEB/AutoNEB。
- **DP**：`pip install "atst-tools[dp]"`；仅 DeePMD-kit calculator 工作流需要。
- **Image-parallel NEB/AutoNEB**：`pip install "atst-tools[parallel]"`；仅当通过外部 `mpirun`/`srun` 启动一个 Python rank 对应一个活动 image 时需要。

<details>
<summary>仅 image-parallel 用户：MPI 环境检查</summary>

使用 image-parallel 前，先验证 `mpi4py` 导入和 two-rank launcher：

```bash
python -c "from mpi4py import MPI; print(MPI.Get_library_version())"
mpiexec -n 2 python -c "from mpi4py import MPI; print(MPI.COMM_WORLD.Get_rank())"
```

如需恢复与站点 MPI 实现匹配的构建：

```bash
MPICC="$(command -v mpicc)" \
  python -m pip install --no-cache-dir --force-reinstall --no-binary=mpi4py mpi4py
```

仅在站点已加载与外层 launcher 和 ABACUS 一致的 MPI 实现后执行该重装；串行用户不需要安装 mpi4py。

</details>

ATST-Tools 只安装 Python 工作流层。真实计算还需要后端运行时：

- ABACUS 工作流需要可执行的 `abacus`、赝势、数值轨道和可用计算资源。
- DP 工作流需要 `atst-tools[dp]` 或等价的 DeePMD-kit Python 环境，以及
  外部模型文件。
- MPI image-level NEB/AutoNEB 需要 `atst-tools[parallel]` 或等价的
  `mpi4py` 环境，且 `mpi4py` 需要匹配站点 MPI 栈。
- DMF 工作流 vendored 了 PyDMF 源码，但运行时仍需要 `cyipopt` 和 IPOPT。
- 使用 GPU 的 ABACUS LCAO 计算，应依据已安装 ABACUS 的文档选择与站点兼容的
  GPU solver。

## 3. 10 分钟快速上手

### 3.1 取得示例并完成一次本地操作

这里的“10 分钟”指安装后的命令、配置和文件操作入门；真实 DFT 计算时间取决于
体系和计算资源。`pip install` 安装 Python 包，不会在当前目录创建 `examples/`。
首次使用请先取得与安装版本对应的示例；已经在仓库中的用户无需重复克隆：

```bash
git clone --branch v2.3.3 https://github.com/QuantumMisaka/atst-tools.git
cd atst-tools
atst --version
atst run --list-types
```

使用其他版本时选用对应 tag；源码开发用户使用当前 checkout 的示例与文档。
以下三组命令按顺序执行。先从仓库根目录校验 YAML：

```bash
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
atst run --dry-run examples/06_relax_H2-Au/config.yaml
```

成功时会显示归一化配置及配置有效信息。普通 `--dry-run` 不执行后端，也不证明
结构文件、模型、赝势或计算资源已经可用；`--check-input` 是另行请求的 ABACUS
输入预检，会调用已安装的 ABACUS，详见 [CLI 参考](CLI_REFERENCE.md#workflow-execution)。

接着进入轻量示例，生成初始路径并读取已有结果，无需 ABACUS、DP 模型或 GPU：

```bash
cd examples/09_lightweight_cli
atst neb make inputs/init.xyz inputs/final.xyz 3 -o first_chain.traj --method linear
atst neb summary inputs/neb_result.extxyz --n-max 1 --tail 5
atst relax post inputs/relax_result.extxyz --output-format traj --output restart.traj
```

应得到 `first_chain.traj`（两个端点和三个内点，共五帧）、已有 NEB 结果的终端摘要，
以及提取的 `restart.traj`。`first_chain.traj` 是插值初猜，其占位能量/力不构成计算结果。
后处理示例中的既有数据用于学习文件交接；新生成结构尚未经过后端计算。

### 3.2 运行真实后端算例

仍从上一步的轻量示例目录开始：

```bash
cd ../06_relax_H2-Au
atst config validate config.yaml
# Confirm the backend and resources before executing the next command.
atst run config.yaml
```

执行前确认：`abacus` 可用，所需赝势/轨道文件存在，MPI 与线程数适合当前资源。
该示例设置 `mpi: 4`、`ks_solver: cusolver`，需要相应 ABACUS GPU 构建和资源；
不能直接当作通用 CPU 算例。CPU 或其他站点应先按自己的 ABACUS 配置修改后端设置。
示例 `max_steps: 1` 用于短运行展示，通常不足以达到 `fmax: 0.05`，完成不代表收敛。

普通 `atst run` 的结构、模型及输出相对路径以**当前工作目录**为基准，不会自动
切换到 YAML 所在目录。因此先 `cd` 到算例目录，再运行 `config.yaml`；每个独立
计算使用自己的目录。API/process runner 的路径约定见
[Python API 参考](PYTHON_API_REFERENCE.md#paths-mpi-and-backends)。

DP 用户先安装 `atst-tools[dp]` 并取得模型，再按
[示例指南](../../examples/README.md#usage)运行 `config_dp.yaml`。首次学习不需要
选择 image-parallel；外层 MPI 与后端 MPI 的区别见 [后端指南](ABACUSLITE_WRAPPER_GUIDE.md)。

### 3.3 读取结果与选择下一步

Relax 示例完成后，在当前算例目录查看：

| 文件/操作 | 用途 |
| --- | --- |
| `relax.traj` | 优化轨迹；`atst relax summary relax.traj --tail 5` 查看末尾变化。 |
| `final_relaxed.traj` | 本次最终结构及保存的计算结果。 |
| `atst_artifacts.json` | 产物清单与阶段事实；读取 `stages` 中的 `converged`。 |
| `relax_run/` | ABACUS 输入、输出与运行诊断。 |

`converged: true` 表示记录的优化准则达到，`false` 表示未达到，`null` 表示缺少可用
收敛事实。退出码为零只说明执行完成；TS 搜索完成后，振动和 IRC 仍是显式选择的
后续步骤。重启前先保留原结果，并查对应 workflow 的 `restart` 语义。

根据科学问题选择下一步：有两个端点时从 NEB 入手；需要自适应插点时看 AutoNEB；
已有 TS 初猜时看 Dimer/Sella/CCQN；需要粗路径接单端搜索时看 D2S。
模板由已安装版本生成，避免手抄不兼容字段：

```bash
atst run --show-template neb --calculator abacus
atst run --show-template d2s --calculator dp
```

更多算例见 [examples/README.md](../../examples/README.md)；完整字段及默认值见
[YAML 参数表](YAML_INPUT_VARIABLES.md)，组合语义见 [配置参考](CONFIG_REFERENCE.md)。

### 3.4 常见问题

| 现象 | 首先检查 |
| --- | --- |
| 找不到 `atst` 或导入包失败 | 是否激活安装包的 Python 环境；用 `python -m pip show atst-tools` 核对安装位置。 |
| 找不到 `examples/` | pip 安装不会下载示例到当前目录；按 §3.1 取得仓库。 |
| 找不到 `inputs/...`、模型或赝势 | 当前目录是否为算例目录；配置中的相对路径是否存在。 |
| 配置通过但无法启动 ABACUS | 普通 dry-run 只校验配置；检查后端命令、MPI、GPU solver 和资源。 |
| 优化结束但 `converged: false` | 查看步数、阈值及后端错误；短示例的步数上限可能只够展示流程。 |
| 已安装包没有 `vibration validate` | 用 `atst --version` 核对版本；2.3.1 已包含该命令，检查命令与包是否来自同一 Python 环境。 |

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
| `constant_potential` | ABACUS 恒电势固定几何单点/串行扫描 | `atst run config.yaml` |

常规 workflow 交付结构、阶段执行状态和 optimizer 已提供的收敛事实；完成计算
不会自动运行 IRC，也不等于过渡态已验证。振动/IRC 等额外计算仍由 YAML 中明确配置。
可使用独立只读筛查，检查已保存的振动结果和可选冻结结构证据：

```bash
atst vibration validate vibration_results.json --structure frozen_ts.traj
```

它不会启动 calculator 或新振动计算。缺少检查范围或冻结力证据时保持 `unknown`；
筛查结果不证明 IRC 连通性。命令和 Python 入口见
[CLI 参考](CLI_REFERENCE.md#vibration-tools)与
[Python API 参考](PYTHON_API_REFERENCE.md)。

DMF 当前是 experimental：默认只面向非周期基线，输出 `tmax` TS candidate，
不能表述为已验证 TS；周期输入默认拒绝，只有显式设置
`pbc_mode: cartesian_unwrapped`、`initial_path: linear`、确认风险并关闭
rotation/translation removal 时才进入实验路径。D2S 默认仍使用 rough NEB；
`rough_method: dmf` 可作为实验性 rough stage 生成候选后接 Dimer/Sella/CCQN，
但在 refinement、vibration/IRC runtime 验收完成前不能视为 supported 生产路径。
D2S、CCQN 和 IRC 已纳入 2.0.x schema 与示例，不再是待集成状态。功能支持状态、
验证边界和暂不支持项目以
[FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md) 为准。

恒电势功能通过 `calculator.constant_potential`
装饰 ABACUS calculator，可运行固定几何的单点或串行目标扫描；固定晶胞的
`relax`、串行 `neb` 和 ASE 驱动 `md` 只接受 `energy_boundary: compensated_gate`、
`reference_electrode: custom` 及单一 `target_mu_ev`。MD 支持固定晶胞的
VelocityVerlet（`nve` 选择器）和 Bussi、Langevin、NVTBerendsen（`nvt`）。
恒电势 MD 从 2.3.2 起支持，真实后端验证目前覆盖短程轨迹。
电子与库交换，因此 `nve` 不代表固定电子数微正则系综。每次给出核力前均要求
SCF 和恒电势残差收敛；未收敛的状态不会写成已完成帧。MD 的每步诊断和续跑
checkpoint 位于 `calculation.directory`，`restart: true` 从最后完成步继续，
`steps` 表示新增步数。`reference_fcp` 仅用于固定几何参考算法复现和诊断。
恒电势功能不覆盖 cell-relax、stress、AutoNEB、D2S、ABACUS 原生恒电势 MD、
两 Fermi 或显式 `nupdown`。参数、能量定义和产物见
[配置参考](CONFIG_REFERENCE.md#211-constant-potential-evaluation)。

## 5. ABACUS / abacuslite 集成

ABACUS calculator 通过独立安装的 `abacuslite>=1.2.1,<2` 集成。缺包或导入失败会
直接报错，不回退到仓库内实现；`atst_tools.external.ASE_interface.abacuslite`
历史路径仅转发到同一独立包，不包含第二套实现。

对于 `calculation: scf`，abacuslite 会自动在 running log 中寻找与本次 STRU
对应的最新帧。它在统一原子序和坐标单位后，接受周期性等价的坐标，因此过渡态或
NEB 图像跨越晶胞边界仍可识别；不同原子可以有不同的整数晶格平移，非正交晶胞也
适用。不同结构、晶胞、原子数或顺序，以及 shape/有限值/奇异晶胞/坏帧等问题会
fail-closed 并给出诊断，不会用较早的合法帧掩盖损坏输出。检查不会隐式 wrap 或修改
输入、候选帧、力或路径坐标。原生 `relax`、`md` 和 `MD_dump` 仍保持末帧语义；该
检查只用于 SCF 结果选择，且没有新增 `pbc_mode`、容差或其他配置开关。若使用
`write_input` 的自定义 `stru_file`，检查会读取同一文件名；未调用 `write_input` 时
仍使用默认 `STRU`。

当前 2.3.3 使用独立 abacuslite（验证基线 1.2.1）的 SCF 帧匹配行为：按
`1e-5 Å、rtol=0` 比较晶胞分量和周期等价的 Cartesian 坐标残差；旧默认 `1e-4 Å`
能接受的较大误差现在可能被拒绝。这是几何匹配容差，不是 SCF 或力收敛阈值；
ATST 不再维护或修改 vendored 匹配器。

固定晶胞路径准备也采用 `1e-5 Å、rtol=0`：容差内保留各输入晶胞，超差或 PBC
不同则 warning，并在副本上采用初始端点／本次加载链首帧的参考边界，不缩放坐标。
NEB、AutoNEB 和 D2S rough DyNEB 启动前，仅内部运行副本统一必要的周期晶胞向量，
满足 ASE 原有检查；重启以恢复链为基准。原文件始终保留，容差内预处理结果保留原值，实际轨迹
写运行晶胞，manifest 的 `metadata.fixed_cell` 记录参考边界与适配。改胞后旧端点
能量和力失效，`auto` 会重算，`never` 会在缺少有效结果时报错。详见
[配置语义参考](CONFIG_REFERENCE.md#22-nudged-elastic-band-neb)。

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
- 反向生成通过 `atst prepare` 从 ABACUS 输入目录（`INPUT`/`STRU`/`KPT`/
  `PP`/`ORB`）生成可运行的过渡态 YAML，无需手工编写配置。
- ATST-Tools 不替代 ABACUS CLI，不负责站点调度提交策略，不承诺覆盖全部
  abacuslite IO API。

读取 ABACUS `STRU` 时，晶胞矢量始终按 `LATTICE_CONSTANT × Bohr` 换算；
原子坐标则依 `ATOMIC_POSITIONS` 的模式分别解释：`Direct` 为分数坐标，
`Cartesian` 按晶格常数换算，`Cartesian_au` 为 Bohr，
`Cartesian_angstrom` 为 Å。Relax、MD、恒电势和过渡态工作流共用此读取语义；
详见[配置参考](CONFIG_REFERENCE.md)。

从 ABACUS 运行目录生成 NEB 配置（`atst prepare` 不运行 ABACUS）：

```bash
atst prepare run_dir --workflow neb \
  --init-structure init/STRU --final-structure final/STRU \
  --n-images 5 -o atst_neb.yaml
```

`--workflow` 当前支持 `neb`（默认）；`--init-structure`/`--final-structure`
指定端点结构（默认取运行目录 `STRU`），`--n-images` 设置内点个数（默认 5）。
默认允许只有结构、尚无能量和受力的端点；生成的 YAML 会启用端点优化，运行时
对缺 E/F 的端点先做 Relax，再以优化后的端点插值建链。`--no-gate` 作为旧命令的
兼容选项保留，已无需指定；`-o` 指定输出 YAML 路径。生成时用户可控的 ABACUS 值原样带入，仅施加三个
技术地板：`calculation` 归一化为 `scf`、`cal_force` 归一化为 `1`、KPT 拒绝
line 模式（接受 Gamma/MP 网格与 point 显式 K 点）。等价能力也可通过 Python
API `atst_tools.api.build_config_from_abacus_dir` 调用。

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
`summary` 子命令只读已有轨迹、cache 或阶段输出，可用于调度任务监控和最终结果摘要；
不会创建 calculator，也不会运行 ABACUS/DP。

ABACUS 前后处理：

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
atst abacus collect run_abacus --output abacus_results.json
atst prepare run_dir --workflow neb --init-structure init/STRU --final-structure final/STRU -o atst_neb.yaml
```

更多命令见 [CLI_REFERENCE.md](CLI_REFERENCE.md)。

GPU 工作站上的设备绑定与运行证据（可选，不影响旧调用）：

```bash
atst run config.yaml --devices 0,1 --threads auto      # 绑定设备与线程预算
atst run config.yaml --telemetry                        # 额外写出 runtime_evidence.json
```

等价写法是 YAML 里的 `runtime` 段（`devices` / `binding` / `threads` /
`telemetry`，语义见 [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) 第 4 节）。
`devices` 的整数是"当前可见集合内"的逻辑序号，不是物理卡号；没有
`runtime` 段、也没有运行时选项时，`atst run` 行为与过去完全一致。
`python -m atst_tools.api.runner` 接受同样的选项，并会在运行工作流前完成绑定。

## 7. 参数文档入口

- 手写语义参考：[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)。用于理解常见配置组合、
  workflow 语义、ABACUS/DP calculator 配置和运行边界。
- 参数总表：[YAML_INPUT_VARIABLES.md](YAML_INPUT_VARIABLES.md)。该文件由对应 checkout 的
  schema 生成，是非 calculator YAML 字段的主入口；阅读时应匹配已安装版本。
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

## 9. 维护者入口

开发新 workflow、配置字段、示例或发布时，请使用
[维护交接清单](../developer/HANDOVER.md) 和
[示例验证操作指南](../developer/EXAMPLE_VALIDATION_OPERATIONS.md)。
