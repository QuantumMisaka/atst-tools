## 审查结论

复核日期：2026-05-11

实施更新：本报告早期审查指出的 NEB/D2S/lightweight CLI 缺口已在本轮补齐。`atst run` 仍是唯一耗时 workflow 入口；`atst neb make/post` 与 `atst traj` 仅做轻量前后处理。`atst run neb` 现在支持两种互斥输入：已有 `calculation.init_chain`，或嵌套 `calculation.make` 现场生成 chain 后运行。

最终状态摘要：

| 项 | 状态 | 说明 |
| --- | --- | --- |
| NEB restart shared helper | ✅ 完成 | `select_last_neb_chain()` strict 模式用于 restart；`select_post_neb_chain()` 用于 post/export |
| `atst run neb` 嵌套 make | ✅ 完成 | `init_chain` 与 `make` 二选一；`make.output` 默认 `init_neb_chain.traj` |
| `atst neb make` legacy-visible options | ✅ 完成 | 支持 `--fix`、`--mag`、`--from-chain`、`--ts`、`--no-align` |
| `sort_tol` / pymatgen autosort | ✅ 明确丢弃 | 不进入 CLI 或 YAML；继续使用 `Fast_IDPPSolver` 和现有 alignment |
| `atst neb post` AutoNEB/export | ✅ 完成 | 支持 `--autoneb-prefix`、`--autoneb-files`、`--write-latest`、`--write-neb-init-chain`、`--plot-all`、`--strict-band` |
| `atst neb post --view` | ✅ 修复 | 使用用户传入 trajectory，不再 hardcode `neb.traj` |
| `atst traj` namespace | ✅ 完成 | `collect` 与 `transform` 支持 trajectory roundtrip 和 NEB latest-band split |
| D2S optional vibration | ✅ 完成 | 默认关闭；`enabled: true` 后支持 `indices: auto/list/all` 和 thermochemistry JSON |

以下历史审查内容保留为决策背景；其中“缺失/未覆盖”的条目以上表最终状态为准。

历史结论：本报告对项目当前 NEB CLI 状态的核心判断真实有效。`atst run` 是唯一耗时 workflow 入口；`atst neb make/post` 是无 calculator 的轻量前/后处理入口；当前 `atst run neb` 不直接消费 `INIT FINAL N_IMAGES`，而是消费已经生成好的 `init_chain`。

进一步对比 main branch 的 `neb/neb_make.py`、`neb/neb_make_ori.py` 和 `neb/neb_post.py` 后，需要补充一个重要结论：当前 git-style CLI 尚未做到对 main branch NEB 轻量脚本的 100% 功能覆盖。当前实现已经覆盖了最小 make/post 主路径，并额外增强了部分鲁棒性，但 AutoNEB post、多文件输入、latest band 导出、部分 make 参数仍缺失。

### 1. atst run neb 输入和续算逻辑 ✅ 已确认

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 支持 neb-make 之后的输入（neb chain） | ✅ 是 | 通过 `calculation.init_chain` 指定，例如 `inputs/init_neb_chain.traj` |
| 支持直接基于 neb-make 的最小输入（INIT FINAL N_IMAGES） | ❌ 否 | 必须先通过 `atst neb make` 生成 init_chain，不能直接用两个结构作为 atst run 输入 |
| 续算时取最近一次 chain 作为输入 | ✅ 是 | `run_neb()` 在 restart=True 时：<br>1. 先从 init_chain_file 读取原始 n_images<br>2. 调用 `get_last_neb_band(traj_file, n_images)` 取最近完整 band<br>3. 用这个 band 继续计算 |

**代码位置**：`src/atst_tools/scripts/main.py:186-260`

---

### 2. atst run autoneb 功能 ✅ 已确认

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 输入要求 | ✅ 和 NEB 类似 | 需要 `calculation.init_chain` 指定一个预先生成的 chain |
| 续算逻辑 | ⚠️ 有差异 | AutoNEB 不是从一个单 trajectory 取 last band，而是：<br>- 保留已有的 `run_autoneb*.traj` 和 `AutoNEB_iter/`<br>- 从这些文件中恢复状态 |

**代码位置**：`src/atst_tools/mep/autoneb.py:152-274`

---

### 3. 是否需要新增 `atst <type> run` 轻量 CLI？

#### **结论：不需要** ✅ 保持当前设计

| 原因 | 说明 |
| --- | --- |
| 已有的 Workflow CLI Decisions 明确 | 当前设计是：<br>- `atst neb/dimer/relax/vibration`：轻量命令，无 calculator，仅前/后处理<br>- `atst run`：统一 YAML 驱动入口，处理所有耗时计算<br>新增 `atst <type> run` 会打破这个清晰的边界 |
| 用户体验一致性 | 当前 `atst run config.yaml` 是单一、统一的入口，用户只需要学习一种用法 |
| 避免代码重复 | 新增 `atst <type> run` 会导致和 `atst run` 大量重复的 YAML 加载/验证/计算器设置代码 |
| “覆盖 YAML 已有内容”的需求 | 可以通过以下方式实现，不需要新增 CLI 路径：<br>1. Python 脚本读取 YAML，修改字段，保存，然后调用 `atst run`<br>2. 保持 YAML 作为唯一配置源是良好设计 |
| 当前已有足够的灵活性 | `--show-template <type>` + 用户编辑 YAML 覆盖默认值，满足绝大多数场景 |

---

### 建议改进（可选）

如果确实需要简化 NEB 的“从 INIT FINAL 直接跑”流程，可以考虑：
1. 扩展 `atst neb make`，让它可选地接受一个配置模板，然后自动调用 `atst run`（一步完成 make + run）
2. 但这也要谨慎，因为会把轻量命令和计算命令耦合在一起

---

## 当前状态复核

### `atst run neb`

当前实现与报告一致：

- `calculation.init_chain` 是 NEB run 的必需输入，由 `ConfigLoader.validate()` 对 `neb` 类型检查。
- `run_neb()` 在非续算模式下读取 `init_chain` 的完整 image chain。
- `run_neb()` 在 `restart: true` 或 `atst run --restart` 时，先读取 `init_chain` 得到期望 band size，再从 `trajectory` 中调用 `get_last_neb_band()` 取最后一个完整 band。
- 续算边界是明确的：restart trajectory 必须存在，且 frame 数必须是 band size 的整数倍；否则报错。
- image 级并行是有条件启用的：只有用户通过 MPI 启动且 `world.size > 1` 时才实际并行；单进程下会降级为串行 image 计算并给出 warning。

当前未支持：

- `atst run neb` 不支持直接写 `init_structure`、`final_structure`、`n_images` 后在 workflow 内自动生成 chain。
- `atst run neb` 不会自动从 `atst neb make` 的命令参数生成或补全 YAML。
- NEB endpoint 能量/力是否需要在 post 阶段补算，当前不在 `atst run neb` 中处理。

### `atst neb make`

当前实现与报告一致：

- 命令形态为 `atst neb make INIT FINAL N_IMAGES -o OUTPUT --method IDPP|linear`。
- 只做结构插值与 chain 写出，不创建 calculator，不运行 ABACUS/DP。
- 当前参数已经覆盖主工作流需要的最小前处理能力。

可补充边界：

- `N_IMAGES` 在 CLI help 中表述为 intermediate images，输出 chain 的总 image 数为 `N_IMAGES + 2`。
- 命令目前不写 config，不检查后续 `atst run` 所需的 calculator/data 路径。

### main branch `neb_make.py` 覆盖度

对比对象：

- `main:neb/neb_make.py`
- `main:neb/neb_make_ori.py`
- 当前：`src/atst_tools/scripts/cli.py::_neb_make_command`
- 当前：`src/atst_tools/utils/idpp.py::generate`

覆盖结论：

| main 功能 | 当前状态 | 说明 |
| --- | --- | --- |
| 从 initial/final 生成 chain | ✅ 已覆盖 | `atst neb make INIT FINAL N_IMAGES` |
| IDPP / linear 插值 | ✅ 已覆盖 | 当前 `--method IDPP|linear` |
| 输出 `init_neb_chain.traj` | ✅ 已覆盖 | `-o/--output` |
| 输入 format 指定 | ✅ 已覆盖 | 当前 `--format` |
| endpoint energy/force 写入 `SinglePointCalculator` | ✅ 已覆盖且更稳健 | 当前 endpoint 缺少能量/力时回退到 `0.0` 和零力，main 新脚本会直接读取能量/力 |
| atom index 对齐 | ⚠️ 当前为新实现，不是 main 等价实现 | 当前默认 Hungarian alignment，`--no-align` 可关闭；main 新脚本使用 pymatgen `autosort_tol/sort_tol` |
| `sort_tol` | 🚫 明确丢弃 | 该能力依赖 pymatgen matching/autosort，在实践中已证明存在问题；不迁移到当前仓库 |
| `--fix height:direction` | ❌ CLI 未覆盖 | 当前 `generate()` 支持 `fix_height/fix_dir`，但 `atst neb make` 未暴露参数 |
| `--mag element:moment,...` | ❌ CLI 未覆盖 | 当前 `generate()` 支持 `mag_ele/mag_num`，但 CLI 未暴露参数 |
| 从已有 guess trajectory 取最后 `n_max+2` 个 image | ❌ 未覆盖 | main `neb_make_ori.py -i input_guess_chain.traj n_max` 支持 |
| TS guess 分段插值 | ❌ 未覆盖 | main `neb_make_ori.py --ts ts_guess` 支持 |
| pymatgen diffusion `IDPPSolver` | ⚠️ 当前替换为内部 `Fast_IDPPSolver` | 属于实现替换，不是逐字迁移；需用测试确认行为覆盖 |

因此，当前 `atst neb make` 不能声明已经 100% 覆盖 main branch 的 make 功能。若目标是功能等价，应至少补齐 CLI 参数暴露、已有 guess 输入、TS guess 分段插值，或明确文档化这些 legacy 能力不进入当前设计。

迁移决策：

- 除 `sort_tol` 外，main branch 中 `neb_make.py` / `neb_make_ori.py` 的其他用户可见能力都应迁移。
- `sort_tol` 相关能力不迁移，并应在用户文档中解释为有意丢弃，而不是遗漏。

### `atst neb post`

当前实现与报告一致：

- 命令形态为 `atst neb post TRAJ [--n-max N] [--plot] [--view] [--vib-analysis]`。
- 读取已有 NEB trajectory，调用 `NEBPost` 做 barrier、TS 结构提取和可选 vibration atom index 建议。
- 不创建 calculator，不提交作业。

可补充边界：

- TS 输出文件名当前固定为 `TS_get.cif`，并尽量写 `TS_get.stru`；CLI 暂无 `--output-prefix`。
- `--view` 当前底层 hardcode `ase gui neb.traj@-N:`，不是严格使用用户传入的 `traj_file`，这是一个需要修正的小缺陷。
- `--n-max 0` 依赖 `NEBTools` 自动推断 band size；复杂 trajectory 或 AutoNEB 输出场景下应鼓励用户显式传入 `--n-max`。

### main branch `neb_post.py` 覆盖度

对比对象：

- `main:neb/neb_post.py`
- 当前：`src/atst_tools/scripts/cli.py::_neb_post_command`
- 当前：`src/atst_tools/utils/post.py::NEBPost`

覆盖结论：

| main 功能 | 当前状态 | 说明 |
| --- | --- | --- |
| 普通 NEB 单 trajectory post | ✅ 已覆盖 | `atst neb post TRAJ --n-max N` |
| 自动推断 `n_images` | ✅ 已覆盖且更稳健 | 当前自动推断失败时 fallback 到全列表长度 |
| barrier 输出 | ✅ 已覆盖 | 当前还对缺失 calculator 的 image 做 fallback |
| TS 结构导出 `TS_get.cif/.stru` | ✅ 已覆盖且更稳健 | 当前用 `np.isclose`，并捕获 `.stru` 写出失败 |
| plot final band | ✅ 已覆盖 | `--plot` 调用 `plot_neb_bands()` |
| view final band | ⚠️ 有 bug | 当前保留 main 的 hardcode `ase gui neb.traj@-N:`，未使用用户传入 `traj_file` |
| plot all bands | ❌ CLI 未覆盖 | `NEBPost.plot_all_bands()` 存在，但 `atst neb post` 没有参数调用 |
| write latest band `.traj/.extxyz` | ❌ CLI 未覆盖且默认行为不同 | main 脚本默认调用 `write_latest_bands()`；当前 CLI 不写 latest band |
| `--autoneb {traj_files}` 多文件 post | ❌ 未覆盖 | main 支持 `python neb_post.py --autoneb file1 file2 ...`；当前 CLI 只接收单个 `traj_file` |

因此，当前 `atst neb post` 也不能声明已经 100% 覆盖 main branch 的 post 功能。它覆盖了普通 NEB 主路径，并改善了若干鲁棒性，但缺失 AutoNEB 多文件入口和 latest/all-band 输出。

### `atst neb post` 与 AutoNEB 结果

进一步确认结论：

- `NEBPost` 的核心输入是 `List[Atoms]`，并不要求这些 image 必须来自普通 NEB 的单个 `neb.traj`。因此从概念和工具实现上，它可以分析 AutoNEB 的最终 path。
- 当前 AutoNEB 主输出是多个单 image 文件：`<prefix>000.traj`, `<prefix>001.traj`, ...，以及 `AutoNEB_iter/` 中的迭代轨迹。它不是普通 NEB 那种“一个 trajectory 文件中连续写入多个完整 band”的格式。
- 当前 `atst neb post` CLI 只接受一个 `traj_file`，并调用 `ase.io.read(traj_file, index=":")`。所以它不能直接消费 `run_autoneb*.traj` glob 或多个 AutoNEB image 文件。
- 如果用户或后续工具先把 `run_autoneb000.traj ... run_autonebNNN.traj` 合并为一个 final-chain trajectory，`atst neb post` 可以对这个合并文件做 barrier、TS 提取和 vibration-index 分析。

已用当前重跑的 `03_autoneb_Cy-Pt` 输出做过本地确认：

- `run_autoneb000.traj` 到 `run_autoneb009.traj` 共 10 个 image 可以组成一个 final chain。
- `NEBPost(images, n_max=8)` 可得到 10-image chain。
- 将该 chain 写成单个 `.traj` 后，`get_last_neb_band(exported_chain, 10)` 可以正确读回 10 个 image。

需要明确区分：

- **可用于普通 NEB 续算/再优化**：可以。将 AutoNEB final chain 导出为单个 `init_chain`，即可作为 `atst run neb` 的 `calculation.init_chain`，或作为普通 NEB restart trajectory 中的一个完整 band。
- **可用于 AutoNEB 原生续算**：不能只靠 `atst neb post` 导出的 final chain。当前 AutoNEB restart 依赖保留 `<prefix>*.traj` 和 `AutoNEB_iter/` 状态；`AutoNEBRunner.run()` 在 `restart=True` 时不清理这些文件，让 ASE AutoNEB 从这些文件恢复。单个 final-chain trajectory 不是 AutoNEB 原生 restart state。

因此，NEB restart 取结构逻辑和 `NEBPost` 选取最后 chain 的逻辑只有在“输入是单个普通 NEB-style trajectory，且 frame 顺序为完整 band 重复”时是一致的。对 AutoNEB 的多文件输出，两者当前不一致：`NEBPost` 内部可以处理 image list，但 CLI 没有多文件入口；`get_last_neb_band()` 只处理单文件 trajectory。

### `atst neb post` 与 `atst run neb --restart` 的取轨迹逻辑

当前两套逻辑相关但不完全一致，暂时不能认为“一致可复用”：

| 场景 | `atst run neb --restart` | `atst neb post` |
| --- | --- | --- |
| 输入类型 | 单个 trajectory 文件 | 当前 CLI 也是单个 trajectory 文件 |
| band size 来源 | 读取 `init_chain` 的 image 数，作为 `expected_n_images` | `--n-max > 0` 时用 `n_max + 2`；`--n-max 0` 时由 `NEBTools._guess_nimages()` 推断 |
| frame 数校验 | 严格要求 trajectory frame 数是 band size 的整数倍 | 不严格校验，直接取最后 `n_images` 个 image |
| 返回内容 | 最后一个完整 band | 最后 `n_images` 个 image |
| 不完整 trajectory | 报错 | 可能仍取最后若干 image，存在误判风险 |
| AutoNEB 多文件 | 不支持 | `NEBPost` 核心可支持，但当前 CLI 不支持 |

可复用关系：

- 若 `atst neb post --n-max` 显式传入的 band size 与 `init_chain` image 数一致，且 trajectory frame 数为完整 band 重复，两者选出的 final chain 是一致的。
- 若使用 `--n-max 0` 自动推断，或 trajectory 末尾存在不完整 band，两者行为不等价。

开发结论：

- 应抽取一个共享 helper，例如 `select_neb_chain(images, n_images=None, strict=False)`。
- `atst run neb --restart` 使用 `strict=True`，保持当前严格 checkpoint 语义。
- `atst neb post` 默认可用 `strict=False`，但当用户传 `--strict-band` 或 `--write-neb-init-chain` 时应使用严格模式，避免导出不可续算 chain。
- AutoNEB 多文件输入应先排序读成 image list，再复用同一个 helper 选择/导出 chain。

必要性判断：有必要复用。当前 `get_last_neb_band()` 和 `NEBPost.__init__()` 都在做“从一组 frames 中选择最后一条 chain”的同类工作，但严格性、band size 来源和错误处理不同。短期看它们还能工作；长期看如果 `neb post` 增加 `--write-neb-init-chain`、AutoNEB final-chain 导出、restart 诊断，就会直接影响用户续算输入的可靠性。把选择逻辑抽为共享 helper，可以让“可用于续算的 chain”只由一处代码定义，同时保留 post 的宽松分析模式。

---

## main branch 全脚本迁移审计

本节按 main branch 顶层脚本能力核对当前仓库迁移情况。示例目录中的重复脚本按其所属功能归并，不逐个重复列出。

### NEB / AutoNEB

| main 脚本 | main 功能 | 当前覆盖情况 | 后续处理 |
| --- | --- | --- | --- |
| `neb/neb_run.py` | ABACUS NEB 计算 | ✅ 已迁移 | `atst run` + `calculation.type: neb`；当前还保留 image-level parallel 降级 warning 和 restart |
| `neb/autoneb_run.py` | ABACUS AutoNEB 计算 | ✅ 已迁移 | `atst run` + `calculation.type: autoneb`；restart 依赖 `<prefix>*.traj` 和 `AutoNEB_iter/` |
| `neb/neb_make.py` | pymatgen IDPP/linear chain 生成、`sort_tol`、fix、mag | ⚠️ 部分迁移 | 迁移 fix/mag；丢弃 `sort_tol`；当前 IDPP 替换为内部实现 |
| `neb/neb_make_ori.py` | ASE NEB 插值、已有 chain 续作输入、TS guess 分段插值、fix、mag | ⚠️ 部分迁移 | 迁移 `--from-chain`、`--ts`、fix、mag |
| `neb/neb_post.py` | 普通 NEB post、AutoNEB 多文件 post、barrier、plot、latest band、TS 导出 | ⚠️ 部分迁移 | 迁移 `--autoneb-prefix`/多文件输入、`--plot-all`、`--write-latest`、`--output-prefix`、`--strict-band` |
| `neb/neb_dist.py` | 两个结构之间的距离/Frobenius norm 检查 | ❌ 未迁移 | 可作为轻量命令 `atst neb distance INIT FINAL` 或通用 `atst structure distance`；P3，不阻塞核心 workflow |
| `neb/traj_collect.py` | 多结构收集成 trajectory，支持 `--no-calc` | ❌ 未迁移 | 可作为 `atst traj collect`；也可被 `atst neb post --autoneb-prefix` 内部替代 |
| `neb/traj_transform.py` | trajectory 转 extxyz/traj/ABACUS STRU/cif；NEB band 切分 | ❌ 未迁移 | 可作为 `atst traj convert`；NEB band 切分应复用 shared chain helper |

### Dimer / Sella / IRC / D2S

| main 脚本 | main 功能 | 当前覆盖情况 | 后续处理 |
| --- | --- | --- | --- |
| `dimer/dimer_run.py` | ABACUS Dimer 计算，输出 TS_dimer | ✅ 主体已迁移 | `atst run` + `calculation.type: dimer`；TS 输出可由 `atst relax post`/后处理补强 |
| `dimer/neb2dimer.py` | 从 NEB 结果生成 dimer 初猜和位移向量 | ✅ 主体已迁移 | `atst dimer make-from-neb`；仍可与 `neb post` 输出规范统一 |
| `dimer/neb2dimer_abacus.py` | ABACUS NEB -> endpoint opt -> Dimer 集成 | ✅/⚠️ 已以 D2S 迁移 | `calculation.type: d2s`, `method: dimer`；需继续验证 endpoint/post 输出等价 |
| `sella/sella_run.py` | ABACUS Sella TS 优化 | ✅ 主体已迁移 | `atst run` + `calculation.type: sella` |
| `sella/neb2sella_abacus.py` | ABACUS NEB -> endpoint opt -> Sella 集成 | ✅/⚠️ 已以 D2S 迁移 | `calculation.type: d2s`, `method: sella`；需补轻量 TS/IS/FS 导出一致性 |
| `sella/sella_IRC.py` | Sella IRC forward+reverse、normalize trajectory | ⚠️ 部分迁移 | `calculation.type: irc` 支持 both/forward/reverse 和 normalized trajectory；真实 ABACUS 下已划定边界，需后续稳健化 |
| `ase-dp/neb2dimer_dp.py` | DP NEB/Dimer/thermo 集成 | ✅/⚠️ 架构迁移 | `calculator.name: dp` + D2S + vibration thermochemistry；需 DP 实算回归 |
| `ase-dp/neb2sella_dp.py` | DP NEB/Sella/thermo 集成 | ✅/⚠️ 架构迁移 | `calculator.name: dp` + D2S/Sella + vibration thermochemistry；需 DP 实算回归 |
| `ase-dp/sella_dp_run.py` | DP Sella TS 优化 | ✅/⚠️ 架构迁移 | `calculator.name: dp`, `calculation.type: sella`；需 DP 实算回归 |
| `ase-dp/sella_dp_IRC.py` | DP IRC 和 normalized trajectory | ⚠️ 部分迁移 | 当前 IRC workflow calculator-agnostic，但 DP 回归未闭合 |

### Relax / Vibration / Thermochemistry / DP

| main 脚本 | main 功能 | 当前覆盖情况 | 后续处理 |
| --- | --- | --- | --- |
| `relax/relax_run.py` | ABACUS 结构优化 | ✅ 已迁移 | `atst run` + `calculation.type: relax` |
| `ase-dp/relax_dp.py` | DP 结构优化，输出 latest STRU/cif | ✅/⚠️ 主体迁移 | `calculator.name: dp`, `calculation.type: relax`；输出 latest 由 `atst relax post` 覆盖 |
| `vibration/vib_analysis.py` | 振动频率、ZPE、HarmonicThermo | ✅/⚠️ 已迁移并扩展 | `calculation.type: vibration` 支持 harmonic thermo、ZPE、restart cache 清理 |
| `vibration/idealgas_analysis.py` | IdealGasThermo，小分子热化学 | ✅ 已迁移 | `thermochemistry.model: ideal_gas`，已有 `examples/11_vibration_ideal_gas_H2` |
| `vibration/vib_displace.py` | 生成振动位移结构目录 | ❌ 未迁移 | 可作为后续 `atst vibration displace`；当前非发布核心路径 |
| `ase-dp/vib_dp.py` | DP 振动分析 | ✅/⚠️ 架构迁移 | `calculator.name: dp`, `calculation.type: vibration`；需 DP 回归 |
| `ase-dp/idealgas_dp.py` | DP 小分子 ideal gas thermo | ✅/⚠️ 架构迁移 | 当前 thermo calculator-agnostic；需 DP 示例确认 |
| `ase-dp/autoneb_dp.py`, `ase-dp/autoneb_dpa2.py` | DP AutoNEB | ✅/⚠️ 架构迁移 | `calculator.name: dp`, `calculation.type: autoneb`；需 DP 实算回归 |
| `ase-dp/dimer_dpa2.py` | DP Dimer | ✅/⚠️ 架构迁移 | `calculator.name: dp`, `calculation.type: dimer`；需 DP 实算回归 |

### source modules

| main 模块 | main 功能 | 当前覆盖情况 | 后续处理 |
| --- | --- | --- | --- |
| `source/abacus_neb.py`, `source/my_neb.py` | 自定义 NEB 封装 | ✅/⚠️ 已重构 | 当前 `atst_tools.mep.neb.AbacusNEB` 基于 ASE NEB；按重构要求舍弃 main 中额外实现细节 |
| `source/abacus_autoneb.py`, `source/my_autoneb.py` | AutoNEB 封装 | ✅/⚠️ 已重构 | 当前 `atst_tools.mep.autoneb` 包装 ASE AutoNEB |
| `source/abacus_dimer.py`, `source/my_dimer.py` | Dimer 封装 | ✅/⚠️ 已重构 | 当前 `atst_tools.mep.dimer.AbacusDimer` 基于 ASE Dimer |
| `source/neb2vib.py` | NEB TS 到 vibration 辅助 | ⚠️ 部分迁移 | 当前 `atst neb post --vib-analysis` 提供 atom index 建议；后续应补 `--write-vib-indices` |

总体结论：

- 当前仓库已经迁移了 main branch 的核心耗时 workflow：NEB、AutoNEB、Dimer、Sella、Relax、Vibration、D2S/NEB-to-single-end、IRC 的主入口。
- 当前仓库尚未完整迁移 main branch 的所有轻量工具能力，尤其是 trajectory collect/transform、AutoNEB post 多文件处理、NEB make 的 TS guess/from-chain/fix/mag。
- DP 相关脚本多已通过 calculator-agnostic YAML 架构映射，但仍需要 DP 实算回归，不能只凭接口存在声明 100% 行为等价。

## 后续开发方向

### P0：保持入口边界，不新增 `atst neb run`

维持当前设计：

- `atst run CONFIG.yaml`：唯一耗时 workflow 入口。
- `atst neb make/post`：轻量前/后处理，不创建 calculator。

理由：这能避免 YAML 加载、calculator 构建、restart、日志和 Slurm 使用方式在多个 CLI 路径中重复实现。后续补强应围绕“更容易生成正确输入”和“更容易检查输出”，而不是新增另一个 run 入口。

### P1：增强 `atst neb make` 到 `atst run neb` 的衔接

建议新增轻量能力，但不自动运行计算：

- `atst neb make --write-config config.yaml --calculator abacus`：在写出 `init_neb_chain.traj` 的同时生成最小 NEB YAML。
- `atst neb make --config-template existing.yaml`：读取用户模板，只更新 `calculation.init_chain`，不覆盖 calculator 参数。
- 在生成的 YAML 中明确 `init_chain`、`trajectory`、`fmax`、`max_steps`、`climb`、`parallel` 等字段。
- 单元测试：验证 make 仍可独立只写 chain；加参数时额外写出 YAML，且 `atst run --dry-run` 可通过。

这样保留 `atst run` 的统一入口，同时解决用户从 `INIT FINAL N_IMAGES` 到 YAML 的手工负担。

### P1：补齐 main branch `neb_make.py` 功能覆盖

建议按兼容优先级补齐：

- 暴露当前 `generate()` 已支持但 CLI 未暴露的参数：
  - `--fix HEIGHT:DIR`
  - `--mag ELEMENT:MOMENT[,ELEMENT:MOMENT...]`
- 增加 `--from-chain INPUT_TRAJ`，等价迁移 main `neb_make_ori.py -i`：从已有 guess trajectory 取最后 `N_IMAGES + 2` 个 image 并写出 output。
- 增加 `--ts TS_GUESS`，支持 initial -> TS -> final 的分段插值。
- 明确丢弃 `sort_tol`：不提供 `--sort-tol`，不复用 pymatgen autosort/matching 路径；当前 atom index alignment 继续使用仓库内实现，并保留 `--no-align`。
- 单元测试：
  - make 暴露 fix/mag 后，检查中间 image constraints/magmom；
  - `--from-chain` 只取最后完整 chain；
  - `--ts` 输出总 image 数和 TS 所在位置正确；
  - 当前默认 alignment 和 `--no-align` 行为不回退。

若不打算保留某个 legacy 能力，应在文档中显式标记为“有意不迁移”，不能声称 100% 覆盖。

### P1：补强 `atst run neb` 的 restart 可解释性

建议改进报错与日志，不改变算法：

- restart 开始时打印：`init_chain` band size、restart trajectory、选中的最后完整 band index。
- 当 trajectory frame 数不是 band size 整数倍时，错误信息提示可用 `atst neb post --n-max` 或检查损坏 trajectory。
- 增加 dry-run 输出中的 restart 诊断：如果 `--restart` 且 trajectory 存在，报告可用 band 数；不存在则提前报错。
- 单元测试覆盖：完整 band、非完整 band、缺失 trajectory、`--restart` 覆盖 YAML。

同时建议把 restart 选链逻辑抽到共享 helper，供 `atst neb post` 复用：

- `read_neb_trajectory(path)`：读取单文件 trajectory。
- `select_last_neb_chain(images, expected_n_images, strict=True)`：严格选择最后完整 band。
- `select_post_neb_chain(images, n_max=0, strict=False)`：post 友好包装，自动推断但可切 strict。
- `read_autoneb_final_chain(prefix_or_files)`：读取并排序 AutoNEB final image 文件。

### P1：补强 `atst neb post` 输出控制

建议增强后处理用户体验：

- 增加 `--output-prefix PREFIX`，控制 TS 结构输出名，默认仍为 `TS_get` 以保持兼容。
- 增加 `--write-latest PREFIX`，调用 `NEBPost.write_latest_bands()` 写出最后一个 band 的 `.traj/.extxyz`，方便后续 restart、Dimer、Sella、Vibration。
- 增加 AutoNEB final-chain 输入支持：允许 `atst neb post --autoneb-prefix run_autoneb` 或支持多个 positional trajectory 文件，把 `run_autoneb*.traj` 排序读入后交给 `NEBPost`。
- 增加 `--write-neb-init-chain PATH`，把普通 NEB 或 AutoNEB post 选中的 final chain 写成可直接用于 `atst run neb` 的 `calculation.init_chain`。
- 增加 `--plot-all`，迁移 main `plot_all_bands()` 能力。
- 默认是否写 `neb_latest.traj/.extxyz` 需谨慎：为兼容 main 可提供 `--write-latest neb_latest`，但不建议默认写文件，避免当前 CLI 产生隐式输出。
- 增加 `--strict-band`，当用户希望导出可续算 chain 时使用和 `run --restart` 一致的严格 frame 校验。
- 修正 `--view` 使用用户传入的 `traj_file`，不要 hardcode `neb.traj`。
- 对 `--n-max 0` 自动推断失败或可疑时给出清晰提示，建议用户显式传 `--n-max`。
- 单元测试覆盖 output prefix、latest band 写出、view 命令路径、无 energy/force 的 extxyz fallback、AutoNEB 多文件输入排序和导出。

### P2：NEB post 面向后续 workflow 的轻量桥接

建议增加不会触发 calculator 的结构导出能力：

- `atst neb post --write-ts ts_guess.traj|stru|cif`：明确输出 TS guess，供 Sella/Dimer/Vibration 使用。
- `atst neb post --write-vib-indices vib_indices.json`：把 `--vib-analysis` 的 atom indices 和 displacement vector 机器可读化。
- `atst neb post --write-neb-init-chain inputs/init_neb_chain.traj`：把普通 NEB 最后 band 或 AutoNEB final path 导出为普通 NEB 可消费的 chain。
- `atst dimer make-from-neb` 已经覆盖 Dimer 初猜和 displacement vector，可与 `neb post` 输出规范统一。

### P2：AutoNEB 续算边界文档化

建议明确写入用户文档和 CLI help：

- AutoNEB 原生续算需要保留 `<prefix>*.traj` 和 `AutoNEB_iter/`，并通过 `atst run --restart config.yaml` 或 `calculation.restart: true` 继续。
- `atst neb post` 导出的 final chain 适合转入普通 NEB、Dimer、Sella、Vibration 或静态检查；它不是 AutoNEB 原生 restart checkpoint。
- 如果用户想“从 AutoNEB 结果继续优化”，推荐路径是：`atst neb post --autoneb-prefix run_autoneb --write-neb-init-chain inputs/autoneb_final_chain.traj`，然后用 `calculation.type: neb` 运行普通 NEB refinement。

### P2：文档与 examples 补强

建议新增或补充：

- 在 `examples/09_lightweight_cli/` 增加完整串联文档：`atst neb make` -> `atst run --dry-run` -> `atst neb post` -> `atst dimer make-from-neb`。
- 在 `docs/user/CLI_REFERENCE.md` 明确：`atst neb make` 的 `N_IMAGES` 是中间 image 数，`atst run neb` 的 `init_chain` 是总 chain 文件。
- 在 `docs/user/CONFIG_REFERENCE.md` 补充 NEB restart 行为和 trajectory frame 数要求。

## 推荐执行顺序

1. 先修 `atst neb post` 的小缺陷和输出控制：`--output-prefix`、`--write-latest`、`--view` 使用传入轨迹。
2. 同一阶段加入 AutoNEB final-chain post 支持：`--autoneb-prefix` 或多文件输入，以及 `--write-neb-init-chain`。
3. 再做 `atst neb make --write-config`，把 lightweight preprocessing 和 YAML workflow 平滑连接。
4. 补齐 `atst neb make` 除 `sort_tol` 外的 legacy 能力：`--fix`、`--mag`、`--from-chain`、`--ts`。
5. 最后补 `atst run neb` restart 诊断与 dry-run 检查，并抽 shared chain selection helper。

这一路线不改变当前 CLI 架构，不引入 `atst neb run`，但能明显降低用户从结构准备、运行到后处理/续算的操作成本。
