# 文档编写与维护规范

**版本**: 2026-05-28
**日期**: 2026-05-28
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档定义 ATST-Tools 文档的元数据、生命周期、报告分级、更新映射和检查命令。

## 1. 文档元数据

长期维护文档和 reports 文档必须在开头保留简洁元数据：

```markdown
# 标题

**版本**: <Version or YYYY-MM-DD>
**日期**: <YYYY-MM-DD>
**状态**: <草案/维护/已发布/归档/待删除复核>
**责任人**: <Owner>
```

生成文件可以使用生成器自带的头部，但必须说明来源，例如
`YAML_INPUT_VARIABLES.md` 说明它由 `config_schema.py` 生成。

## 2. 命名与格式

- 文件名使用明确语义，reports 推荐 `<TOPIC>_<TYPE>_<YYYY-MM-DD>.md`。
- 发布说明使用 `docs/releases/RELEASE_NOTES_<version>.md`。
- 示例代码使用 fenced code block，并标注 `bash`、`yaml` 或 `python`。
- 文件引用使用相对 Markdown 链接。
- 用户入口保持短、当前、可执行；长审查和历史证据放到 reports 或 archive。

## 3. 生命周期

| 类型 | 维护方式 |
| :--- | :--- |
| `guide` | 长期维护，功能变化时同步更新。 |
| `reference` | 长期维护，schema/CLI/backend 变化时同步更新。 |
| `status` | 作为当前状态入口，变化后必须刷新日期和结论。 |
| `validation` | 保留能证明当前功能、环境或科学结果的证据。 |
| `review` | 仅在结论仍影响当前设计或迁移边界时活跃保留。 |
| `plan` | 只保留仍要执行的计划；完成后吸收结论并移出活跃计划目录。 |
| `release` | 版本级记录，发布后长期保留。 |
| `archive` | 不指导当前工作，只保留历史审计价值。 |

文档迁移前先判断结论是否已被长期文档、最终报告、测试或 release notes 吸收。

## 4. Reports L1-L4 分级

| 级别 | 含义 | 处置 |
| :--- | :--- | :--- |
| L1 | 状态入口，如 feature matrix 和 documentation status report | 长期活跃，`docs/index.md` 可链接。 |
| L2 | 当前验证证据，如 DP、Issue #25 final、MPI parallel、CCQN validation | 活跃保留，完整清单在治理账本。 |
| L3 | 当前主题审查，如迁移审查、算法比较、覆盖率审查 | 主题仍活跃时保留。 |
| L4 | 历史或已被取代材料 | 移到 `docs/archive/` 或 `docs/archive/pending_delete/`。 |

新增或移动 reports 时，必须同步
[DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)。

## 5. 更新映射

| 变更类型 | 必查文档 |
| :--- | :--- |
| 新增或修改 YAML 字段 | `config_schema.py`、`YAML_INPUT_VARIABLES.md`、`CONFIG_REFERENCE.md`、示例、`test_config.py` |
| 新增 workflow | README 支持列表、`USER_GUIDE_CN.md`、`CLI_REFERENCE.md`、`CONFIG_REFERENCE.md`、examples、feature matrix、tests |
| 新增 CLI 命令 | `CLI_REFERENCE.md`、`docs/skills/atst-cli/SKILL.md`、README 命令列表、CLI tests |
| 新增 calculator backend | README backend section、`CONFIG_REFERENCE.md`、用户指南、feature/status reports、factory tests |
| 新增 example | `examples/README.md`、`examples/reference_results.json` 或明确无 reference 说明、example tests |
| 新增 validation report | `DOCUMENTATION_STATUS_REPORT.md`，必要时更新 `docs/index.md`，并判断旧报告是否降级 |
| 修复重要 bug | 最终修复报告或更新现有 active report，必要时更新 feature matrix 和回归测试 |
| 准备 release | release notes、feature matrix、documentation status、pending-delete review |

## 6. 归档与待删除流程

- `docs/archive/`：用于有历史审计价值但不指导当前工作的文档。
- `docs/archive/pending_delete/`：用于结论已被取代、继续活跃保留会误导读者、且仍需维护者最终确认的文件。
- 待删除文件不得从 README、`docs/index.md`、用户指南或开发者入口回链。
- 最终删除前确认：无活跃链接、无唯一验证证据、结论已被吸收、治理账本记录过处置。

## 7. 检查命令

文档-only 变更至少运行：

```bash
git diff --check -- README.md docs examples/README.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md
```

还应对 README 和非 archive 的 `docs/**/*.md` 执行本地相对链接检查。若修改 HTML
报告，用 Python 标准库 `HTMLParser` 做基础解析。若修改 YAML schema，重新生成参数表并运行：

```bash
conda run -n atst-dev python -m atst_tools.utils.config_docs --output docs/user/YAML_INPUT_VARIABLES.md
conda run -n atst-dev pytest tests/unit/test_config.py -q
```
