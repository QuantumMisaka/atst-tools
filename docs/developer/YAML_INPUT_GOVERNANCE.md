# YAML 输入治理规范

**版本**: 2.0.0-rc
**日期**: 2026-05-12
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档定义 `atst run` YAML 输入变量的开发治理规则。目标是保证所有用户可编辑变量都有统一的类型、默认值、含义说明、文档导出和测试覆盖。

## 1. 治理原则

- **Schema first**: `src/atst_tools/utils/config_schema.py` 是 YAML 变量的唯一事实来源。
- **Canonical path only**: 每个用户变量只能有一个公开 YAML path，不新增 alias、重复字段或兼容旁路。
- **Default in schema**: 除必须由用户提供且无安全默认值的变量外，默认值必须由 Pydantic schema 管理。
- **Runtime consumes normalized config**: `atst run` 必须先调用 `ConfigLoader.normalize()`，workflow/calculator 读取规范化后的字段。
- **Document from schema**: 非 calculator YAML 变量表由 schema 自动生成，不手工维护。

ABACUS INPUT 变量是唯一例外：它们统一放在 `calculator.abacus.parameters` 中透传给 ABACUS，不逐项纳入 ATST-Tools schema。

## 2. 关键入口

- Schema: `src/atst_tools/utils/config_schema.py`
- Loader: `src/atst_tools/utils/config.py`
- Markdown exporter: `src/atst_tools/utils/config_docs.py`
- Generated user variable table: `docs/user/YAML_INPUT_VARIABLES.md`
- Manual user reference: `docs/user/CONFIG_REFERENCE.md`
- Governance tests: `tests/unit/test_config.py`, `tests/unit/test_config_governance.py`

## 3. 新增或修改 YAML 变量流程

1. 在 `config_schema.py` 中新增字段，明确类型、默认值和 `Field(description=...)`。
2. 对枚举、正数范围、互斥字段和结构约束添加 Pydantic validator。
3. 确保变量影响计算行为时，workflow/calculator 实际读取规范化后的字段。
4. 如果有直接构造 workflow 的内部测试路径，使用 `apply_calculation_defaults()` 复用 schema 默认值。
5. 重新生成变量表：
   ```bash
   python -m atst_tools.utils.config_docs --output docs/user/YAML_INPUT_VARIABLES.md
   ```
6. 更新 `CONFIG_REFERENCE.md`、必要的用户向导和对应 example YAML。
7. 更新单元测试，至少覆盖 validate/normalize、文档同步和冗余变量拒绝。

## 4. 禁止事项

- 不在 workflow 内新增 `calc_config.get("new_key", 123)` 形式的用户变量默认值。
- 不新增多个 YAML 名称指向同一语义变量。
- 不把 calculator backend 私有参数混入 `calculation` 层。
- 不手工编辑 `YAML_INPUT_VARIABLES.md` 后跳过 schema/exporter 更新。

运行时动态默认值可以保留，例如 `n_simul: null` 时由 MPI `world.size` 决定。

## 5. 外部开发者添加新 `atst run` 功能点

新增计算工作流时，最小接入路径是：

1. 在 `src/atst_tools/workflows/` 或 `src/atst_tools/mep/` 添加实现。
2. 在 `config_schema.py` 添加新的 `Calculation` schema，并加入 `VALID_CALCULATION_TYPES` 和 discriminated union。
3. 在 `src/atst_tools/scripts/main.py` 添加 `atst run` dispatch 和 `--show-template` 模板。
4. 添加 example YAML 和用户文档。
5. 添加 workflow/config/examples 单元测试。
6. 重新生成 `docs/user/YAML_INPUT_VARIABLES.md`。

新增 calculator backend 时，应优先接入 `src/atst_tools/calculators/factory.py`，并把 backend 自身变量放在 `calculator.<backend>` 层。
