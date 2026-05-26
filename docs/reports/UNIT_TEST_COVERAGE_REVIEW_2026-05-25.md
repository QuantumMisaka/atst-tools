# ATST-Tools 单元测试覆盖审查报告

日期：2026-05-25

本报告以 `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md` 中的 examples 复现结论，以及当前 `src/atst_tools` 核心实现为参考，审查现有单元测试对项目关键功能和复现实例的覆盖情况。

## 审查范围与方法

审查对象为 `tests/unit` 下的单元测试，以及 `src/atst_tools` 下的项目代码。覆盖率统计使用当前 `atst-dev` 环境中的 `coverage.py 7.14.0`；`pytest-cov` 插件当前不可用，因此未使用 `pytest --cov`。

执行命令：

```bash
conda run -n atst-dev pytest tests -q
conda run -n atst-dev pytest tests --collect-only -q
conda run -n atst-dev python -m coverage run --source=src/atst_tools -m pytest tests -q
conda run -n atst-dev python -m coverage report -m
conda run -n atst-dev python -m coverage report -m --omit='src/atst_tools/external/ASE_interface/abacuslite/*','src/atst_tools/external/ASE_interface/tests/*'
```

## 测试清单与运行结果

当前 `tests/unit` 共 12 个测试文件，pytest 收集 133 个测试。`conda run -n atst-dev pytest tests -q` 结果为全部通过。

| 测试文件 | 测试数 | 主要覆盖内容 |
| --- | ---: | --- |
| `test_config.py` | 30 | YAML 配置加载、schema 校验、默认值、非法字段、backend selector、D2S/IRC/vibration 参数 |
| `test_workflows.py` | 37 | NEB、AutoNEB、D2S、Dimer、Sella、Relax、Vibration、IRC 的 workflow 调度与关键参数传递 |
| `test_cli.py` | 25 | `atst` CLI、run/config/abacus/neb/dimer/relax/vibration/traj 子命令与 post/pre 处理 |
| `test_factory.py` | 9 | ABACUS/DP calculator factory、DP 共享策略、type map/dict 冲突、backend 来源日志 |
| `test_restart_helpers.py` | 8 | NEB/AutoNEB restart 轨迹读取、vibration cache 检查与清理 |
| `test_neb_endpoints.py` | 7 | NEB endpoint single-point 结果修复、placeholder 策略、AutoNEB 初始文件写出前修复 |
| `test_abacuslite_profile.py` | 6 | ABACUS LTS 3.10.1 version 解析、MPI version fallback、STRU species 顺序 |
| `test_examples.py` | 3 | 所有 example config 可解析/校验、ABACUS 示例使用 `ks_solver: cusolver`、输入路径存在 |
| `test_config_governance.py` | 3 | schema 字段说明、自动生成 YAML 变量文档、冗余公开路径治理 |
| `test_examples_reference_results.py` | 2 | `reference_results.json` 覆盖全部示例、barrier case 的 TS 参考产物存在 |
| `test_thermochemistry.py` | 2 | harmonic / ideal-gas vibration 热化学结果 |
| `test_idpp.py` | 1 | Fast IDPP 在斜晶胞下使用 Cartesian nearest image 的回归测试 |

## 覆盖率总览

全量 `src/atst_tools` 覆盖率为 50%。该数字包含 vendored `abacuslite` 解析器和工具模块，其中 `latestio.py`、`legacyio.py`、`ksampling.py` 等大体量代码目前没有单元覆盖，会显著拉低总覆盖率。

排除 `src/atst_tools/external/ASE_interface/abacuslite/*` 和 `src/atst_tools/external/ASE_interface/tests/*` 后，ATST-Tools 核心代码覆盖率为 68%。

| 模块域 | 代表文件覆盖率 | 评价 |
| --- | --- | --- |
| 配置/schema | `config_schema.py` 97%，`config_docs.py` 90%，`config.py` 75% | 覆盖充分，是当前最稳固的单元测试区域 |
| Calculator factory | `factory.py` 92%，`dp.py` 86%，`abacuslite_backend.py` 92% | 覆盖较好，重点覆盖参数归一、DP 共享与 backend 选择 |
| CLI | `scripts/cli.py` 85%，`scripts/main.py` 66% | CLI 子命令覆盖较广，run 主流程仍有未覆盖分支 |
| Workflow | `d2s.py` 79%，`irc.py` 73%，`relax.py` 76%，`vibration.py` 87% | 高层工作流覆盖较好，主要依赖 mock 和 monkeypatch |
| MEP 核心 | `autoneb.py` 50%，`dimer.py` 54%，`neb.py` 58%，`sella.py` 23% | 数值核心路径覆盖不足，尤其 Sella wrapper |
| 工具模块 | `neb_endpoints.py` 87%，`restart_helpers.py` 82%，`thermochemistry.py` 89%，`idpp.py` 44%，`post.py` 33%，`analysis.py` 19%，`io.py` 30% | endpoint/restart/thermochemistry 较好，post/analysis/io/IDPP 仍需补强 |
| vendored abacuslite | `core.py` 50%，`generalio.py` 45%，`latestio.py` 0%，`legacyio.py` 0% | 项目关键补丁点有定向测试，但不应将整个 vendored backend 视为已充分覆盖 |

## 关键功能覆盖情况

现有单元测试对配置系统覆盖较完整：支持的 calculation type、必填 workflow input、calculator section 匹配、DP model、DP `type_map` / `type_dict` 冲突、IRC direction、vibration thermochemistry model、YAML alias 治理、optimizer kwargs、NEB/AutoNEB backend selector、D2S NEB 参数和 schema 文档治理均有测试。

计算器构造层覆盖了 ABACUS 配置扁平化、ABACUS backend 来源日志、DP calculator 构造、`head` / `type_dict` 参数、OMP 线程设置、共享 calculator cache key 和 `share_calculator: false`。这能支撑 examples 中 ABACUS/DP 配置能被项目代码正确消费的基本判断，但不等价于真实 ABACUS/DeePMD 集成测试。

NEB/AutoNEB/D2S 相关测试覆盖了 DP 共享 calculator、native ASE backend selector、optimizer kwargs、AutoNEB fmax/maxsteps schedule、Issue #25 的 serial AutoNEB fmax schedule、endpoint constraint 继承、IDPP 控制参数和 D2S endpoint optimization 策略。结合复现报告，当前单元测试能够防止复现过程中暴露出的 endpoint、IDPP、AutoNEB schedule 和 backend selector 类回归。

Dimer、Sella、Relax、Vibration、IRC 的高层调度已有 mock 级测试：Dimer 覆盖位移 mask、`max_num_rot`、轨迹写出和 DP calculator 选择；Sella 覆盖 calculator 选择；Relax/Vibration/IRC 覆盖基本运行、结果写出、cache 错误处理和 IRC boundary error 报告。缺口是这些测试多数不执行真实优化器数值路径。

abacuslite 兼容修复有直接单元测试：`ABACUS v3.10.1` banner 解析、MPI `abacus --version` 空 stdout fallback、STRU first-occurrence species order 和模板元素分组。这与 examples 复现报告中的 abacuslite 审计结论一致。

## Examples 复现案例映射

| 复现案例 | 单元测试覆盖现状 | 剩余风险 |
| --- | --- | --- |
| `01_neb_Li-Si` | `test_examples_reference_results.py` 检查 barrier reference、TS index、正能垒和 TS 结构文件；`test_neb_endpoints.py` 覆盖 Li-Si endpoint regression；NEB workflow/CLI 有 mock 覆盖 | 未在单元测试中重算真实 ABACUS barrier |
| `02_neb_H2-Au` | reference results、example config、NEB workflow/CLI 路径有覆盖 | 未校验参考 barrier 数值本身是否等于报告值 |
| `03_autoneb_Cy-Pt` | reference results、AutoNEB runner、native backend、schedule、endpoint 修复和 abacuslite STRU species order 有覆盖 | 未在单元测试中执行真实 AutoNEB 或 ABACUS image 计算 |
| `04_dimer_CO-Pt` | Dimer workflow、位移 mask、旋转参数、轨迹写出有覆盖 | reference JSON 中最终 TS energy/fmax/RMSD 未被逐项断言 |
| `05_sella_H2-Au` | Sella calculator 选择和相关 workflow 调度有基础覆盖 | `mep/sella.py` 覆盖率仅 23%，最终 TS reference 未被逐项断言 |
| `06_relax_H2-Au` | example config/schema、RelaxWorkflow mock 运行、relax post 覆盖 | 无真实 ABACUS relax 集成测试 |
| `07_vibration_H2-Au` | example config/schema、VibrationWorkflow、cache 校验、post 结果写出、thermochemistry 覆盖 | 振动位移真实 ABACUS 计算未在单元测试中执行 |
| `08_d2s_Cy-Pt` | reference barrier case、D2S rough NEB 参数、IDPP 控制、endpoint optimization、Dimer/Sella 链路有覆盖 | D2S 全流程真实计算复杂，单元测试只覆盖调度和关键参数 |
| `09_lightweight_cli` | CLI pre/post、neb/dimer/relax/vibration/traj 子命令 fixture 覆盖较多 | 缺少端到端 CLI golden output 测试 |
| `10_irc_H2` | example config/schema、IRC forward/reverse、boundary error 和 unrelated assertion 处理有覆盖 | 真实 Sella IRC 数值路径未执行 |
| `11_vibration_ideal_gas_H2` | example config/schema、ideal-gas thermochemistry 覆盖 | reference output schema 仅间接覆盖 |

## 主要缺口与补测建议

优先级高：

1. 为 `examples/reference_results.json` 增加更强断言：逐项检查 01/02/03/08 barrier、TS index、结构路径，04/05 final energy/fmax/RMSD，08 Sella final energy/fmax，防止参考值漂移。
2. 为 `mep/sella.py` 增加 wrapper 初始化、trajectory、restart/异常路径的 mock 测试，将当前 23% 覆盖提升到至少与 Dimer 同级。
3. 为 `utils/post.py`、`utils/analysis.py` 和 `utils/io.py` 增加小型 ASE trajectory/Atoms fixture，覆盖 barrier/TS 提取、位移分析和结构读取错误路径。

优先级中：

1. 补充 `scripts/main.py` 中模板、参数解析、错误分支和 run dispatch 的轻量测试，减少 CLI 与 run 层之间的未覆盖分支。
2. 为 `utils/idpp.py` 增加 `align_atom_indices`、`robust_interpolate`、metadata preservation、fix/magmom helper 的直接测试；目前只有一个斜晶胞 nearest-image 回归测试。
3. 对 `utils/abacus_io.py` 增加 ABACUS INPUT/KPT/STRU roundtrip 与异常 log fixture 测试。

优先级低：

1. vendored abacuslite 的 `latestio.py`、`legacyio.py` 和 `ksampling.py` 覆盖率为 0%，但这些是第三方 backend 代码。除项目实际 patch 点外，不建议把全面覆盖 vendored 代码作为短期目标。
2. legacy console scripts `scripts/neb_make.py` 和 `scripts/neb_post.py` 覆盖率为 0%。如果保留为正式入口，应补 smoke tests；如果只是兼容入口，应在文档中明确。

## 结论

当前单元测试对 ATST-Tools 的配置治理、examples 配置可用性、calculator factory、CLI 主路径和 workflow 调度已有较好覆盖。核心代码排除 vendored abacuslite 后覆盖率为 68%，足以作为重构期基础质量门槛，但还不足以证明 MEP 数值核心和真实 ABACUS/DeePMD 集成路径完全可靠。

结合 examples 复现报告，本项目的单元测试已经覆盖了复现过程中最关键的回归点：配置可加载、ABACUS GPU solver 预设、reference results 存在、NEB endpoint 修复、AutoNEB schedule、D2S IDPP/endpoint 参数、abacuslite version fallback 和 STRU species order。下一步最有价值的补强方向是把 reference results 的数值断言补全，并提高 Sella、post analysis、IDPP 和 ABACUS IO 的单元覆盖。

## 测试机制完善结果

日期：2026-05-25

本轮按“默认快速本地测试 + 可选集成测试标记”的策略完善了测试机制。默认 `pytest tests -q` 仍不依赖真实 ABACUS、DeePMD、GPU 或 Slurm；需要调度系统的测试通过 `slurm` marker 和 `--run-slurm` 显式启用。

新增 pytest markers：

- `unit`：快速本地单元测试，不依赖外部可执行程序。
- `integration`：本地集成式 fixture 测试，不提交 Slurm。
- `slurm`：可能需要 ABACUS/DeePMD 和 Slurm allocation 的显式 opt-in 测试。

新增/增强测试覆盖：

- `examples/reference_results.json` 现在逐项钉住 `01/02/03/08` 的 barrier、TS index、TS/final 结构路径，以及 `04/05` final energy、fmax、RMSD 和 `08_d2s_Cy-Pt` 的 Sella final 参考值。
- `mep/sella.py` 新增 wrapper 级测试，覆盖 calculator 设置、trajectory、`eta`、`order`、`fmax` override、`max_steps` 和 legacy root `abacus.directory`。
- `utils/analysis.py` 新增位移主原子识别和零位移路径测试。
- `utils/post.py` 新增从 `atoms.info/arrays` 恢复能量/力并写出 latest band 的测试；该测试暴露并修复了 extxyz 写出时 calculator results 与已有 `atoms.info/arrays` 键冲突的问题。
- `utils/io.py` 新增普通 ASE 结构读取与 ABACUS `STRU` 读取测试，覆盖 mobility constraint 和 magmom 解析。
- `utils/abacus_io.py` 新增 parsed frame collection 和缺失 run dir 异常测试。
- `utils/idpp.py` 新增 atom index alignment、元素计数不匹配、PBC robust interpolation、fix/magmom helper 测试。

完善后测试规模：

| 测试文件 | 测试数 |
| --- | ---: |
| `test_abacuslite_profile.py` | 6 |
| `test_cli.py` | 25 |
| `test_config.py` | 30 |
| `test_config_governance.py` | 3 |
| `test_examples.py` | 3 |
| `test_examples_reference_results.py` | 8 |
| `test_factory.py` | 9 |
| `test_idpp.py` | 5 |
| `test_neb_endpoints.py` | 7 |
| `test_post_analysis_io.py` | 7 |
| `test_restart_helpers.py` | 8 |
| `test_thermochemistry.py` | 2 |
| `test_workflows.py` | 39 |

当前 pytest 收集测试数为 152 个，默认测试全部通过。

覆盖率变化：

| 覆盖口径 | 完善前 | 完善后 |
| --- | ---: | ---: |
| 全量 `src/atst_tools`，包含 vendored abacuslite | 50% | 53% |
| 排除 vendored abacuslite/tests 后的 ATST-Tools 核心代码 | 68% | 73% |

重点模块改善：

- `mep/sella.py`：23% -> 100%。
- `utils/analysis.py`：19% -> 95%。
- `utils/io.py`：30% -> 95%。
- `utils/idpp.py`：44% -> 64%。
- `utils/abacus_io.py`：63% -> 75%。
- `utils/post.py`：33% -> 43%，并修复了 latest band extxyz 写出冲突。

仍建议后续继续补强：

1. `utils/post.py` 中 barrier/TS 结构写出、plot fallback 和 view 分支仍未充分覆盖。
2. `scripts/main.py` 的模板、参数解析、错误分支和 run dispatch 仍有较多未覆盖分支。
3. `mep/autoneb.py`、`mep/dimer.py`、`mep/neb.py` 的数值核心仍主要依赖 mock 级测试；真实 ABACUS/DeePMD 路径应保留在显式 opt-in 的 integration/slurm 层。
