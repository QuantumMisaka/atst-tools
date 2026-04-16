# 迭代 1 开发计划：功能闭环与正式发布

**版本**: 1.0
**日期**: 2026-03-04
**周期**: 2026-03-05 至 2026-04-01 (4周)
**状态**: 计划中

## 1. 迭代目标
本迭代旨在解决 RC 阶段遗留的“最后一公里”问题，达成功能、文档、测试的全面闭环，发布 v2.0.0 正式版。

*   **目标 1 (功能)**: 完成 D2S 工作流接入，实现 100% 预定功能覆盖。
*   **目标 2 (质量)**: 核心工作流 (NEB/Dimer/Relax) 测试覆盖率 > 60%，消除 Placeholder 测试。
*   **目标 3 (文档)**: 文档与代码完全同步，建立自动化文档检查机制。
*   **目标 4 (发布)**: 发布 v2.0.0，归档所有 legacy 代码。

## 2. 需求拆解

### Story 1: D2S 工作流接入
*   **As a** 用户
*   **I want to** 使用 `type: d2s` 配置运行双端到单端搜索
*   **So that** 我可以自动化完成从粗糙路径到精确过渡态的搜索
*   **验收标准**:
    *   `atst-run config.yaml` (type=d2s) 能正常启动。
    *   `src/atst_tools/workflows/d2s.py` 逻辑被正确调用。
    *   提供完整的 `examples/08_d2s` 运行测试报告。

### Story 2: 测试体系补全
*   **As a** 开发者
*   **I want to** 拥有可运行的集成测试
*   **So that** 我在修改代码时不会破坏现有功能
*   **验收标准**:
    *   `tests/integration/test_relax.py`: 覆盖 RelaxWorkflow。
    *   `tests/integration/test_dimer.py`: 覆盖 DimerWorkflow。
    *   CI 流程中包含这些测试的自动运行。

### Story 3: 文档自动化检查
*   **As a** 维护者
*   **I want** CI 检查文档链接和代码一致性
*   **So that** 文档不会随代码演进而过时
*   **验收标准**:
    *   引入 `pre-commit` 钩子检查 Markdown 链接有效性。
    *   脚本检查 `examples/` 下的 `config.yaml` 是否符合 `CONFIG_REFERENCE.md` 规范。

## 3. 技术方案
*   **D2S 接入**: 修改 `src/atst_tools/scripts/main.py`，引入 `D2SWorkflow` 类，实例化并调用 `.run()`。需处理 `dft_params` 传递给 `CalculatorFactory` 的逻辑。
*   **测试框架**: 使用 `pytest` + `ase.calculators.emt` (作为 mock DFT) 进行轻量级集成测试，避免依赖 ABACUS/DP 二进制。
*   **文档检查**: 编写 Python 脚本 `scripts/check_docs.py`，遍历文档中的链接，并校验 YAML schema。

## 4. 任务排期 (甘特图摘要)

| 任务 | 负责人 | 估时 | Week 1 | Week 2 | Week 3 | Week 4 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **D2S 接入与调试** | TBD | 5d | █████ | | | |
| **CLI/Config 文档补全** | TBD | 3d | ███ | | | |
| **Relax/Dimer 测试编写** | TBD | 5d | | █████ | | |
| **文档自动化脚本** | TBD | 3d | | ███ | | |
| **全量回归测试** | TBD | 4d | | | ████ | |
| **Release Notes 准备** | TBD | 2d | | | ██ | |
| **v2.0.0 发布** | TBD | 1d | | | | █ |

## 5. 交付物清单
*   代码: `src/` 更新 (D2S 接入)。
*   测试: `tests/integration/` 新增测试用例。
*   文档: `docs/` 全量更新，含 `CONFIG_REFERENCE.md` 等。
*   工具: `scripts/check_docs.py`。
*   发布: PyPI 包 v2.0.0。