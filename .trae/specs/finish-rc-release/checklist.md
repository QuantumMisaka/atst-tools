# ATST-Tools 重构检查清单

## 功能完整性

- [ ] D2SWorkflow.__init__ 签名已统一为 (config, calc_name, calc_config)
- [ ] D2SWorkflow._get_calc 支持 calc_name 参数（'abacus' 和 'dp'）
- [ ] D2SWorkflow 内部调用 AbacusDimer/AbacusSella 时正确传递 calc_name
- [ ] main.py 中已导入 D2SWorkflow
- [ ] main.py 中 calc_type == 'd2s' 分支已有实际实现
- [ ] D2SWorkflow 可通过 atst-run + YAML 配置正常调用

## 测试覆盖

- [ ] tests/unit/test_config.py 存在且包含 ConfigLoader 测试
- [ ] tests/unit/test_factory.py 存在且包含 CalculatorFactory 测试
- [ ] tests/unit/test_workflows.py 存在且包含 Workflows 测试
- [ ] 所有单元测试可在无外部依赖（ABACUS/DeepMD）的环境下通过

## 示例验证

- [ ] examples/01_neb_Li-Si/config.yaml 格式正确
- [ ] examples/02_neb_H2-Au/config.yaml 格式正确
- [ ] examples/03_autoneb_Cy-Pt/config.yaml 格式正确
- [ ] examples/04_dimer_CO-Pt/config.yaml 格式正确
- [ ] examples/05_sella_H2-Au/config.yaml 格式正确
- [ ] examples/06_relax_H2-Au/config.yaml 格式正确
- [ ] examples/07_vibration_H2-Au/config.yaml 格式正确
- [ ] examples/08_d2s_Cy-Pt/config.yaml 与重构后的 D2SWorkflow 兼容
- [ ] 各示例目录下的 config_dp.yaml 格式正确（如存在）

## 文档

- [ ] docs/FEATURE_STATUS_MATRIX.md 已更新，D2S 标记为完成
- [ ] docs/ 下其他文档与实际代码实现一致
- [ ] README.md 与实际代码一致

## 代码质量

- [ ] 代码变更遵循项目的 Python 风格
- [ ] 新增/修改的代码有适当的 docstring
- [ ] 没有引入新的 lint 错误（如运行 linter）
