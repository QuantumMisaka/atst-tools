# atst-tools 侧设计记录：`atst prepare` 反向生成 + 轨迹应力保留

**日期**: 2026-08-12
**状态**: 待实施（设计已确认，等待 canonical spec 审阅批准）
**权威规格**: ABACUS toolbox
`docs/superpowers/specs/2026-08-12-atst-prepare-reverse-and-trajectory-stress-design.html`
（跨仓库协调文档，本记录只固化 atst-tools 上游专属决策，不复制全文）

## 范围

- **W1**: 新增顶层 `atst prepare` 命令与
  `atst_tools.api.build_config_from_abacus_dir(...)` Python API，从 ABACUS 运行
  目录（INPUT/STRU/KPT/PP/ORB）反向生成可运行的过渡态 YAML。
- **W2**: mep 层轨迹应力保留——`AbacusNEB.get_forces()` 收集应力（并行分支加入
  `world.sum`）、覆写 `AbacusNEB.iterimages()` 冻结含 stress、AutoNEB
  `store_E_and_F_in_spc` / `_store_E_and_F_in_spc_reduced` 冻结带 stress。

## atst-tools 专属决策

- **命令面**: 顶层 `atst prepare <abacus_run_dir> --workflow neb
  --init-structure ... --final-structure ... -o atst_neb.yaml`；
  `atst neb make` 保持纯插值、calculator 无关。
- **门控**: 生成 NEB YAML 时两端点目录必须带可解析 energy+forces，否则拒绝；
  有即视为 INPUT 合法（复用端点证据解析族 `read_abacus_out` 末帧 /
  `get_endpoint_results` 语义，不设白名单、不做强制覆盖）。
- **值语义**: 全部值用户可决定、原样带入（含 `cal_stress`/`init_*`/`out_*`/
  `onsite_radius`，其中 `onsite_radius` 无 atst 默认值，2026-08-12 群确认）；
  仅三个技术地板——`calculation` 归一化为 scf、`cal_force` 归一化为 1（均为
  NEB 内点单点力评估的结构性要求，2026-08-12 用户裁定）、KPT 拒绝 line-mode
  （接受 Gamma/MP 网格与 point 显式 K 点）。
- **KPT 三档优先级（2026-08-12 用户裁定）**: 与 Agent 当前
  `resolve_runtime_kpoint_spec` 逻辑一致——INPUT `gamma_only=1` → `[1,1,1]`；
  INPUT `kspacing` → 经既有 `convert_kspacing_to_kpts` 从 STRU cell 派生
  （显式 Bohr⁻¹→Å⁻¹ 换算，公式与 toolbox `kgrid_from_kspacing` 数学等价，
  不引入新科学逻辑）；否则读 KPT 文件（line 拒绝）。CLI 与 Agent 语义完全
  一致（W3 全量委托，删除 toolbox `_runtime_kpts` 适配器）。
- **pseudo_dir/orbital_dir（2026-08-12 用户裁定）**: 按 abacuslite/atst 兼容
  方式进入——解析后落在 `calculator.abacus.pseudo_dir`/`orbital_dir` 顶层字段
  （经 `AbacusProfile` 注入写 INPUT），**不进 `parameters`**；STRU 元素头 →
  `pseudopotentials`/`basissets`（同为顶层）。
- **版本归属**: 新增独立功能点，倾向 minor（2.3.0）；发布说明须声明向后兼容
  （纯增量，`cal_stress: 0` 下轨迹与现状一致）。
- **基线**: 开发前先将 main 拉平到 v2.2.2（当前 main 停在 2.2.0 finalize，
  toolbox 子模块 pin v2.2.2）。

## 文档义务（HANDOVER）

- 新增 CLI → 同步 `CLI_REFERENCE.md` / `USER_GUIDE_CN.md` /
  `CONFIG_REFERENCE.md`；若改 schema 重新生成 `YAML_INPUT_VARIABLES.md` 并运行
  `tests/unit/test_config.py`；更新 `FEATURE_STATUS_MATRIX.md`。
- 发布 → 新增 `docs/releases/RELEASE_NOTES_<版本>.md` + 更新文档账本。
- 完整架构/数据流/测试/上线/风险见权威规格。
