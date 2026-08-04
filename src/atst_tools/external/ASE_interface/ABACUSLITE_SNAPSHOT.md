# abacuslite vendored 快照基线

- 快照引入：2026-05-10（atst-tools `881a926`）
- drift-check CI 引入：2026-07-06（`7a04854`）钉扎 `762919f6`（= #7588 PR head）
- 当前基线：上游 `70f7ed69b5677c447afdc78e05240e93da660e66`（2026-07-22 commit；2026-07-23 `b8556c7` 写入 CI）
- 同步状态（2026-08-04 核对）：对上游 develop tip 零上游侧欠账；仅 fork 侧语义补丁（efermi 容错 + core.py 帧选择，见 PATCHES.md）
- 差异摘要：以 `scripts/check_abacuslite_snapshot.py --upstream <基线树> --vendored ...` 输出为准

## 同步流程

阶段拉取（发布 patch / 支持新 ABACUS / 上游新加固）后：更新本文件基线 SHA + 差异摘要；CI `ABACUS_DEVELOP_REF` 从本文件解析（单一事实源）。
