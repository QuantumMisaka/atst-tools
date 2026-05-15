## ABACUS & DP Calculator 支持审查报告

---

### 1. ABACUS Calculator 支持情况（✅ 完整可用）

| 项 | 状态 | 说明 |
| :--- | :--- | :--- |
| 后端实现 | ✅ | 使用官方 `abacuslite`（优先外部安装，否则使用 vendored 快照） |
| 配置结构 | ✅ | 支持 `calculator.abacus`（推荐）和根级 `abacus`（兼容） |
| 参数 | ✅ | `command`、`mpi`、`omp`、`directory`、`kpts`、`pseudopotentials`、`basissets`、`pseudo_dir`、`orbital_dir`、`parameters` 都支持 |
| 兼容映射 | ✅ | 自动将 `pp`→`pseudopotentials`、`basis`→`basissets`、`basis_dir`→`orbital_dir` 转换 |
| MPI 命令 | ✅ | 自动构建：`mpirun -np <mpi> <command>` |
| OMP 环境 | ✅ | 设置 `OMP_NUM_THREADS` |
| 日志 | ✅ | 后端来源（external/vendored）只打印一次 |
| SAI 验证 | ✅ | `refactor/unify-structure` 分支所有 ABACUS 示例在 SAI 上通过（01~08、10、11） |
| 单元测试 | ✅ | `tests/unit/test_factory.py` 包含完整覆盖 |

**Backend 解析流程**（`abacuslite_backend.py`）：
```
1. try: from abacuslite import Abacus, AbacusProfile  → "external"
2. except: from atst_tools.external.ASE_interface.abacuslite import ...  → "vendored"
```

**示例配置**（`examples/01_neb_Li-Si/config.yaml`）：
```yaml
calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_neb
    kpts: [2, 2, 2]
    parameters:
        calculation: scf
        ecutwfc: 100
        basis_type: lcao
        ks_solver: cusolver  # SAI GPU
        ...
```

---

### 2. DP (Deep Potential) Calculator 支持情况（✅ CLI/Workflow 架构与实算验证完成）

| 项 | 状态 | 说明 |
| :--- | :--- | :--- |
| Factory 实现 | ✅ | `DeepPotentialFactory` 已拆分到 `calculators/dp.py`，懒加载 `deepmd.calculator.DP` |
| 配置结构 | ✅ | 支持 `model`、`head`、`type_map`/`type_dict`、`omp`、`share_calculator` |
| Backend 识别 | ✅ | deepmd-kit `DeepPot` 根据模型文件自动识别 backend；ATST-Tools 不额外暴露 backend 选择 |
| DPA multi-head | ✅ | `calculator.dp.head` 传递给 deepmd-kit，用于 DPA3 等多 head 模型 |
| 共享实例 | ✅ | cache key 包含 model、head、type 映射和构造参数；NEB/DyNEB/AutoNEB 串行时启用 ASE shared calculator |
| 单元测试 | ✅ | 覆盖 lazy import、head/type 映射、OMP、cache、NEB/DyNEB/AutoNEB 共享策略 |
| 文档标注 | ✅ | CONFIG_REFERENCE.md 和 ML_CALCULATOR_PLAN.md 已更新 |
| DP 特定参数 | ✅ | `omp`、`share_calculator` 已实现 |
| SAI 实算验证 | ✅ | 2.0.0 使用 DPA-3.1-3M.pt / `Omat24` head 覆盖现有 `atst run` workflow 示例 |

**当前实现**：
```python
DP(model=model_file, head=head, type_dict=type_dict)
```

**实现边界**：
- ✅ `deepmd.calculator.DP` 是唯一 DP ASE 入口。
- ✅ `.pb`、`.pt` 等模型 backend 由 deepmd-kit 根据模型文件自动检测。
- ✅ DPA3 等 multi-head 模型通过 `head` 选择分支；不配置时保留 deepmd-kit 原生报错。
- ❌ 旧 `deepmd_pt` / `*_dpa2.py` 脚本不迁移。

**文档状态**：
- `CONFIG_REFERENCE.md` §3.2：记录当前 DP 参数和 deepmd-kit backend 自动识别边界。
- `ML_CALCULATOR_PLAN.md`：实现项已勾选，DP 工作流回归结论已补齐。
- `DP_VALIDATION_2.0.0.md`：记录 2.0.0 DP 实算验证、AutoNEB 修复和 IRC/Sella 边界。

---

### 3. CalculatorFactory 统一入口（✅ 完整可用）

```python
class CalculatorFactory:
    @staticmethod
    def get_calculator(name: str, config: Dict[str, Any], **kwargs) -> Calculator:
        name = name.lower()
        if name == "abacus":
            return AbacusFactory.get_calculator(config, **kwargs)
        if name in {"dp", "deepmd"}:
            return DeepPotentialFactory.get_calculator(config, **kwargs)
        raise ValueError(...)
```

支持名称：
- `"abacus"` → AbacusFactory
- `"dp"` 或 `"deepmd"` → DeepPotentialFactory

---

### 4. 测试覆盖情况（✅ DP 单元测试通过，ABACUS 完整覆盖）

- ✅ `tests/unit/test_factory.py`：abacus & dp 工厂测试
- ✅ `tests/unit/test_config.py`：dp 配置解析验证
- ✅ `tests/unit/test_examples.py`：所有 `config_dp.yaml` 解析验证
- ✅ `pytest tests -q` 在 `atst-dev` 环境通过

---

### 5. 发现的问题/待办

| 优先级 | 问题 | 说明 |
| :--- | :--- | :--- |
| 低 | 长时生产级 DP 回归 | 2.0.0 已完成示例级 SAI GPU 验证；更大体系和更长步数可作为后续 benchmark 扩展 |

---

### 6. 总结

| Calculator | 状态 |
| :--- | :--- |
| ABACUS | ✅ 完整可用，SAI 验证通过，文档完整 |
| DP | ✅ CLI/Workflow 架构支持完成，DPA-3.1-3M.pt / `Omat24` 示例级 SAI 工作流回归通过 |
