# FastIDPP 算法比对与 08_d2s_Cy-Pt 问题溯源报告

日期：2026-05-25

## 背景与结论

本报告面向 ATST-Tools 项目管理者和 abacuslite/工作流协作者，解释 `08_d2s_Cy-Pt` 复现 main 分支 rough NEB/D2S 结果时暴露的 FastIDPP 路径差异问题。

核心结论如下：

- 旧 `Fast_IDPPSolver` 的工程目标是移除 pymatgen runtime dependency，并用 SciPy `L-BFGS-B` 快速优化 IDPP pair-distance objective；但它不是 pymatgen `IDPPSolver` 的算法等价实现。
- main 分支 `08_d2s_Cy-Pt` 基线来自 pymatgen diffusion 的 `IDPPSolver.from_endpoints(..., sort_tol=0.5)` 路径族。对该案例，复现目标不是“生成任意平滑 IDPP 路径”，而是“生成与 main/pymatgen 同一条初始路径”。
- 旧 FastIDPP 在中间 image 上与 main/pymatgen 路径存在约 `0.17-0.21 A` 的几何差异。对 Cy-Pt@graphene 这种表面反应体系，该差异足以把 rough NEB 初始链推入另一条高能几何通道。
- ABACUS 单点诊断排除了 calculator 本身造成 eV 级误差的可能；问题集中在进入 rough NEB 前的路径几何。
- 当前 `Fast_IDPPSolver` 已改为 pymatgen-compatible 的 NEB-like IDPP update，同时保持项目内部实现和轻依赖优势。修复后 job `429504` 复现 main rough NEB 能垒和后续 Sella 收敛行为。
- 综合效率与稳健性后，本项目最合适的默认实现不是“最快优化 IDPP objective”的实现，而是“以可接受插值成本稳定生成正确 NEB 初始路径”的实现；当前 pymatgen-compatible FastIDPP 最符合 ATST-Tools 的 examples 复现和 D2S 稳健性目标。

## 代码来源与对比对象

本次比对涉及三类实现：

1. 旧 FastIDPP：
   - 来源：`git show cfe63c8:src/atst_tools/utils/idpp.py`
   - 特征：`Fast_IDPPSolver` 基于 `scipy.optimize.minimize(..., method="L-BFGS-B")`。

2. 当前 FastIDPP：
   - 来源：`src/atst_tools/utils/idpp.py`
   - 特征：`Fast_IDPPSolver` 实现 pymatgen-compatible 的 NEB-like path relaxation。

3. 参照实现：
   - 来源：本地 `atst` 环境中的 `pymatgen.analysis.diffusion.neb.pathfinder.IDPPSolver`
   - 特征：main 分支 legacy Cy-Pt D2S 路径生成所依赖的算法族。

D2S 工作流调用点为 `src/atst_tools/workflows/d2s.py`。当前 `run_rough_neb()` 仍通过 `Fast_IDPPSolver.from_endpoints(init_atoms, final_atoms, n_images)` 生成 rough NEB 初始链，再进入 ASE `DyNEB` + `FIRE` 优化。

## 旧 FastIDPP 实现方式

旧实现的主要逻辑如下：

- `robust_interpolate()` 先在 scaled coordinates 中执行 PBC-aware linear interpolation，得到初始中间 images。
- `Fast_IDPPSolver.__init__()` 计算 endpoints 的 pair-distance matrix：
  - `d_start = start_atoms.get_all_distances(mic=self.mic)`
  - `d_end = end_atoms.get_all_distances(mic=self.mic)`
  - 对每个 image 线性插值得到 `target_dists`。
- weights 使用 endpoint 平均距离：
  - `avg_dists = (d_start[None, :, :] + d_end[None, :, :]) / 2.0`
  - `weights = 1.0 / (avg_dists**4 + eye * 1e-12)`
- `_objective_function()` 将所有中间 image 坐标展平成一个大变量，用当前坐标实时计算 MIC pair vectors：
  - 坐标转 fractional。
  - pair difference 做 `diff_scaled -= np.round(diff_scaled)`。
  - 再转回 Cartesian。
- objective 为全局 IDPP pair-distance loss：
  - `energy = 0.5 * np.sum(weights * delta_dists**2)`
  - gradient 直接由 pair-distance loss 求导。
- `run()` 使用 SciPy `minimize(..., method="L-BFGS-B", jac=True)` 优化所有中间 images。

该实现的优点是直接、轻量、易于移除 pymatgen 依赖；但它隐含了一个关键假设：直接优化 pair-distance objective 可以等价替代 pymatgen 的 IDPP path relaxation。08 案例证明这个假设不成立。

## 当前 FastIDPP 实现方式

当前实现保留 `robust_interpolate()` 作为初始猜测，但核心优化方式已改为与 pymatgen `IDPPSolver` 对齐：

- 每个 image 的 `target_dists` 仍由 endpoints distance matrix 线性插值得到。
- weights 改为按 image 依赖的平均距离构造：
  - `initial_distances = [img.get_all_distances(mic=self.mic) for img in images[1:-1]]`
  - `avg_dists = (target_dists + initial_distances) / 2.0`
  - `weights = 1.0 / (avg_dists**4 + eye * 1e-8)`
- `_build_translations()` 为每个中间 image、每个 atom pair 预先构造 nearest-image translation matrix。
  - 当前实现枚举 `(-1, 0, 1)^3` 的 fractional shifts，选择最短 Cartesian vector。
  - 这对应 pymatgen 中 `lattice.get_distance_and_image()` 返回 image translation 的用法。
- `_get_funcs_and_forces()` 用固定 translation matrix 计算 IDPP objective 和 “true forces”。
- `_get_total_forces()` 加入 NEB-like tangent 和 spring force：
  - 由相邻 image 的 flattened displacement 构造 tangent。
  - spring force 沿 tangent 控制 image spacing。
  - IDPP true force 的 tangent 分量被投影掉，只保留垂直于路径的有效分量。
- `run()` 不再调用 L-BFGS-B，而是按 pymatgen 风格迭代更新：
  - `disp = step_size * total_forces`
  - 每个分量裁剪到 `max_disp`
  - 以内置 residual 和 max-force 双条件判断收敛。

这使当前 FastIDPP 不再是“另一个 IDPP optimizer”，而是“pymatgen IDPP 更新规则的项目内实现”。

## 算法差异表

| 维度 | 旧 FastIDPP | 当前 FastIDPP | 对 08 案例的影响 |
| --- | --- | --- | --- |
| 优化器 | SciPy `L-BFGS-B` 全局优化 flattened coordinates | pymatgen-compatible NEB-like iterative update | 旧实现可能收敛到 pair-distance loss 上可接受、但与 main path 不同的路径 |
| 路径约束 | 没有显式 spring/tangent projection | 加入 tangent、spring force、perpendicular true force | 当前实现维持 image spacing 和路径形态，更接近 pymatgen/main |
| weights | endpoint 平均距离 `((d_start+d_end)/2)^-4` | 每个 image 的 `(target_dist+initial_dist)/2` 的 `1/d^4` | 旧实现对中间 image 的局部 pair-distance 权重不等价于 pymatgen |
| PBC/MIC | objective 计算时动态 `round()` fractional pair difference | 每个 image/pair 固定 nearest-image translation matrix | 当前实现更贴近 pymatgen 的 `get_distance_and_image()` 路径 |
| 单步控制 | L-BFGS-B 内部步长控制 | `step_size` + `max_disp` 显式控制 | 当前实现避免一步跨越到远离初始路径的几何区域 |
| 收敛判据 | SciPy optimizer status + gradient norm | objective residual + max force component | 当前实现与 pymatgen IDPP stop criteria 更一致 |
| 目标定位 | 快速独立 IDPP 优化器 | main/pymatgen 路径等价实现 | 当前实现满足 examples 复现需求 |

## 综合评价：效率、稳健性与适用场景

从单次插值调用看，旧 L-BFGS-B FastIDPP 具有明确优势。它的实现短、依赖轻，只需要 SciPy `minimize()` 和 ASE `Atoms`，不需要 pymatgen，也不需要在每一步显式构造 NEB-like total forces。对于小体系、非周期体系，或只需要一个较平滑的经验初猜而不要求复现 legacy pymatgen 路径的场景，这种实现有现实价值。`temp_repos/mace-reaction-kit/mace_asekit/workflows/neb.py` 中的 `_IDPPSolver` 也采用了同类方案，说明该路线作为轻量工程实现并非没有合理性。

但是，ATST-Tools 的 D2S/NEB examples 复现关注的是全工作流效率，而不是 IDPP 子步骤的局部耗时。08 案例中，旧 FastIDPP 的插值本身可能更快，但它生成的路径使后续 ABACUS rough NEB 进入高能通道，job `429068` 在 4V100 上运行数小时后 barrier 继续升高并被取消。相比之下，当前 FastIDPP 的插值步骤更接近 pymatgen 的 NEB-like update，单次插值可能不如旧 L-BFGS-B 简洁，但它让 rough NEB 从正确路径盆地启动，避免后续昂贵的 GPU ABACUS 计算跑飞。因此从“完成一次可复现实例”的总成本看，当前实现更高效。

从算法稳健性看，当前实现的优势来自路径约束而不是优化器复杂度。旧实现直接最小化 pair-distance objective，允许所有中间 image 坐标作为一个全局变量被 L-BFGS-B 调整；这能快速降低 objective，但不显式约束 image spacing、path tangent 和 PBC pair-vector continuity。当前实现把 IDPP force 放入 NEB-like relaxation：spring force 控制相邻 image 间距，tangent projection 让 IDPP true force 主要作用在路径垂直方向，固定 nearest-image translation matrix 保持 pair-vector 连续性。这些机制正是表面反应、斜晶胞和跨 PBC 位移体系需要的稳健性来源。

不同实现的推荐定位如下：

| 实现 | 最适用场景 | 不适用场景 | 综合定位 |
| --- | --- | --- | --- |
| 旧 L-BFGS-B FastIDPP / mace NEB `_IDPPSolver` | 小体系、快速初猜、实验性轻量工作流、无需复现 pymatgen/main 路径的任务 | D2S examples 复现、复杂表面反应、对路径盆地敏感的 ABACUS rough NEB | 有效率优势，但不适合作为 ATST-Tools 默认复现实现 |
| pymatgen `IDPPSolver` | 作为 legacy baseline 和算法行为参考 | ATST-Tools 默认 runtime，尤其是希望保持轻依赖和 ASE `Atoms` 数据流时 | 算法参考可靠，但依赖和对象转换成本较高 |
| ASE 原生 IDPP | 普通 ASE-native NEB、用户不要求 main/pymatgen legacy path 等价时 | 需要精确复现 main 分支 pymatgen IDPP 路径的案例 | 通用性好，但不是本项目 08 复现的最强保证 |
| 当前 pymatgen-compatible FastIDPP | ATST-Tools 默认 D2S、examples 复现、复杂 PBC/表面反应路径 | 极端追求最短代码或单次插值最低开销的实验场景 | 综合最优：轻依赖、ASE-native、可复现、路径稳健 |

因此，旧实现的效率价值应被承认，但它更适合作为可选实验方案或快速初猜工具；当前实现更适合作为 ATST-Tools 的生产默认，因为它优化的是完整工作流的成功率和复现性。

## 08_d2s_Cy-Pt 实测证据

`08_d2s_Cy-Pt` 的 endpoints 本身并不是问题来源。已完成的报告记录显示：

- 当前 `examples/08_d2s_Cy-Pt/inputs/init.stru` 对 main `STRU_IS`：endpoint RMSD `0.00054 A`。
- 当前 `examples/08_d2s_Cy-Pt/inputs/final.stru` 对 main `STRU_FS`：endpoint RMSD `4e-6 A`。
- atom ordering 和 formulas 一致。

在旧 FastIDPP 下，clean retry job `429068` 即使对齐了 `scale_fmax=1.0` 和 IDPP `5000/1e-3` 控制，仍然生成了非 main-like rough path：

- 第一条 rough band 的 main relative energies, eV：
  `[0.000, 0.236, 0.765, 1.376, 1.989, 2.463, 2.679, 2.545, 2.090, 1.425, 0.747, 0.395]`
- `429068` 第一条 rough band relative energies, eV：
  `[0.000, 3.055, 3.627, 4.346, 5.070, 5.343, 5.439, 5.655, 5.125, 4.546, 4.143, 0.395]`

这说明路径刚进入 rough NEB 时已经处于明显不同的高能通道。随后 job `429068` 写出十个 rough bands，barrier 从 `5.655415 eV` 升至 `23.248852 eV`，TS fmax 升至 `26.143183 eV/A`，最终被取消。

为了排除 calculator/execution-stack 本身误差，job `429445` 直接用 ABACUS LTS 3.10.1 + `cusolver` 重算 main first-band TS image 6：

- stored main energy：`-11864.151250632500 eV`
- LTS recalc energy：`-11864.151272551300 eV`
- energy delta：`-2.19e-5 eV`
- fmax delta：`-6.7e-5 eV/A`

这排除了 “ABACUS LTS/cusolver 对 exact main geometry 给出 multi-eV 偏差” 的可能。问题集中在 rough NEB 入口前的 IDPP path geometry。

离线几何诊断进一步确认：

- pymatgen IDPP 生成的 images 与 main `neb_images.traj` first-band images 只差约 `5e-6` 到 `1.3e-5 A`。
- 旧 FastIDPP 的中间 images 与 main/pymatgen 差约 `0.17-0.21 A`。
- 修复后当前 FastIDPP 与 pymatgen IDPP 在 printed precision 下 RMSD 为 0。

最终验证 job `429504` 使用修复后的 FastIDPP，并完成 rough NEB + Sella：

- first rough barrier：`2.678812 eV`
- main first rough barrier：`2.678795 eV`
- delta：`+0.000017 eV`
- last rough barrier：`1.714806 eV`
- main last-band rough barrier 约：`1.715682 eV`
- last rough barrier delta：约 `-0.000876 eV`
- Sella final fmax：`0.039662 eV/A`
- Sella final energy：`-11865.557601 eV`

## 问题来源分析

旧 FastIDPP 的问题不是“不能生成平滑路径”，而是“生成的路径不等价于 main/pymatgen 的 IDPP 路径”。在 08 案例中，这一点足以导致 eV 级结果偏差，原因如下：

1. D2S rough NEB 对初始路径高度敏感。

   D2S 先生成 rough NEB chain，再从 rough path 中提取 TS guess 进入单端 Sella/Dimer。rough NEB 的优化器是局部路径优化器，不是全局反应路径搜索器。如果初始 chain 已经进入另一条高能几何通道，后续 DyNEB/FIRE 不保证能跨回 main MEP basin。

2. Cy-Pt@graphene 是局部几何敏感体系。

   该体系包含 graphene/Cy/Pt/H 的表面吸附和反应构型。中间 image 中 Pt、H、环状碳结构与基底的相对位置变化，在 0.1 A 量级就可能显著改变局部 bonding、short contacts、adsorbate-substrate interaction 和电子结构收敛路径。因此 `0.17-0.21 A` 的中间 image 偏差不能被视为 harmless interpolation noise。

3. 旧实现优化目标与 pymatgen 路径生成目标不同。

   旧实现用 L-BFGS-B 直接最小化 pair-distance loss。该 objective 不包含 NEB-like spring/tangent projection，也没有 pymatgen 的 fixed translation matrix 处理。因此，即使 pair distances 在某种意义上被优化，image spacing 和路径形态也可能偏离 main/pymatgen。

4. PBC nearest-image 处理差异会改变 pair vector continuity。

   旧实现每次 objective 中对 fractional pair difference 做 `round()`，属于动态 MIC 选择；当前实现和 pymatgen 对每个 image/pair 使用固定 nearest-image translation matrix。对于 slab/斜晶胞/跨边界移动的吸附体系，translation 选择差异会改变 pair vector 的连续性，从而改变 IDPP force direction。

5. weights 差异改变了近距离 pair 的主导程度。

   IDPP 使用 `1/d^4` 权重，近距离 pair 对路径优化影响极大。旧实现用 endpoint 平均距离构造 weights；pymatgen/current 实现按每个 image 的 target distance 与 initial image actual distance 平均构造 weights。对中间 images，权重矩阵不同会改变优化时哪些 pair 被强烈惩罚，进而改变路径。

因此，旧 FastIDPP 的“更快、更少依赖”没有自动转化为“更稳健地复现 main”。它在工程依赖层面更轻，但在数值路径层面缺少与 legacy baseline 的等价性。

## 当前修复方案

当前修复没有重新引入 pymatgen runtime dependency，而是在 ATST-Tools 内部实现 pymatgen-compatible 的关键算法：

- 保留 ASE `Atoms` 输入输出，继续适配项目 CLI/YAML 工作流。
- 保留 `robust_interpolate()` 作为初始猜测来源。
- 在 `Fast_IDPPSolver` 内部实现 image-dependent weights、nearest-image translation matrix、NEB-like tangent/spring update 和 max-displacement 限制。
- D2S 仍通过 `Fast_IDPPSolver.from_endpoints()` 调用，不改变用户接口。

这使当前实现同时满足两类目标：

- 工程目标：不依赖 pymatgen runtime，仍可在 `atst-dev` 中直接运行。
- 复现目标：对 main 使用 pymatgen IDPP 生成的 legacy path，当前 FastIDPP 能生成等价路径。
- 稳健目标：在 D2S rough NEB 入口前生成与 main/pymatgen 同一路径盆地的初始链，降低后续 ABACUS 优化跑飞风险。
- 成本目标：用略高的插值复杂度换取更低的全工作流失败成本；对 08 案例，这比旧 L-BFGS-B 插值的局部速度优势更重要。

## 对项目后续维护的建议

1. 保留当前 pymatgen-compatible FastIDPP 作为默认实现。

   08 案例已证明，路径等价性对 D2S 复现比“独立优化器看起来更先进”更重要。默认实现应优先保证 legacy baseline 可复现。

2. 不建议恢复旧 L-BFGS-B FastIDPP 作为默认 D2S 路径生成器。

   旧实现可以作为研究性 alternative、快速初猜工具或实验分支保留。它在轻量化和单次插值效率上有优势，但不应作为 examples 或用户默认路径。若未来要重新引入，必须用 08 类表面反应案例做 geometry-level、barrier-level 和 full-workflow 成功率验证。

3. 为 FastIDPP 保持单元测试和案例级参考值双重保护。

   单元测试应覆盖 PBC robust interpolation、nearest-image 行为和参数透传；examples/reference results 应继续钉住 `08_d2s_Cy-Pt` 的 first rough barrier、TS index、last rough barrier 和 Sella final fmax。

4. 在用户文档中明确区分“去除 pymatgen 依赖”和“复现 pymatgen IDPP 行为”。

   当前实现不是简单丢弃 pymatgen 算法，而是在不引入运行时依赖的前提下复刻其对本项目关键案例必要的 IDPP path relaxation 行为。

5. 若未来提供多个 IDPP backend，应明确标注适用范围。

   可以考虑在实验接口中区分 `pymatgen_compatible`、`ase_native` 和 `legacy_l_bfgs`。其中 `pymatgen_compatible` 应继续作为 D2S/examples 默认；`ase_native` 面向普通 ASE 工作流；`legacy_l_bfgs` 仅用于快速初猜或算法对比，并需要在文档中提示其不保证复现 main/pymatgen legacy path。

## 结论

`08_d2s_Cy-Pt` 的实测结果表明，旧 FastIDPP 的主要问题是算法等价性不足，而不是 ABACUS calculator、abacuslite STRU 顺序或 endpoints 输入错误。旧实现基于 L-BFGS-B 直接优化 pair-distance objective，缺少 pymatgen IDPP 的 image-dependent weights、fixed nearest-image translations 和 NEB-like tangent/spring update，导致中间 images 偏离 main/pymatgen 路径约 `0.17-0.21 A`。该偏离在表面反应体系中被 rough NEB 放大为 eV 级能垒差异和路径失稳。

当前 FastIDPP 修复后，ATST-Tools 保留了内部实现与轻依赖优势，同时恢复了与 main/pymatgen IDPP 路径的数值等价性。job `429504` 的 rough NEB 和 Sella 结果确认该修复是 08 案例复现 main baseline 的关键条件。旧 L-BFGS-B FastIDPP 仍有轻量和局部效率优势，但在 ATST-Tools 的默认 D2S 语境下，当前 pymatgen-compatible FastIDPP 是更稳健、更可复现、全工作流成本更低的实现。
