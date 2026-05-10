# ATST-Tools 需求评审与增强规格说明（更新版）

## 落地计划审查

根据开发团队提供的 Terminal#922-998 落地计划，我进行详细审查：

**✅ 与原始需求的一致性（全覆盖）：**
- 需求1: 开发文档和CLI help信息增强 ✅ 覆盖
- 需求2: IRC 计算支持 ✅ 覆盖
- 需求3: atst relax post ✅ 覆盖
- 需求4: vibration 续跑机制完善 ✅ 覆盖
- 需求5: --output-structure vs --output-traj ✅ 覆盖
- 需求6: abacuslite 使用提示 ✅ 覆盖
- 需求7: NEB 续算审查 ✅ 覆盖
- 需求8: 文档治理完善 ✅ 覆盖

**✅ 新增的优秀设计：**
- Workflow CLI Decisions 表格，明确每个功能是否需要轻量命令
- 共享 restart/cache helper，统一处理续算逻辑
- 详细的测试计划
- 清晰的 assumptions
- gitignore 考虑和工作树检查
- 隐藏兼容别名策略

---

## 现状概述（更新）

首先，我们对 [CLI_DEV.md](docs/developer/plans/CLI_DEV.md) 计划的落地情况进行评估：

**✅ 已完成的功能：**
1. 统一的 git-style CLI（`atst run`、`atst neb`、`atst dimer`、`atst vibration`）
2. `atst run --restart` 机制（临时覆盖 calculation.restart）
3. NEB 续算机制（从 trajectory 最后一个 band 继续）
4. AutoNEB、Dimer、Sella 基本可用
5. Vibration post 命令已实现

**❌ 未完成或有问题的部分：**
1. Vibration 续跑机制不完善：
   - 当前 `_prepare_cache` 只清理 cache，但 0 字节文件处理不完整
   - 缺少对坏文件的识别和清理
2. 缺少 IRC 计算支持
3. 缺少 relax post 命令
4. CLI 帮助信息可更详细
5. `--output-structure` 参数可能过长

---

## What Changes（更新版）

根据开发团队的落地计划，我们进行详细规划：

### 优先级 1 - 高（核心健壮性）：
1. **共享 restart/cache helper**：
   - 统一处理“从 traj 取最后一帧/最后完整 NEB band”
   - 检测坏 cache JSON
   - 输出清晰错误

2. **Vibration 续跑机制完善**（需求 4）：
   - 识别并清理 0 字节或无效 JSON 文件
   - restart=false 时清理整个 vibration cache 目录后重算
   - restart=true 时保留有效 cache*.json，删除坏文件
   - atst vibration post 在 cache 缺失或损坏时给出可操作错误

3. **NEB/D2S 续算完善**（需求 7）：
   - NEB restart 从目标 trajectory 读取最后完整 band，并校验 image 数
   - D2S 的各阶段使用同一 helper 判断是否可续算
   - AutoNEB 文档中标明 restart 边界
   - Dimer/Sella/Relax restart 从对应 trajectory 最后一帧续算，不静默回退

### 优先级 2 - 中（功能增强）：
4. **Relax post 命令**（需求 3）：
   - 新增 `atst relax post TRAJ --ind -1 --output-format stru|cif|poscar --output PATH`
   - 输出能量、最大原子力，并写出选中结构

5. **IRC 计算支持**（需求 2）：
   - 新增 `calculation.type: irc`，基于 sella.IRC
   - YAML 必需字段为 init_structure
   - 主入口仍是 `atst run config.yaml`，不新增直接运行 IRC 的轻量命令

6. **参数简化**（需求 5）：
   - 将 dimer 前处理参数公开为 `--output-traj`
   - `--output-structure` 仅作为隐藏兼容别名保留一个重构周期

### 优先级 3 - 低（易用性/文档）：
7. **CLI help 信息增强**（需求 1）：
   - 增强 `atst --help` 与各子命令 help
   - 明确哪些命令是 YAML workflow，哪些是轻量前/后处理

8. **abacuslite 使用提示**（需求 6）：
   - 在 abacus calculator factory 中记录一次 abacuslite backend 来源
   - 优先外部安装，失败后 vendored fallback
   - 避免每个 image 重复刷日志

9. **文档治理完善**（需求 8）：
   - 更新 README.md、docs/index.md、CLI_REFERENCE.md、CONFIG_REFERENCE.md
   - 新增或更新正式报告到 docs/reports/
   - 保持 .trae 仅为临时/spec 工作区，不作为正式文档入口

---

## Impact（更新）

- 影响的代码：
  - `src/atst_tools/workflows/vibration.py`
  - `src/atst_tools/scripts/cli.py`
  - `src/atst_tools/scripts/main.py`
  - `src/atst_tools/calculators/factory.py`
  - 新增：`src/atst_tools/utils/restart_helpers.py`（共享 restart/cache helper）
  - 新增：`src/atst_tools/workflows/irc.py`（IRC workflow）
  - 文档：更新多个 md 文件
  - tests：新增多个单元测试

---

## Workflow CLI Decisions（关键决策）

| Workflow | 轻量 CLI | 原因 |
| --- | --- | --- |
| neb | ✅ make/post | 典型前处理和后处理，不需要 calculator |
| dimer | ✅ make-from-neb | 从 NEB 生成 TS guess，实际优化走 YAML |
| sella | ❌ 不新增 | 需要 calculator、约束、收敛参数，走 YAML 更清晰 |
| d2s | ❌ 不新增 | 组合 workflow，入口保持 atst run |
| relax | ✅ post | 从 trajectory 提取最终结构/能量/力是无重计算后处理 |
| vibration | ✅ post | 从 ASE cache 重建 summary/result JSON 是无重计算后处理 |
| irc | ❌ 不新增 | 通过 YAML workflow 运行，后续如需要可再加 trajectory 分析命令 |

---

## ADDED Requirements（更新版）

### Requirement 1: 共享 restart/cache helper

#### 功能规格：
1. 在 `utils/restart_helpers.py` 中新增：
   - `get_last_frame(traj_file)`: 从 trajectory 取最后一帧
   - `get_last_neb_band(traj_file, expected_n_images)`: 取最后完整 NEB band
   - `check_cache_files(vib_dir)`: 检测坏 cache JSON（0 字节或无效 JSON）
   - `clean_cache_files(vib_dir, keep_good=True)`: 清理坏文件，保留好文件

### Requirement 2: 完善 Vibration 续跑机制

#### 场景描述：
vibration 计算中断时会产生 0 字节的 cache.json 文件，导致直接续跑失败。

#### 功能规格：
1. 在 `VibrationWorkflow._prepare_cache` 中：
   - 使用共享 helper 检查所有 `cache*.json` 文件
   - 若 `restart=True`：保留有效 cache，删除坏文件
   - 若 `restart=False`：清空整个 vib 目录
2. 在 `_vibration_post_command` 中：
   - 添加详细的错误提示，说明 cache 目录可能有问题
   - 尝试解析缓存文件，失败时给出明确提示

---

### Requirement 3: 完善 NEB/D2S/Dimer/Sella/Relax 续算

#### 功能规格：
1. NEB restart：从目标 trajectory 读取最后完整 band，并校验 image 数；不完整时抛出明确异常
2. D2S：各阶段使用同一 helper 判断是否可续算
3. Dimer/Sella/Relax：restart 从对应 trajectory 最后一帧续算；如果 trajectory 不存在或不可读，给出明确错误，不静默回退

---

### Requirement 4: 添加 Relax post 命令

#### 功能规格：
1. 在 `cli.py` 中添加 `atst relax post` 子命令
2. 参数：
   - `traj_file`: 轨迹文件（必填）
   - `--ind`: 帧索引（默认 -1，最后一帧）
   - `--output-format`: 输出格式（默认 stru，支持 cif、poscar 等）
   - `--output`: 输出文件路径（可选）
3. 功能：
   - 读取指定帧
   - 输出能量和最大原子受力到 stdout
   - 保存结构到文件

---

### Requirement 5: IRC 计算支持

#### 功能规格：
1. 在 `workflows/irc.py` 中新增 IRC workflow
2. 在 `main.py` 中添加 dispatch
3. 通过 `calculation.type: irc` 配置
4. 基于 sella.IRC 实现
5. YAML 常用参数包括 trajectory、max_steps、fmax、dx、eta、gamma、irctol、keep_going
6. restart 通过 IRC trajectory 最后一帧续算

---

### Requirement 6: 参数简化和兼容

#### 功能规格：
1. 将 dimer make-from-neb 的 `--output-structure` 重命名为 `--output-traj`
2. 保留 `--output-structure` 作为隐藏兼容别名一个重构周期
3. 更新 CLI_REFERENCE.md 中的文档

---

### Requirement 7: CLI help 和文档增强

#### 功能规格：
1. 增强每个子命令的 `help` 和 `description`
2. 更新 CLI_REFERENCE.md、CONFIG_REFERENCE.md、README.md、docs/index.md
3. 在 abacuslite factory 中添加来源提示信息（内置 vs 系统），仅记录一次
4. 新增正式报告到 docs/reports/，记录 SPEC 完成情况

---

## Test Plan（详细）

### 单元测试：
- CLI：旧 console scripts 不存在；atst run dispatch；--restart 覆盖 YAML；relax post；dimer --output-traj 与隐藏别名；help/list/template 包含 IRC
- Config：irc 类型校验、必需字段、模板输出
- Restart helper：最后一帧、最后完整 NEB band、不完整 trajectory 报错、坏 JSON cache 检测
- Vibration：restart 保留好 cache、删除坏 cache；非 restart 清理 cache；post 遇到坏 cache 报错
- Factory：abacuslite source hint 只记录一次

### 集成/烟测：
- conda run -n atst-dev pytest tests -q
- conda run -n atst-dev python -m compileall -q src/atst_tools tests
- conda run -n atst-dev atst run --show-template irc --calculator abacus
- conda run -n atst-dev atst run --dry-run examples/06_relax_H2-Au/config.yaml

### 工作树检查：
- git status --short 不出现新 Slurm/ABACUS/vibration/trajectory 输出
- git check-ignore -v 验证运行输出被 ignore，examples/tests 输入未被 ignore

---

## Assumptions

- 当前分支仍是重构分支，允许破除旧 CLI 稳定性；但对已新增参数保留隐藏别名，降低本轮测试和用户草稿配置的破坏面
- IRC 采用本环境已安装的 sella.IRC，若用户环境未安装 sella，则在运行时给出安装提示
- 本轮不做真实 ABACUS/Slurm 实算，只做轻量单测、compile、CLI dry-run；真实 GPU 实算作为发布前单独验收
- 不回滚或清理用户已有未提交改动；只在相关文件上增量修改，并保留已跟踪科学输入文件

---

## MODIFIED Requirements

无

## REMOVED Requirements

无
