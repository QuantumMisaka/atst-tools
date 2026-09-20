# ATST Runtime 本地真实 GPU 验证 2026-09-21

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 维护（P1/P2 本地真实设备证据；SAI V100 基准仍属 P5）
**责任人**: ATST-Tools maintainers

## 1. 目的

在真实 GPU 上验证隔离运行路径（`atst run --devices/--threads/--telemetry`）
的设备解析、环境绑定、DP 推理与运行证据链路，作为
[GPU 节点调优计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md)
P1/P2 验收的本地真实设备证据。本报告不代表 SAI V100、ABACUS、MPI 或平台
验收。

## 2. 环境

| 项 | 值 |
| --- | --- |
| 主机 GPU | 1 × NVIDIA GeForce RTX 2070 SUPER（8 GiB，驱动 572.70，UUID `GPU-26530a40-880d-9be7-85c5-0e07cd25af54`） |
| Python | 3.10.19（`atst-dev`），源码经 `PYTHONPATH=src` 指向基线工作树 |
| 关键依赖 | ase 3.28.0、numpy 2.2.6、pydantic 2.12.5、deepmd-kit 3.1.2、mpi4py 4.1.2 |
| 模型 | `examples/dp_model_manifest.json` 的 `DPA-3.1-3M`（head `Omat24`，sha256 `86dd3a80…`，`scripts/download_dp_model.py` 校验下载） |
| 输入 | `examples/06_relax_H2-Au/inputs/init.stru` 副本（H2-Au 小体系） |

## 3. 命令

```bash
cd ~/scratch/atst-gpu-local-20260921
CUDA_VISIBLE_DEVICES=0 PYTHONPATH=<repo>/src \
  python -m atst_tools.scripts.cli run config.yaml \
  --devices 0 --telemetry --threads 4
```

配置：`calculation.type=relax`、`fmax 0.2`、`max_steps 20`、DP 计算器
（`head: Omat24`、`omp: 4`）；`--devices 0` 为“可见集合内逻辑序号”。

## 4. 结果

工作流成功（`atst-api-result-v1` `status=success`，relax 收敛，末态能量
−203.7575 eV，wall ≈ 31.5 s），并产出完整证据链：

```text
runtime_evidence.json  status=complete  workflow=relax
devices: bound=true  caller_bound=true  requested=["0"]（--devices）
         inherited=["0"]  effective=["0"]  allocation_identity=unverified
threads: OMP/OPENBLAS/MKL/NUMEXPR=4（source=explicit），cpu_affinity_count=32
counters: dp.calculator_built=1  dp.force_calls=3  counters_scope=process
sampler:  observed，26 samples / 30.5 s
          gpu: uuid=GPU-26530a40…  utilization=6%  memory=3408/8192 MiB
          processes: unavailable（宿主未报告计算进程，记原因不填 0）
manifest metadata: runtime_evidence=runtime_evidence.json
cache: .atst_cache/attempt-1（每 attempt 独立可写目录）
```

## 5. 结论与局限

- 隔离路径在真实 GPU 上完成“请求 → 收窄 → child 绑定 → DP 推理 → 证据”
  全链路；旧调用（无 runtime 键）路径未受影响（全量单测）。
- 局限：单卡 RTX 2070 SUPER、单进程、无 MPI/ABACUS/SIF 参与；采样为宿主
  范围（整卡）值，进程归属在当前环境不可用；未测量并发/吞吐。
- 后续：SAI 4V100 的并发曲线、NEB 图数×卡数映射、DP image-parallel NEB
  E2E 与 ABACUS 侧基准按计划 P5 执行（需维护者确认 fixture/容差/预算）。
