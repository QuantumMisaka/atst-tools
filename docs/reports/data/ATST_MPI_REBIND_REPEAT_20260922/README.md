# MPI 重绑定现场重复实测（2026-09-22，SAI 4V100）

作业 `1451595`/`1451596`/`1451597`（节点 `4v100n13`/`n23`/`n26`），代码固定点 `bc420aa`（main，随后发布为 v2.2.8）。
用例：`dp_neb_ft2dp_chain10_mpi8`，`mpiexec --oversubscribe -n 8` + `runtime.binding: round_robin`，1 卡。

| 结果 | 值 |
| --- | --- |
| 用例 | 3/3 `succeeded`，`ranks=8`，wall 14.5 / 15.7 / 19.0 s |
| 绑定 | sidecar `devices.bound=true`、`effective=['0']` |
| MPI 事实 | sidecar `counters_mpi.world_size=8`（rank 求和 Σ`dp.force_calls=26`）；worker 级 `mpi` 字段为 `null`（证据形状差异，见下） |
| 旧挂起现象 | 不可复现（修复 `0668d61` 之后连续 3 次 + 历史 1434302 单次均正常） |

环境注意：作业必须使用站点上与既有成功运行一致的模块链
`module load deepmd-kit/3.2.0 abacus/LTSv3.10.1-sm70-auto`（→ Open MPI v5.0.8）；
只装 deepmd（Open MPI 5.0.10/nvhpc26.3）时 `mpiexec` 会以 `prterun … exit 2` 在 ~3 s 失败（本轮已用 6 次作业定位）。

证据形状差异：本次 worker 侧 sidecar 的 `mpi`/`local_rank` 为 null，而 `counters_mpi.world_size=8` 存在；
归档 P5 运行（1436926/1436941）记录的是 `mpi.world_size=8`。两者都证明 8 rank 执行，但字段落点不同，
若后续需要机器可读的 world 事实，应在 worker 侧补齐（记为小项）。
