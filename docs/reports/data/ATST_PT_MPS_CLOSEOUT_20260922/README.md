# ATST PT 线程键与 MPS 归因站点复验（2026-09-22，SAI 4V100）

配套报告：[`../../ATST_P2_CLOSEOUT_2026-09-22.md`](../../ATST_P2_CLOSEOUT_2026-09-22.md) §9。代码固定点 `af82973`。

| 路径 | 内容 / 证明 |
| --- | --- |
| `run-pt-mps-verify.sbatch` | 现场入口脚本（1 GPU、显式 `--threads 4 --telemetry`，含语义契约断言） |
| `atst-tools-pt/slurm-1445792.out` | 通过的一轮（节点 `4v100n26`，exit 0）：两个 `DP_*` 线程键=4、`threads_source=explicit`、`mps.detected=false` 且三路探测均完成、`self_reported.max_memory_allocated_mib=620.139` |
| `atst-tools-pt/slurm-1445744.out` | 首轮（节点 `4v100n18`，因断言过严在 MPS 处中止；归档脚本对应通过轮，复现该失败需回退断言）：同一线程键通过；断言要求 `detected=true` 而现场为 false → 据此把断言改为语义契约（true 需正证据 / false 需完成的进程表探测 / null 需 reason） |
| `pt-mps-verify/runtime_evidence.json` | 通过轮次的完整 sidecar：`environment.threads`（含两个 `DP_*`）、`telemetry.sampler.mps`、`self_reported` |

边界：MPS 守护进程在 2026-09-22 下午两次作业（4v100n18 / 4v100n26）中均**不可见**，故「detected=true 且 reason 点名 MPS」的正向路径只有单测（替身）覆盖；当日上午 P2 作业（1444802，4v100n18）曾看到守护进程，说明该现象随节点/时间变化，探针三态语义正确。
