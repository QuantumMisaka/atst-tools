# ATST-Tools YAML 配置治理报告

**日期**: 2026-05-12
**版本**: 2.0.0-rc
**状态**: 已引入 Pydantic schema 治理，并补齐自动变量文档导出

---

## 1. 结论

ATST-Tools 的 YAML 输入已经从“分散在 workflow 中读取默认值”的模式，升级为由 `src/atst_tools/utils/config_schema.py` 集中治理的模式。当前 YAML 入口仍保持：

```yaml
calculation:
  type: relax

calculator:
  name: abacus
```

但 `atst run` 在分发任务前会调用 `ConfigLoader.normalize()`，将原始 YAML 转换为带默认值、经过类型校验、结构规范化后的 dict。各 workflow 读取 YAML 控制项时应依赖规范化后的字段，避免在运行路径中再次维护一套默认值。

总体判断：

| 维度 | 当前状态 | 说明 |
| --- | --- | --- |
| 统一入口 | ✅ | `atst run CONFIG.yaml` 仍是唯一计算入口 |
| 变量默认值 | ✅ | 除结构文件、NEB chain/make 输入、DP model 等必须项外，schema 提供默认值 |
| 类型定义 | ✅ | Pydantic model + `Field(description=...)` 定义类型和含义 |
| 校验机制 | ✅ | 支持 required、枚举、正数范围、互斥字段、unknown field 拒绝 |
| 文档同步 | ✅ | `YAML_INPUT_VARIABLES.md` 由 schema 自动生成；`CONFIG_REFERENCE.md` 提供使用说明 |
| 扩展机制 | ✅ | 新 workflow/calculator 应新增 schema model，再接入 loader 和文档 |
| 仍保留的 pass-through | 有意保留 | `calculator.abacus.parameters` 透传 ABACUS INPUT 参数 |

---

## 2. 当前配置数据流

```text
YAML file
  -> ConfigLoader.load()
  -> ConfigLoader.normalize()
  -> ATSTConfig Pydantic schema
  -> normalized dict with defaults
  -> run_from_args() dispatch
  -> workflow / CalculatorFactory
```

`ConfigLoader.validate()` 仍保留旧接口，内部调用同一套 schema；测试和外部调用无需迁移。

Legacy root-level `abacus` 会在 schema 前处理阶段规范化为：

```yaml
calculator:
  name: abacus
  abacus: ...
```

下游代码应优先依赖规范化后的 `calculator` 结构。

---

## 3. 治理边界

### calculation

每个 `calculation.type` 对应一个 schema model：

- `neb`: `init_chain` 与 `make` 二选一；`make.n_images` 必须为正整数。
- `autoneb`: `init_chain` 必填；`n_simul: null` 表示运行时使用 `world.size`。
- `dimer` / `sella`: 单端方法参数有默认值，`dimer_separation/max_num_rot/order` 已进入 schema 并传入 workflow。
- `d2s`: endpoint optimization、rough DyNEB、Dimer/Sella、optional vibration 都有嵌套 schema。
- `vibration` / D2S vibration: thermochemistry 由统一 `ThermochemistryConfig` 管理。
- `irc`: direction、step、tolerance 等由 schema 限定类型和范围。

已清理的冗余入口：

- D2S 不再接受顶层 `endpoint_fmax` / `endpoint_max_steps`，统一使用 `calculation.endpoint_optimization.fmax/max_steps`。
- NEB nested make YAML 不再接受 `mag` 别名，统一使用 `calculation.make.magmom`；轻量 CLI 的 `atst neb make --mag` 保持为命令行参数。
- Vibration 不再接受顶层 `calculation.temperature`，统一使用 `calculation.thermochemistry.temperature`。

### calculator

- `calculator.name: abacus` 使用 `AbacusConfig`。ABACUS 控制变量由 schema 管理；`parameters` 字典保留为 ABACUS INPUT 透传区。
- `calculator.name: dp` / `deepmd` 使用 `DPConfig`。`model` 必填；`head`、`type_map`、`type_dict`、`omp`、`share_calculator` 由 schema 管理。
- `type_map` 与 `type_dict` 互斥；DPA/DPA3 multi-head 模型通过 `head` 传给 deepmd-kit。
- deepmd-kit backend 由模型文件自动识别，ATST-Tools 不暴露独立 backend 变量。

---

## 4. 默认值原则

默认值只在不会掩盖用户意图时提供：

- 物理/算法控制项给出保守默认值，如 `fmax`、`max_steps`、`climb`、`delta`、`nfree`。
- 文件输入项保持 required，如 `init_structure`、`init_chain`、`init_file/final_file`。
- DP `model` 保持 required，避免误运行错误模型。
- ABACUS `parameters` 保持透传，不对 ABACUS INPUT 做过度封装。
- `config_version` 默认 `"2.0.0-rc"`，用于后续兼容治理。

---

## 5. 开发规则

新增 YAML 变量时必须同步完成：

1. 在 `config_schema.py` 中定义字段类型、默认值和 `description`。
2. 如变量影响运行行为，确保 workflow 或 calculator 实际消费该字段。
3. 运行 `python -m atst_tools.utils.config_docs` 重新生成 `docs/user/YAML_INPUT_VARIABLES.md`。
4. 在 `docs/user/CONFIG_REFERENCE.md` 中更新用户说明。
5. 在对应 example 中给出最小可理解用法。
6. 在 `tests/unit/test_config.py` 或 workflow tests 中覆盖 normalize/validate 行为。

不要在 workflow 内直接新增未进入 schema 的 `calc_config.get("new_key", default)`，否则会重新造成变量事实来源分散。运行时动态默认值仍可保留，例如 `n_simul: null` 时使用 MPI `world.size`。

---

## 6. 后续可选增强

本轮已完成 P0/P1 中最关键的 schema 治理。仍可在后续版本继续增强：

- 导出 JSON Schema 给 IDE/YAML language server 使用。
- 提供 `atst run --print-normalized-config` 或写出 `used_config.yaml`，增强可复现性。
- 增加 YAML merge/override 和 CLI `--set`，支持批量参数扫描。
- 逐步移除下游 legacy `abacus` 分支，只保留 loader 层迁移。
