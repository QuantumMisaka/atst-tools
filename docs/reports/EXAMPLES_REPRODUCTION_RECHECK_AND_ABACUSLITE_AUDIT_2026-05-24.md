# Examples 复现复查与 abacuslite 审计

**Version**: 2.0.0
**Date**: 2026-05-24
**Status**: Maintained
**Owner**: ATST-Tools maintainers

范围：基于已完成的 main 分支对比证据 `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md`，复查当前 `examples/` 参考结果，确认示例预置参数是否可开箱即用，并审计验证过程是否要求对 vendored abacuslite 模块做关键修改。

本报告基于已有的已完成验证产物。本次复查没有新提交 4V100 Slurm ABACUS 任务。

## 摘要

对于具备 main 分支同类过渡态或能垒基线的示例，当前 examples 在已接受的容差范围内复现了既有 main 结果：

- `01_neb_Li-Si`、`02_neb_H2-Au`、`03_autoneb_Cy-Pt` 和 `08_d2s_Cy-Pt` 复现了 main 的能垒和过渡态 index。
- `04_dimer_CO-Pt` 和 `05_sella_H2-Au` 复现了 main 的最终过渡态结构和能量，精度与 LTS 对比报告中记录的一致。
- `06_relax_H2-Au`、`07_vibration_H2-Au`、`10_irc_H2` 和 `11_vibration_ideal_gas_H2` 没有 main 分支同类 TS/能垒基线，因此本报告按配置/schema 可用的示例进行确认，而不是作为 TS/能垒复现案例。
- `09_lightweight_cli` 是本地 pre/post CLI 轻量 fixture，不是 ABACUS 复现基准。

## 逐案例复现结果

| 案例 | 工作流 | Main 参考值 | 当前参考结果 | TS / 最终结构参考文件 | 验证证据 | 结论 |
| --- | --- | ---: | ---: | --- | --- | --- |
| `01_neb_Li-Si` | NEB | 能垒 0.618327 eV，TS index 2 | 能垒 0.618346 eV，TS index 2，TS fmax 0.048031 eV/A，band fmax 0.771472 eV/A，TS RMSD 0.000142 A | `examples/reference_structures/01_neb_Li-Si_ts.extxyz` | job 437553，00:18:41，4v100n07 | 可比/可复现 |
| `02_neb_H2-Au` | NEB | 能垒 1.120780 eV，TS index 4 | 能垒 1.124752 eV，TS index 4，TS fmax 0.020535 eV/A，band fmax 0.453789 eV/A，TS RMSD 0.004172 A | `examples/reference_structures/02_neb_H2-Au_ts.extxyz` | job 437554，16:45:17，4v100n29 | 可比/可复现 |
| `03_autoneb_Cy-Pt` | AutoNEB | 能垒 1.327886 eV，TS index 5 | 能垒 1.330070 eV，TS index 5，TS fmax 0.041272 eV/A，band fmax 0.234444 eV/A，TS RMSD 0.004433 A | `examples/reference_structures/03_autoneb_Cy-Pt_ts.extxyz` | job 433962，20:53:59，4v100n35 | 可比/可复现 |
| `04_dimer_CO-Pt` | Dimer | 最终能量 -211834.952698 eV | 最终能量 -211834.954565 eV，能量差 -0.001867 eV，最终 fmax 0.033976 eV/A，最终 RMSD 0.002209 A | `examples/reference_structures/04_dimer_CO-Pt_final_ts.extxyz` | job 437764，10:53:00，4v100n05 | 可比/可复现 |
| `05_sella_H2-Au` | Sella | 最终能量 -239255.122160 eV | 最终能量 -239255.122869 eV，能量差 -0.000709 eV，最终 fmax 0.048256 eV/A，最终 RMSD 0.000007 A | `examples/reference_structures/05_sella_H2-Au_final_ts.extxyz` | job 437568，00:02:14，4v100n28 | 可比/可复现 |
| `08_d2s_Cy-Pt` | D2S | 粗略 NEB 能垒 2.678795 eV | 粗略 NEB 能垒 2.678812 eV，TS index 6，粗略 TS fmax 3.531348 eV/A；最终 Sella 能量 -11865.557601 eV，最终 Sella fmax 0.039662 eV/A | `examples/reference_structures/08_d2s_Cy-Pt_rough_ts.extxyz`；`examples/reference_structures/08_d2s_Cy-Pt_sella_final_ts.extxyz` | job 429504，06:00:52，4v100n07 | 可比/可复现 |
| `06_relax_H2-Au` | Relax | 无 main 同类 TS/能垒基线 | 已检查配置/schema 加载 | N/A | 本地配置验证 | 可作为非 TS 示例直接使用 |
| `07_vibration_H2-Au` | Vibration | 无 main 同类 TS/能垒基线 | 已检查配置/schema 加载，参考输出 `vibration_results.json` | N/A | 本地配置验证 | 可作为非 TS 示例直接使用 |
| `09_lightweight_cli` | Pre/post CLI fixture | 无 ABACUS TS/能垒基线 | 本地轻量 fixture | N/A | 本地 fixture | 可作为本地 CLI fixture 使用 |
| `10_irc_H2` | IRC | 无 main 同类气相 IRC 基线 | 已检查配置/schema 加载 | N/A | 本地配置验证 | 可作为非 TS 示例直接使用 |
| `11_vibration_ideal_gas_H2` | Ideal-gas vibration | 无 main 同类 TS/能垒基线 | 已检查配置/schema 加载，参考输出 `vibration_results.json` | N/A | 本地配置验证 | 可作为非 TS 示例直接使用 |

## 开箱即用参数

`examples/*/config.yaml` 中的 primary ABACUS 预设旨在 SAI 4V100 节点上、文档记录的 `atst-dev` 环境中直接运行。这些配置使用与 ABACUS LTS 3.10.1 兼容的设置；凡需要 ABACUS 计算的示例，均包含面向 GPU 的 `ks_solver: cusolver` 设置。

当前项目布局中，所有示例 config YAML 文件均可通过 schema/配置加载：

- ABACUS primary configs：`01` 到 `08`、`10` 和 `11`。
- DeePMD configs：`config_dp.yaml` 文件已具备 schema 结构，但需要各示例文档中说明的用户自备 DP model 路径。没有该外部模型文件时，这些 DeePMD 变体并非完全自包含。
- IRC variants：`examples/10_irc_H2/config_forward.yaml` 和 `examples/10_irc_H2/config_reverse.yaml` 已具备 schema 可用性。

因此，ABACUS 示例预设可作为仓库提供的示例直接使用。DeePMD 变体在结构上已经可用，但按设计依赖外部模型文件。

## abacuslite 修改审计

已完成的验证过程确实涉及兼容性修改；这些修改已经属于项目历史，并已记录在 LTS 对比报告中。进一步审查后，将 version probe 策略从 vendored abacuslite 迁移到了 ATST-Tools 自己的 calculator/profile adapter 层，需要区分以下几类情况：

1. `src/atst_tools/calculators/abacuslite_backend.py` 新增 `ATSTAbacusProfile`。该 adapter 负责解析 `ABACUS version v3.9.0.17` 和 `ABACUS v3.10.1` 两类输出，并默认用裸 executable 执行 `abacus --version` 作为版本探测。
2. `src/atst_tools/calculators/factory.py` 现在继续把真实计算命令生成为 `mpirun -np N abacus`，但通过 `ATSTAbacusProfile` 将版本探测命令与真实计算命令解耦。
3. `calculator.abacus.version_command` 已加入配置 schema。复杂站点环境可显式设置完整 probe command，例如 `abacus --version` 或站点 wrapper。
4. `src/atst_tools/external/ASE_interface/abacuslite/core.py` 已把此前的 `version()` fallback 还原为 abacuslite 原生行为，即对自身 command 追加 `--version` 后直接解析；不再在 vendored abacuslite 内部实现 `mpirun ...` 到裸 executable 的 fallback。
5. STRU 写出仍保留元素首次出现顺序，而不是按字母顺序重排元素。这是 ATST-Tools examples 复现 main 分支 Cy-Pt STRU 块顺序所需的 vendored 兼容补丁。

进一步核查后可确认：

- `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite/core.py` 当前参考实现中的 `parse_version()` 只匹配 `ABACUS version ...`，未看到可直接解析 `ABACUS v3.10.1` banner 的实现。因此，ATST-Tools 仍需要能解析 LTS banner；但该解析现在位于 `ATSTAbacusProfile.parse_version()`，不再修改 vendored abacuslite 的原生 parser。
- `mpirun -np N abacus --version` 不是用户手写命令，而是 ATST-Tools 的 ABACUS factory 将 `command: abacus` 与 `mpi: N` 组合为 `mpirun -np N abacus` 后，再由 abacuslite `version()` 自动追加 `--version` 产生。对应代码路径是 `src/atst_tools/calculators/factory.py` 中的 `_build_abacus_command()` 与 `src/atst_tools/external/ASE_interface/abacuslite/core.py` 中的 `AbacusProfile.version()`。
- strict Slurm 失败日志显示，该 probe 在当时环境下返回空 stdout，并导致 `RuntimeError: Could not parse ABACUS version from output: ''`，calculator 尚未进入真实 ABACUS 计算就失败。因此，fallback 对当时的验证推进是有效 workaround。

从设计角度看，`version()` fallback 没有改变真实 ABACUS 计算命令，也没有改变 NEB、AutoNEB、Dimer、Sella、D2S 或 ABACUS 科学参数；最终可比的 jobs 均为真实 ABACUS LTS 3.10.1 计算，其能量、力、能垒、TS index 和结构记录在 `examples/reference_results.json` 中。但是，把复杂 version probe fallback 固化在 vendored abacuslite 内部并不是最优雅的长期设计。当前实现已经迁移为由 ATST-Tools 的 ABACUS calculator/profile 构造层显式区分“真实运行命令”和“版本探测命令”：

- 真实计算命令继续由 `command` 和 `mpi` 生成，例如 `mpirun -np 4 abacus` 或用户显式提供的 wrapper command。
- 版本探测默认使用裸 executable，例如 `abacus --version`，避免把 MPI launcher、Slurm slots、GPU/CPU allocation 等运行时约束带入轻量 version probe。
- 对复杂环境提供显式配置项，例如 `version_command` 或 `probe_command`，允许用户指定 `abacus --version`、`srun ... abacus --version` 或站点 wrapper。
- vendored abacuslite 内部保留其上游原生 `version()` 行为；launcher 选择、LTS banner 解析和 probe 策略由 ATST-Tools 的 adapter/factory 层负责。

因此，当前代码不再依赖 vendored abacuslite 的 `version()` fallback。该设计更符合“abacuslite 作为 CLI wrapper、ATST-Tools 负责工作流与运行环境适配”的边界。

## abacuslite 同步与 submodule 评估

对比 `temp_repos/abacus-develop/interfaces/ASE_interface` 后，本次只导入了与当前 vendored copy 明确相关且低风险的 `switch_io_backend_version()` 逻辑，并保留项目已有的相对导入与 STRU 元素首次出现顺序补丁。没有直接整体覆盖 `src/atst_tools/external/ASE_interface`，原因是当前 vendored copy 已包含 ATST-Tools 为包内导入、examples 复现和 ABACUS 输出容错做过的局部适配；直接覆盖会破坏这些已验证行为。

当前不建议把完整 `abacus-develop` 作为 git submodule 引入本项目。该仓库体量和演进范围远大于 ATST-Tools 实际需要的 `interfaces/ASE_interface`，会增加 clone、CI、版本固定和用户安装成本。更合适的机制是保留 vendored copy，并建立轻量同步流程：周期性对比 `temp_repos/abacus-develop/interfaces/ASE_interface` 或上游指定 commit，只挑选 ASE interface 相关更新；每次同步必须附带 diff 审计、单元测试和 examples smoke/reproduction 验证。若未来同步频率显著增加，可以考虑 git subtree 或专门的 sync script，而不是直接引入完整 submodule。

## 2026-07-02 上游 issue 复查

本次代码对比基于本地 `temp_repos/abacus-develop` 的 `develop` checkout
`33a7acdf4`；远端 `develop` 可能继续演进，后续向 `abacus-develop`
提交 PR 前需要重新 fetch/rebase 并复核 `ASE_interface` 差异。当前
vendored abacuslite 与上游参考实现仍只有四个 Python
文件存在差异：`core.py`、`io/generalio.py`、`io/latestio.py` 和
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

## 结论

对于具备 main 分支 TS/能垒基线的 examples，已有完成的验证证据表明这些案例可复现。当前仓库已经在 `examples/reference_results.json` 和 `examples/reference_structures/` 中保存了明确的能垒、过渡态 index、过渡态结构、最终 TS 结构和验证 job 元数据参考值。

abacuslite 模块在验证期确实有兼容性修复；本次复查后的关键调整是：`version()` fallback 已从 vendored abacuslite 内部移除，并迁移到 ATST-Tools 的 `ATSTAbacusProfile` 设计中。当前 vendored abacuslite 的保留差异和已测试修复以 `2026-07-02 上游 issue 复查` 小节为准：保留差异包括相对导入、STRU 元素首次出现顺序、ASE constraint mobility flags 和 legacy band-row 容错解析；另有 I/O backend version switch 逻辑已同步自上游参考实现。本次 vendored snapshot 还包含并由单元测试覆盖三个 issue 修复：numbered backup rotation、property keyword conflict validation 和 unsupported `dipole` de-advertising。ABACUS LTS 3.10.1 banner 解析和裸 `abacus --version` probe 均由 ATST-Tools adapter/factory 层负责。
