# ATST-Tools 重构任务清单

## 任务 1：重构 D2SWorkflow 接口

- [ ] 修改 `D2SWorkflow.__init__` 签名为 `(config, calc_name, calc_config)`
- [ ] 重构 `_get_calc` 方法以支持 calc_name（abacus/dp）
- [ ] 从 config 结构中提取所需参数（替代原有的 dft_params, mpi, omp, abacus_cmd, directory）
- [ ] 确保 D2S 内部调用的 AbacusDimer/AbacusSella 也能正确处理两种计算器

## 任务 2：集成 D2S 到 atst-run

- [ ] 在 main.py 中导入 D2SWorkflow
- [ ] 在 calc_type == 'd2s' 分支中实际调用 workflow.run()
- [ ] 遵循与 relax、vibration 相同的模式

## 任务 3：补充单元测试

### 3.1 测试 ConfigLoader
- [ ] 创建 tests/unit/test_config.py
- [ ] 测试 load() 方法（正常加载、文件不存在）
- [ ] 测试 validate() 方法（必填字段、有效 calc_type）

### 3.2 测试 CalculatorFactory
- [ ] 创建 tests/unit/test_factory.py
- [ ] 测试 abacus 计算器创建（使用 mock）
- [ ] 测试 dp 计算器创建（使用 mock）
- [ ] 测试无效计算器名称的错误处理

### 3.3 测试 Workflows
- [ ] 创建 tests/unit/test_workflows.py
- [ ] 测试 RelaxWorkflow（使用 mock calculator）
- [ ] 测试 VibrationWorkflow（使用 mock calculator）
- [ ] 测试 D2SWorkflow（使用 mock calculator）

## 任务 4：验证和完善示例配置
- [ ] 验证 examples/ 目录下所有 YAML 配置格式正确
- [ ] 特别确认 08_d2s_Cy-Pt/ 配置与重构后的 D2SWorkflow 兼容
- [ ] 验证 config_dp.yaml（DeepMD 配置）格式正确

## 任务 5：更新文档
- [ ] 更新 docs/FEATURE_STATUS_MATRIX.md，标记 D2S 为完成
- [ ] 检查并更新 docs/ 下其他文档以反映实际实现
- [ ] 确保 README.md 与实际代码一致

## 任务依赖关系

- 任务 2 依赖任务 1 完成
- 任务 3-5 可与任务 1-2 并行或在其之后进行
