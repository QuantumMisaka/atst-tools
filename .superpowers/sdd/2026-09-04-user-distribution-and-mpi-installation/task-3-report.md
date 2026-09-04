# Task 3 交付报告

**Task:** Reclassify maintenance-only SAI guidance, remove stale facts, and close governance  
**Commit:** `017b8cc` (`docs: complete distribution and MPI guidance`)

## 改动

- `AGENTS.md` 将 SAI 定义为维护验证环境，说明 image-level NEB/AutoNEB 的 MPI 验证边界，并移除用户入口中的 SAI 注意事项措辞。
- `docs/skills/atst-cli/SKILL.md` 删除过时的 main/v1.5.x legacy 分支政策。
- `docs/developer/HANDOVER.md` 增加 base 安装保持 mpi4py-free、`parallel` 用户先验证站点 MPI import/launcher 的依赖维护要求。
- `docs/releases/RELEASE_NOTES_2.2.3.md` 将 Compatibility 中错误的 `2.3.0` 修正为 `2.2.3`。
- `docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html` 状态更新为“已实施”。
- `docs/reports/DOCUMENTATION_STATUS_REPORT.md` 登记并标记本 SPEC/plan 已实施。
- `docs/superpowers/plans/2026-09-04-user-distribution-and-mpi-installation.md` 将 Task 1–3 的 18 个执行步骤标记完成。
- `tests/unit/test_docs_governance.py` 增加 stale-fact 与维护边界回归测试。

## 根因与集成决定

Task 3 的 RED 测试确认三处事实漂移：AGENTS 使用“开发测试环境”定位 SAI，CLI skill 保留 main/v1.5.x legacy 政策，2.2.3 release notes 却写入 2.3.0。修复沿用既有文档分层，不扩大用户文档的 SAI/site-specific 内容；MPI 依赖边界继续由 base 与 `parallel` extra 的既有契约负责。

## RED → GREEN 证据

- RED：
  `conda run -n atst-dev python -m pytest tests/unit/test_docs_governance.py::test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy -q`
  失败，首个断言确认 AGENTS 尚无“维护验证环境”。
- GREEN：
  `conda run -n atst-dev python -m pytest tests/unit/test_docs_governance.py::test_maintenance_guidance_labels_sai_as_validation_only_and_has_no_legacy_branch_policy tests/unit/test_docs_governance.py::test_user_entrypoints_exclude_maintainer_and_site_operations -q`
  通过（2 passed）。

## 完整验证

状态编辑前已执行并通过：

- `git diff --check -- README.md docs examples/README.md AGENTS.md`
- `rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md`（无匹配，退出码 1）
- `conda run -n atst-dev python scripts/check_docs_governance.py`（输出 `documentation governance checks passed`）
- `conda run -n atst-dev python -m pytest tests -q`（全套通过；仅既有 opt-in MPI/toolbox skips）

SPEC/ledger/plan 状态编辑后再次执行并通过：

- `conda run -n atst-dev python scripts/check_docs_governance.py`
- `git diff --check -- README.md docs examples/README.md AGENTS.md`
- 同一冲突标记扫描无匹配。

## 未执行项与剩余不确定性

未执行 GitHub、Gitee、PyPI 的外部 README 渲染人工检查。该提交尚未 push/publish，且任务明确禁止推送、发布或触发镜像同步；因此外部页面无法可靠反映本地提交。未执行 scheduler/SAI runtime 验证，也未触碰外部同步状态。
