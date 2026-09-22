# ATST P2 收口证据切片（2026-09-22，SAI 4V100）

配套报告：[`../../ATST_P2_CLOSEOUT_2026-09-22.md`](../../ATST_P2_CLOSEOUT_2026-09-22.md)。
作业：`1444802`（P2 收口）、`1444708`（record 双通道）；代码固定点 `0fd205a`。

| 路径 | 内容 / 证明 |
| --- | --- |
| `run-p2-closeout.sbatch`、`run-record-channels.sbatch` | 两条现场入口脚本（含断言），可原样重跑 |
| `configs/`、`cases/` | 4 份用例 YAML（DP 只读共享 a/b、重启、ABACUS）与 4 份清单 |
| `atst-tools/slurm-1444802.out` | P2 收口作业完整输出：MPS 探测、模型目录摘要前后、共享计数、attempt 归属、重启断言 |
| `atst-tools/slurm-1444708.out` | record 双通道作业输出：两条记录的命令、断言与最终夹具事实 |
| `runs/share-second/batch_summary.json` | 共享 worker 批次汇总（2/2 成功、卡时） |
| `runs/share-second/work/ro-a|ro-b/runtime_evidence.json` | 逐用例 sidecar：`counters`（`dp.calculator_built/reused`）、`gauges`、sampler 样本与 `unavailable` 语义 |
| `runs/attempt-1-evidence.json`、`runs/attempt-2-evidence.json` | `ATST_ATTEMPT=1/2` 的 sidecar：`attempt` 字段与缓存目录一致（修复点） |
| `runs/attempt-1.traj`、`runs/attempt-2.traj` | 两次 attempt 的轨迹（保留以便复核归属） |
| `runs/restart/{first,second}/` | 同一 workdir 两次 batch 的汇总、`case_report.json` 与末帧轨迹（能量等价断言） |
| `record-dp/runs/bench_record.json`、`record-abacus/runs/bench_record.json` | 通道夹具：`dp_model`（sha256）与 `abacus_inputs`（`tree_sha256`），含 git 修订与空 warnings |

边界：MPS 归因只覆盖本次站点观测（见报告 §4.5）；站点 venv 的 `dist` 版本字符串仍为 2.2.6，
权威身份看记录里的 git 修订。
