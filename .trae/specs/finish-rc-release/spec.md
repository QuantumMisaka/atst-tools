# ATST-Tools 重构与 v2.0.0 实现规格

## 为什么（Why）

基于实际代码审查，ATST-Tools 虽然在 refactor/unify-structure 分支上进行了重构，但仍然存在以下关键问题需要解决：

1. **D2S 工作流与统一架构不兼容**：`D2SWorkflow` 的接口（`__init__` 参数）与 `RelaxWorkflow`、`VibrationWorkflow` 不一致，无法通过 `atst-run` 统一调用
2. **D2S 仅支持 ABACUS**：虽然 CalculatorFactory 已支持 ABACUS 和 DeepMD，但 D2SWorkflow 硬编码仅使用 abacus
3. **测试覆盖严重不足**：tests/ 目录只有占位文件，无实际单元测试
4. **文档与实现存在偏差**：部分文档描述与实际代码不完全一致

## 什么变更（What Changes）

### 核心修复

1. **重构 D2SWorkflow 接口**
   - 统一 `__init__` 签名为 `(config, calc_name, calc_config)`，与其他 Workflows 一致
   - 从统一配置结构中提取所需参数，而非独立参数列表
   - 确保支持 CalculatorFactory 的两种计算器（abacus 和 dp）

2. **集成 D2S 到 atst-run**
   - 在 main.py 中实现 d2s 分支的实际调用
   - 遵循与 neb、dimer、sella、relax、vibration 相同的模式

3. **补充单元测试**
   - 为 ConfigLoader 添加单元测试
   - 为 CalculatorFactory 添加单元测试（使用 mock）
   - 为核心 Workflows（至少 D2S、Relax、Vibration）添加单元测试（使用 mock）
   - 确保测试可在无外部依赖（ABACUS/DeepMD）的环境下运行

4. **完善文档**
   - 基于实际代码实现更新文档
   - 确保 docs/ 与代码一致

## 影响范围（Impact）

- **受影响代码**：
  - `src/atst_tools/workflows/d2s.py`：需要重构接口
  - `src/atst_tools/scripts/main.py`：需要添加 D2S 集成
  - `tests/` 目录：需要新增测试文件
  - `docs/` 目录：需要同步更新

- **兼容性**：
  - 保持现有配置结构不变
  - 保持其他 Workflows（Relax、Vibration、NEB 等）的接口不变

## 新增需求（Added Requirements）

### 需求：D2SWorkflow 接口统一

D2SWorkflow 必须支持与其他 Workflows 相同的初始化接口：

```python
class D2SWorkflow:
    def __init__(self, config, calc_name, calc_config):
        ...
```

必须支持：
- calc_name 为 'abacus' 或 'dp'（deepmd）
- 从统一的 config 结构中读取所需参数

### 需求：atst-run 支持 d2s 计算类型

当配置中 `calculation.type` 为 'd2s' 时，必须正确调用 D2SWorkflow。

### 需求：单元测试覆盖

必须为以下组件提供单元测试：
- ConfigLoader（load 和 validate 方法）
- CalculatorFactory（正确创建 abacus 和 dp 计算器）
- 核心 Workflows（使用 mock 验证调用流程）

## 修改需求（Modified Requirements）

### 需求：现有 Workflows 保持不变

RelaxWorkflow、VibrationWorkflow、NEB 相关类的现有接口和实现保持不变。

## 删除需求（Removed Requirements）

无。

---

## 审查基准：实际代码现状

### 已完成的部分

✅ **abacuslite 迁移**：已在 `src/atst_tools/external/abacuslite/` 集成，CalculatorFactory 使用它
✅ **CLI + YAML**：atst-run 入口、ConfigLoader、examples/ YAML 配置已实现
✅ **CalculatorFactory**：已支持 abacus 和 dp 两种计算器
✅ **Workflows**：Relax、Vibration、NEB、AutoNEB、Dimer、Sella 已在新架构下

### 待解决的问题

❌ **D2SWorkflow**：接口不统一，仅支持 abacus，未集成到 atst-run
❌ **测试**：tests/ 只有占位文件
❌ **文档**：部分文档与实现不完全一致
