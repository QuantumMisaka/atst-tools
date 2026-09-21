# SAI V100 P5 证据归档（2026-09-21）

本目录是 [SAI 现场验证报告](../../ATST_RUNTIME_SAI_V100_VALIDATION_2026-09-21.md) 的
可版本化证据切片。完整原始产物（轨迹、ABACUS 输出、每次 sweep 的整棵结果树）保留在
站点 `galileo-group/galileouser02:~/atst-p5-20260921/work/`，目录名与本归档一致。

| 目录 | 来源作业 | 内容 |
| --- | --- | --- |
| `dp-matrix2/runs/` | 1431119 | DP 矩阵（4 case × slots 1/2/3 × 3 repeats）：`bench_record.json`（操作者字段已填）、`sweep_summary.json`、证据 pass 的 4 份 `runtime_evidence.json` |
| `dp-matrix4/runs/` | 1431648 | slots=4 档：`bench_record.json`、`sweep_summary.json` |
| `srunpmix4cards/runs/` | 1432107 | 4 内部图 × 4 卡（`srun --mpi=pmix_v5 --gpus-per-task=1`）：`bench_record.json`、`sweep_summary.json`、rank0 `runtime_evidence.json`（`world_size=4`、`counters_mpi`） |
| `abacus3/runs/` | 1431200 | ABACUS 双示例（relax/NEB，host module 通道）：`bench_record.json`、`sweep_summary.json`、两例 `runtime_evidence.json` |
| `abacus5/runs/` | 1432820 | NEB 候选点补跑 ×2：`bench_record.json`、`sweep_summary.json` |
| `abacus4/runs/sweep/slots-1/repeat-1/` | 1431647 | 第一次重复的两例 `harness_case.json`（NEB 750.2 s、relax 171.7 s；该作业 repeat-2 NEB 因站点停滞取消） |

说明：`bench_record.json`（schema `atst-bench-record-v1`）的 `revision.head` 指向
运行时的 git 检出（`4d77fee`/`cfebd79`）；`operator.approved_by` 为维护者本人
（2026-09-21 chat 批复）。
