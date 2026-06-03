# Zn Segmented NEB Runtime Status

**Version**: 2.0.1
**Date**: 2026-05-30
**Status**: Maintained
**Owner**: ATST-Tools maintainers
**Original working note**: `.trae/documents/Zn-NEB-segments.md`

This report preserves the active runtime evidence for the segmented Zn
migration NEB/AutoNEB/D2S plan. It supersedes the initial single-path Zn
validation report and the temporary `.trae` working note.

  ## Summary

  目标是重新计算 Zn 从初态到末态的迁移轨迹和能垒，同时保留三条独立路线互相校验：

  1. 分段直接 NEB；
  2. 分段 AutoNEB；
  3. 分段 D2S rough NEB + CCQN。

  核心策略不再让一个单段 NEB 直接处理 6.6968 A 的 Zn 长程迁移，而是先构造 2 个中间 Zn 位点，把全路径拆成 3 段短迁
  移。每段单独收敛后，再拼接全路径并以统一能量零点计算总 barrier。

  所有 ABACUS 输入继续由 ASE/ATST 驱动几何更新，ABACUS 本身只做单点力计算：

  calculation: scf
  nspin: 2

  旧的 nspin=1 endpoint single-point 结果不能复用，需要重新生成 nspin=2 endpoint 与中间点单点/优化结果。

  ## Common Setup

  - 新建一套 nspin=2 专用输入与运行目录，避免污染旧结果：
      - inputs_nspin2/
      - neb_segmented_nspin2/
      - autoneb_segmented_nspin2/
      - d2s_ccqn_segmented_nspin2/
  - 基于现有 inputs/cineb_endpoint_initial.traj 和 inputs/cineb_endpoint_final.traj 只取结构，不复用其中旧
    SinglePointCalculator。
  - 构造 2 个中间候选位点：
      - M1：Zn 沿初末态 MIC 位移约 1/3 处的结构；
      - M2：Zn 沿初末态 MIC 位移约 2/3 处的结构；
      - 非 Zn 框架初始用 IDPP/线性插值，再用 ABACUS nspin=2 做端点式局部优化。
  - 三段路径固定为：
      - Segment A: IS -> M1
      - Segment B: M1 -> M2
      - Segment C: M2 -> FS
  - ABACUS 参数基于现有 INPUT，但统一加入：
      - calculation: scf
      - nspin: 2
      - init_wfc: atomic
      - init_chg: atomic
      - scf_nmax: 500
      - mixing_beta: 0.25
  - 保留现有关键设置：
      - basis_type: lcao
      - ks_solver: cusolver
      - ecutwfc: 150
      - kspacing: "1.0 0.14 0.14"
      - symmetry: 0
      - vdw_method: d3_0
      - cal_force: 1
      - cal_stress: 0

  ## Scheme 1: Direct Segmented NEB

  直接 NEB 作为基准路线和路径生成路线。

  - 每段使用 8 个 internal images，总计 10 images。
  - 每段先跑 non-climbing warmup：
      - climb: false
      - fmax: 0.30
      - max_steps: 250
      - k: 0.05
      - optimizer: FIRE
      - optimizer_kwargs.maxstep: 0.03
  - warmup 收敛或明显下降后，重启 climbing NEB：
      - climb: true
      - fmax: 0.05
      - max_steps: 500
      - k: 0.08
      - optimizer_kwargs.maxstep: 0.03
  - 判定成功：
      - 每段最终 max fmax < 0.08 eV/A，目标 < 0.05 eV/A；
      - barrier 最近 5 个 band 不单调恶化；
      - 最大力不持续集中在 Zn 或 Zn 邻近 N/O 且数值升高。
  - 总 barrier：
      - 拼接三段最终 band；
      - 以 nspin=2 的 IS 能量为零点；
      - 取全路径最高能 image 的相对能量作为总能垒。

  ## Scheme 2: Segmented AutoNEB

  AutoNEB 作为自适应图像密度校验路线，不再从旧 4-image 全路径启动。

  - 每段从 IS/M1/M2/FS 端点生成 4-image 初始链。
  - 每段 AutoNEB 先关闭 climbing 做 path discovery：
      - n_simul: 4
      - n_max: 12
      - climb: false
      - fmax: [0.35, 0.12]
      - maxsteps: [100, 220]
      - optimizer_kwargs.maxstep: 0.03
  - path discovery 后重启 final AutoNEB：
      - restart: true
      - climb: true
      - fmax: [0.20, 0.05]
      - maxsteps: [150, 350]
      - n_max: 14
  - 作业脚本增加 watchdog 规则：
      - 若当前 abacus.out 超过 60 分钟无更新，且 nvdmon 显示 GPU util 约为 0，则终止当前作业并保留已有 AutoNEB
        images；
      - 后续从最新完整 band clean restart。
  - 判定成功：
      - 每段最高能 image 与最大力 image 相同或相邻；
      - 每段 max fmax 不再停在 >0.5 eV/A；
      - 未复现旧 image_004 SCF CU14 挂死。

  ## Scheme 3: D2S Rough NEB + CCQN

  D2S+CCQN 作为 TS 精修路线，只从已经分段后的短路径启动。

  - 每段 D2S rough NEB：
      - method: ccqn
      - neb.n_images: 10
      - neb.fmax: 0.30
      - neb.max_steps: 450
      - neb.climb: true
      - neb.idpp_maxiter: 8000
      - neb.idpp_tol: 1.0e-5
      - neb.optimizer_kwargs.maxstep: 0.03
  - rough NEB handoff guard：
      - 最近 8 个 band 若 barrier 和 max fmax 数值冻结，则不进入 CCQN；
      - 若 max-energy image 与 max-force image 相差超过 1 个 image，则不进入 CCQN；
      - 若 max-energy image fmax >0.60 eV/A，先增加 images 或重做该段 NEB。
  - CCQN 参数使用 conservative 设置：
      - e_vector_method: interp
      - cos_phi: 0.7
  - CCQN 结果选择：
      - 保存全轨迹 best-fmax frame；
      - 若 fmax 曾低于 0.15 eV/A 后连续升高，则以 best frame 作为候选 TS，而不是最后一帧；
      - 最终 TS 候选需回连对应 segment 两侧 minima 做短 IRC/NEB 验证。

  ## Slurm / Server Plan

  - 预检查阶段使用 4V100PX 或 4V100 + rush-gpu：
      - endpoint nspin=2 single-point；
      - M1/M2 局部优化 smoke；
      - 每条 workflow 的 1 段短 smoke。
  - 生产阶段使用 4V100 + huge-gpu：
      - 1 node；
      - --gpus-per-node=4；
      - --ntasks=16；
      - OMP_NUM_THREADS=2；
      - 不设置 --mem 或 --cpus-per-task。
  - 每个 job 保留：
      - module load abacus/LTSv3.10.1-sm70-auto
      - source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash
      - nvidia-smi dmon -s pucvmte -o T
  - 推荐提交顺序：
      - 先跑 nspin=2 endpoint/M1/M2 验证；
      - 再跑 direct segmented NEB；
      - direct NEB 给出可用路径后，启动 AutoNEB 与 D2S+CCQN 作为独立校验；
      - 不建议一开始并行提交全部 9 个 segment jobs，先确认 Segment A 不再跑飞。

  ## 2026-05-29 Execution Update

  当前 `develop` 已合入 image-level MPI parallel NEB / AutoNEB。串行 ABACUS NEB 已暂停，后续 Zn 生产计算切换为
  image-parallel 模板：

  - Direct NEB warmup/climb：
      - 每段 8 个 moving images；
      - Slurm 使用 8 个 4V100 节点；
      - 外层 `mpirun -np 8`，每个 image rank 独占 1 个 4V100 节点；
      - 每个 image 内部 ABACUS 使用 `mpi: 4`, `omp: 8`。
  - AutoNEB discover/final：
      - `n_simul: 4`；
      - Slurm 使用 4 个 4V100 节点；
      - 外层 `mpirun -np 4`，每个并发 image rank 独占 1 个 4V100 节点；
      - 每个 image 内部 ABACUS 使用 `mpi: 4`, `omp: 8`。
  - D2S rough NEB + CCQN 当前 schema 未暴露 image-level parallel 开关，仍作为独立串行校验路线，需在 direct
    NEB/AutoNEB 至少一条路线给出连续分段路径后再继续推进。
  - 恢复计算时只先投递 Segment A direct NEB warmup，确认并行 ABACUS image 任务可以稳定推进后，再继续 Segment B/C
    或 AutoNEB，不一次性投递全部分段任务。

  ## 2026-05-29 Runtime Status

  - Segment A direct NEB warmup 已以 image-level parallel 运行并保留轨迹：
      - Slurm job: `465537` (`zn2-segA-pneb-warm`)；
      - 节点：8 个 4V100 节点；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 最后检查至 step 19：barrier 降至约 0.198185 eV，但 max fmax 从 step 14 的约 0.491509 eV/A 连续升至约 0.782096 eV/A；
      - max-energy image 仍在 image 5，但 max-force image 偏到 image 2，判断继续推进原 warmup 会浪费 8 节点资源；
      - 已取消 job `465537`，并保存 step 14 band 为 `inputs_nspin2/segA_step014_recover_neb10.traj`。
  - Segment A recovery warmup 已从 step 14 band 以更保守参数重启：
      - Slurm job `465660` 因 recovery workdir 的 `inputs_nspin2` symlink 指向错误，8 个 MPI rank 均报 `FileNotFoundError`，已取消；
      - symlink 已修正为 `../../inputs_nspin2` 后重新投递 Slurm job: `465666` (`zn2-segA-pneb-rec`)；
      - 节点：8 个 4V100 节点；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 参数调整：`k: 0.035`，`optimizer_kwargs.maxstep: 0.015`，仍为 `calculation: scf` + `nspin: 2`；
      - 已写出 7 个 recovery bands：barrier 从约 0.228229 eV 降至约 0.209492 eV，但 max fmax 从约 0.491509 eV/A 连续升至约 0.728394 eV/A；
      - max-energy image 固定在 image 5，max-force image 固定在 image 2，复现原 warmup 的力偏移问题，已取消 job `465666`；
      - 已保存 `inputs_nspin2/segA_recover_step000_candidate_neb10.traj` 和 `inputs_nspin2/segA_recover_step001_candidate_neb10.traj` 作为后续更保守/局部重构候选。
  - Segment B direct NEB warmup 已在 Segment A 稳定启动后投递并运行：
      - Slurm job: `465642` (`zn2-segB-pneb-warm`)；
      - 节点：8 个 4V100 节点；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 已完成，Slurm 状态 `COMPLETED`，ExitCode `0:0`；
      - warmup 最终写出 16 个 bands，barrier 从约 0.179454 eV 降至约 0.065668 eV，max fmax 从约 1.321165 eV/A 降至约 0.297160 eV/A，达到 warmup 阈值。
  - Segment B climbing NEB 已从 warmup 轨迹重启源投递：
      - 已将 `segB_warmup/results/neb.traj` 复制到 `segB_climb/results/neb.traj`，作为 `restart: true` 的 last-band 来源；
      - Slurm job: `466732` (`zn2-segB-pneb-climb`)；
      - 2026-05-29 17:17 已启动于 8 个 4V100 节点 `4v100n[03-10]`；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 当前 climb 轨迹已写出第 0 个 band，仍对应 warmup 末态：barrier 约 0.065668 eV，max fmax 约 0.297160 eV/A；等待后续 climbing steps。
      - 2026-05-29 17:26 已写出第 1 个 climbing band：barrier 约 0.064386 eV，max fmax 约 0.294232 eV/A；barrier 和 max fmax 均小幅下降，继续运行。
      - 2026-05-29 17:31 已写出第 2 个 climbing band：barrier 约 0.062708 eV，max fmax 约 0.288828 eV/A；仍在正常下降，继续运行。
      - 2026-05-29 17:36 已写出第 3 个 climbing band：barrier 约 0.060143 eV，max fmax 约 0.281717 eV/A；FIRE 日志 fmax 约 0.272390，继续运行。
      - 2026-05-29 17:40 已写出第 4 个 climbing band：barrier 约 0.056920 eV，max fmax 约 0.272522 eV/A；FIRE 日志 fmax 约 0.263340，继续运行。
      - 2026-05-29 17:50 已写出第 6 个 climbing band：barrier 约 0.050099 eV，max fmax 约 0.251555 eV/A；barrier 接近 0.05 eV，但 force 仍明显高于 climb 收敛阈值，继续运行。
      - 2026-05-29 17:55 已写出第 7 个 climbing band：barrier 约 0.046894 eV，max fmax 约 0.240370 eV/A；barrier 已低于 0.05 eV，但 force 仍未收敛，继续运行。
      - 2026-05-29 18:00 已写出第 8 个 climbing band：barrier 约 0.043846 eV，max fmax 约 0.228527 eV/A；仍在下降，继续运行。
      - 2026-05-29 18:04 已写出第 9 个 climbing band：barrier 约 0.040951 eV，max fmax 约 0.219453 eV/A；仍在下降，继续运行。
      - 2026-05-29 18:09 已写出第 10 个 climbing band：barrier 约 0.038183 eV，max fmax 约 0.210009 eV/A；仍在下降，继续运行。
      - 2026-05-29 18:19 已写出第 12 个 climbing band：barrier 约 0.033190 eV，max fmax 约 0.189753 eV/A；仍在下降，继续运行。
      - 2026-05-29 18:28 已写出第 14 个 climbing band：barrier 约 0.028764 eV，max fmax 约 0.171118 eV/A；仍在下降，继续运行。
      - 2026-05-29 18:38 已写出第 16 个 climbing band：barrier 约 0.024913 eV，max fmax 约 0.154806 eV/A；FIRE 日志 fmax 约 0.127424，仍在下降，继续运行。
      - 2026-05-29 18:56 已写出第 20 个 climbing band：barrier 约 0.018652 eV，max fmax 约 0.127709 eV/A；FIRE 日志 fmax 约 0.094160，仍在稳定下降，继续保留任务运行。
      - 2026-05-29 19:10 已写出第 23 个 climbing band：barrier 约 0.015058 eV，max fmax 约 0.117308 eV/A；FIRE 日志 fmax 约 0.074211，已低于可接受阈值 0.08 eV/A 但尚未达到目标 0.05 eV/A，继续运行至自然收敛或后续平台判据触发。
      - 2026-05-29 19:29 已写出第 27 个 climbing band：barrier 约 0.011443 eV，max fmax 约 0.105117 eV/A；FIRE 日志 fmax 约 0.050840，接近目标 0.05 eV/A 且仍在下降，继续保留任务自然收敛。
      - 2026-05-29 19:34 已自然收敛完成，Slurm 状态 `COMPLETED`、ExitCode `0:0`；最终第 28 个 climbing band 的 barrier 约 0.010705 eV，轨迹逐像 max fmax 约 0.101984 eV/A，FIRE 日志 fmax 约 0.046674，达到 climb 目标 0.05 eV/A。
  - Segment C direct NEB warmup 配置和脚本均已验证通过并投递：
      - Slurm job: `465680` (`zn2-segC-pneb-warm`)；
      - 已开始运行于 8 个 4V100 节点；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 配置为 image-level parallel，`calculation: scf` + `nspin: 2`；
      - 已写出 10 个 bands：barrier 从约 0.518135 eV 降至约 0.317225 eV，max fmax 从约 2.277051 eV/A 降至约 0.604217 eV/A；
      - step 6-7 的 fmax 回升后已恢复下降，当前继续运行。
      - 2026-05-29 16:53 复核：已写出 11 个 bands，最新 barrier 约 0.312407 eV，轨迹 max fmax 约 0.561755 eV/A，FIRE 日志 fmax 约 0.392481；尚未达到 warmup 阈值 0.30，但仍在下降，继续保留任务运行。
      - 2026-05-29 17:03 复核：已写出 12 个 bands，最新 barrier 约 0.309271 eV，轨迹 max fmax 约 0.552625 eV/A，FIRE 日志 fmax 约 0.417498；barrier 继续下降但 fmax 进入平台，暂不取消，继续观察。
      - 2026-05-29 17:10 复核：已写出 13 个 bands，最新 barrier 约 0.306947 eV，轨迹 max fmax 约 0.579371 eV/A，FIRE 日志 fmax 约 0.490999；barrier 仍缓慢下降，但 fmax 已回升，若后续 2-3 个 band 继续在 0.55-0.60 eV/A 附近振荡或上升，应停止 warmup 并从当前较低 barrier band 改用更保守/分段策略。
      - 2026-05-29 17:16 复核：已写出 14 个 bands，latest barrier 约 0.303796 eV，但轨迹 max fmax 升至约 0.617075 eV/A，FIRE 日志 fmax 升至约 0.601816；step 10-13 连续在 0.55-0.62 eV/A 平台并回升，已取消 job `465680` 释放 8 节点资源。
      - 已保存 `inputs_nspin2/segC_step011_recover_neb10.traj` 和 `inputs_nspin2/segC_step013_recover_neb10.traj`；其中 step 11 作为 C recovery 默认起点。
  - Segment C recovery warmup 已准备并排队：
      - 配置 `configs/zn_nspin2_segC_neb_warmup_recover_parallel.yaml` 已通过 `atst config validate`；
      - sbatch 脚本 `jobs/submit_zn_nspin2_segC_neb_warmup_recover_parallel.sbatch` 已通过 `bash -n`；
      - Slurm job: `467504` (`zn2-segC-pneb-rec`)；
      - 2026-05-29 20:53 已启动，运行于 8 个 4V100 节点 `4v100n[03,08-11,15,17,28]`；
      - 日志确认：`Image-level NEB parallelism active: world.size=8, interior_images=8`；
      - 2026-05-29 21:04 已写出 2 个 recovery bands：barrier 从约 0.309271 eV 降至约 0.305029 eV，轨迹 max fmax 从约 0.552625 eV/A 降至约 0.535859 eV/A；当前 recovery 相比旧 warmup 取消前的 fmax 回升更稳定，继续运行。
      - 2026-05-29 21:09 报告刷新确认当前 best band 仍为 barrier 约 0.305029 eV，max fmax 约 0.535859 eV/A；继续等待后续 recovery steps。
      - 2026-05-29 21:09 日志 FIRE fmax 已从 step 0 的约 0.417503 eV/A 降至 step 1 的约 0.357873 eV/A，继续运行。
      - 2026-05-29 21:16 已写出第 2 个 recovery step：barrier 约 0.301590 eV，轨迹 max fmax 约 0.521903 eV/A；FIRE 日志 fmax 约 0.311536 eV/A，继续下降。
      - 2026-05-29 21:23 自然完成，Slurm 状态 `COMPLETED`、ExitCode `0:0`；最终 FIRE fmax 约 0.293725 eV/A，达到 warmup 阈值 0.30；最终轨迹 barrier 约 0.298679 eV，轨迹 max fmax 约 0.511461 eV/A。
      - 参数为 `k: 0.035`、`optimizer_kwargs.maxstep: 0.015`、`calculation: scf` + `nspin: 2`。
  - Segment C climbing NEB 已从 recovery 轨迹重启源投递：
      - 已将 `segC_warmup_recover/results/neb.traj` 复制到 `segC_climb/results/neb.traj`，作为 `restart: true` 的 last-band 来源；
      - 配置 `configs/zn_nspin2_segC_neb_climb_parallel.yaml` 已通过 `atst config validate`；
      - sbatch 脚本 `jobs/submit_zn_nspin2_segC_neb_climb_parallel.sbatch` 已通过 `bash -n`；
      - Slurm job: `468233` (`zn2-segC-pneb-climb`)；
      - 2026-05-29 21:28 已启动，运行于 8 个 4V100 节点 `4v100n[08-11,19-22]`；
      - 2026-05-29 21:58 复核：任务继续保留运行；已写出 3 个 climbing bands，barrier 约 0.300592 eV，轨迹 max fmax 约 0.501117 eV/A，FIRE 日志 fmax 从 0.503580 降至 0.459515，尚未卡死。
      - 2026-05-29 22:00 报告刷新：已写出 4 个 climbing bands，barrier 约 0.302712 eV，轨迹 max fmax 约 0.484771 eV/A，max-energy image 为 image 6，max-force image 为 image 7，相邻且 fmax 继续下降，继续保留任务。
      - 2026-05-29 22:13 复核：已写出 5 个 climbing bands，barrier 约 0.304850 eV，轨迹 max fmax 约 0.465286 eV/A，FIRE 日志 fmax 降至约 0.349483；max-energy image 与 max-force image 仍相邻，继续运行。
      - 2026-05-29 22:20 复核：已写出 6 个 climbing bands，barrier 约 0.306326 eV，轨迹 max fmax 约 0.446221 eV/A，FIRE 日志 fmax 降至约 0.254373；max-energy image 与 max-force image 仍相邻，继续运行。
      - 2026-05-29 22:28 报告刷新：已写出 7 个 climbing bands，barrier 约 0.308136 eV，轨迹 max fmax 约 0.429454 eV/A，FIRE 日志 fmax 降至约 0.241510；max-energy image 与 max-force image 仍相邻，继续运行。
      - 2026-05-29 22:31 报告刷新：已写出 8 个 climbing bands，barrier 约 0.308841 eV，轨迹 max fmax 约 0.415116 eV/A，FIRE 日志 fmax 降至约 0.224739；max-energy image 与 max-force image 仍相邻，继续运行。
      - 2026-05-29 22:40 报告刷新：已写出 9 个 climbing bands，barrier 约 0.308939 eV，轨迹 max fmax 约 0.403261 eV/A，FIRE 日志 fmax 降至约 0.209283；max-energy image 为 image 6，max-force image 为 image 5，继续运行。
      - 2026-05-29 22:49 报告刷新：已写出 10 个 climbing bands，barrier 约 0.308425 eV，轨迹 max fmax 约 0.400472 eV/A，FIRE 日志 fmax 降至约 0.196224；max-energy image 为 image 6，max-force image 为 image 5，继续运行。
      - 2026-05-29 23:01 报告刷新：已写出 11 个 climbing bands，barrier 约 0.307381 eV，轨迹 max fmax 约 0.397497 eV/A，FIRE 日志 fmax 降至约 0.180164；max-energy image 为 image 6，max-force image 为 image 5，仍在下降，继续运行。
      - 2026-05-29 23:11 报告刷新：已写出 12 个 climbing bands，barrier 约 0.305886 eV，轨迹 max fmax 约 0.395221 eV/A，FIRE 日志 fmax 降至约 0.166253；max-energy image 为 image 6，max-force image 为 image 5，仍在下降，继续运行。
      - 2026-05-29 23:16 报告刷新：已写出 13 个 climbing bands，barrier 约 0.304096 eV，轨迹 max fmax 约 0.383383 eV/A；max-energy image 为 image 6，max-force image 为 image 5，继续下降，继续运行。
      - 2026-05-29 23:21 复核：暂无新增完整 band；FIRE 日志 step 12 fmax 约 0.168160，较 step 11 小幅回升但整体仍低于前序平台，保留任务继续观察。
      - 2026-05-29 23:26 报告刷新：已写出 14 个 climbing bands，barrier 约 0.302151 eV，轨迹 max fmax 约 0.371644 eV/A；FIRE 日志 step 13 fmax 约 0.186657，较 step 12 继续回升，但轨迹 max fmax 仍下降，保留任务继续观察。
      - 2026-05-29 23:31 报告刷新：已写出 15 个 climbing bands，barrier 约 0.300178 eV，轨迹 max fmax 约 0.363829 eV/A；max-energy image 为 image 6，max-force image 为 image 5。轨迹力继续下降，保留任务运行。
      - 2026-05-29 23:36 报告刷新：暂无新增完整 band；FIRE 日志 step 14 fmax 约 0.197372，连续两步回升但轨迹 max fmax 尚未平台化，继续保留观察。
      - 2026-05-29 23:42 报告刷新：已写出 16 个 climbing bands，barrier 约 0.298271 eV，轨迹 max fmax 约 0.357357 eV/A；FIRE 日志 step 15 fmax 约 0.200707，仍在回升，但轨迹 max fmax 继续下降，保留任务继续观察。
      - 2026-05-29 23:47 报告刷新：已写出 17 个 climbing bands，barrier 约 0.296581 eV，轨迹 max fmax 约 0.350079 eV/A；FIRE 日志 step 16 fmax 约 0.197960，较 step 15 小幅回落，继续运行。
      - 2026-05-29 23:57 报告刷新：已写出 18 个 climbing bands，barrier 约 0.295076 eV，轨迹 max fmax 约 0.342602 eV/A；FIRE 日志 step 17 fmax 约 0.190029，继续运行。
      - 2026-05-30 00:02 报告刷新：已写出 19 个 climbing bands，barrier 约 0.293734 eV，轨迹 max fmax 约 0.335008 eV/A；FIRE 日志 step 18 fmax 约 0.177674，继续运行。
      - 2026-05-30 00:19 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 21 个 climbing bands，barrier 约 0.291218 eV，轨迹 max fmax 约 0.323304 eV/A，max-energy image 为 image 6，max-force image 为 image 7。轨迹力仍在下降，继续保留 NEB 任务。
      - 2026-05-30 00:25 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 22 个 climbing bands，barrier 约 0.289853 eV，轨迹 max fmax 约 0.320996 eV/A，FIRE 日志 step 21 fmax 约 0.123117 eV/A。仍未达到 climb 目标 0.05 eV/A，但没有卡死，继续保留任务运行。
      - 2026-05-30 00:28 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 23 个 climbing bands，barrier 约 0.288388 eV，轨迹 max fmax 约 0.318481 eV/A，FIRE 日志 step 22 fmax 约 0.102600 eV/A。继续接近 climb 阈值，保留任务运行。
      - 2026-05-30 00:32 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 23 个 climbing bands，barrier 约 0.288388 eV，轨迹 max fmax 约 0.318481 eV/A，FIRE 最新 step 22 fmax 约 0.102600 eV/A。等待下一步写回。
      - 2026-05-30 00:37 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 24 个 climbing bands，barrier 约 0.286777 eV，轨迹 max fmax 约 0.315827 eV/A，FIRE 日志 step 23 fmax 约 0.082878 eV/A。继续接近 climb 目标，保留任务运行。
      - 2026-05-30 00:41 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 24 个 climbing bands，barrier 约 0.286777 eV，轨迹 max fmax 约 0.315827 eV/A，FIRE 最新 step 23 fmax 约 0.082878 eV/A。继续等待下一步写回。
      - 2026-05-30 00:45 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 25 个 climbing bands，barrier 约 0.285069 eV，轨迹 max fmax 约 0.313051 eV/A，FIRE 日志 step 24 fmax 约 0.065116 eV/A。接近但尚未达到 0.05 eV/A climb 目标，继续保留任务运行。
      - 2026-05-30 00:49 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 25 个 climbing bands，barrier 约 0.285069 eV，轨迹 max fmax 约 0.313051 eV/A，FIRE 最新 step 24 fmax 约 0.065116 eV/A。继续等待自然收敛或下一步写回。
      - 2026-05-30 00:54 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 26 个 climbing bands，barrier 约 0.283315 eV，轨迹 max fmax 约 0.310040 eV/A；FIRE step 25 fmax 回升至约 0.071857 eV/A，尚未达到 0.05 eV/A。轨迹 max fmax 仍下降，继续保留观察。
      - 2026-05-30 00:59 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 27 个 climbing bands，barrier 约 0.281576 eV，轨迹 max fmax 约 0.306913 eV/A；FIRE step 26 fmax 约 0.077178 eV/A。FIRE fmax 连续两步回升，但轨迹 max fmax 与 barrier 仍下降，暂不取消，继续观察是否形成平台。
      - 2026-05-30 01:03 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 27 个 climbing bands，barrier 约 0.281576 eV，轨迹 max fmax 约 0.306913 eV/A；FIRE 最新 step 26 fmax 约 0.077178 eV/A。继续观察下一步是否回落或形成平台。
      - 2026-05-30 01:08 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 28 个 climbing bands，barrier 约 0.279882 eV，轨迹 max fmax 约 0.303643 eV/A；FIRE step 27 fmax 约 0.079729 eV/A。FIRE fmax 连续三步回升但路径 barrier 和轨迹 max fmax 仍下降，暂不取消，下一轮重点确认是否平台化。
      - 2026-05-30 01:13 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 29 个 climbing bands，barrier 约 0.278307 eV，轨迹 max fmax 约 0.300423 eV/A；FIRE 最新 step 27 fmax 仍约 0.079729 eV/A。路径指标仍持续改善，暂不取消。
      - 2026-05-30 01:18 报告刷新：作业 `468233` 仍为 `RUNNING`；最新仍为 29 个 climbing bands，barrier 约 0.278307 eV，轨迹 max fmax 约 0.300423 eV/A；FIRE step 28 fmax 约 0.080389 eV/A。FIRE fmax 已连续四步在 0.07-0.08 eV/A 附近，但路径指标此前仍改善，继续观察下一步是否同时平台化。
      - 2026-05-30 01:36 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 32 个 climbing bands，barrier 约 0.274116 eV，轨迹 max fmax 约 0.367559 eV/A。barrier 仍在下降，但 max-force image 的力较 01:18 明显回升，继续保留任务并重点观察是否形成新的高力平台。
      - 2026-05-30 01:59 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 35 个 climbing bands，barrier 约 0.270206 eV，轨迹 max fmax 约 0.347322 eV/A。barrier 继续下降，max fmax 较 01:36 回落但仍高于 01:18，继续保留观察。
      - 2026-05-30 02:02 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 36 个 climbing bands，barrier 约 0.268868 eV，轨迹 max fmax 约 0.335510 eV/A，FIRE step 35 fmax 约 0.080750 eV/A。01:21 的高力回升后已逐步回落，但尚未达到 0.05 eV/A 目标，继续保留任务运行。
      - 2026-05-30 02:15 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 38 个 climbing bands，barrier 约 0.266225 eV，轨迹 max fmax 约 0.313104 eV/A。FIRE step 36/37 fmax 分别约 0.086639/0.090151 eV/A，较 step 35 回升但路径 barrier 和轨迹 max fmax 仍下降，继续保留观察。
      - 2026-05-30 02:24 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 39 个 climbing bands，barrier 约 0.264992 eV，轨迹 max fmax 约 0.304586 eV/A，FIRE step 38 fmax 约 0.091083 eV/A。路径指标继续改善，但 FIRE fmax 仍未达到 0.05 eV/A。
      - 2026-05-30 02:32 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 40 个 climbing bands，barrier 约 0.263760 eV，轨迹 max fmax 约 0.298423 eV/A，FIRE step 39 fmax 约 0.089943 eV/A。轨迹指标继续改善，但 FIRE fmax 仍处于 0.09 eV/A 附近，继续观察。
      - 2026-05-30 02:38 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 41 个 climbing bands，barrier 约 0.262626 eV，轨迹 max fmax 约 0.294528 eV/A，FIRE step 40 fmax 约 0.087048 eV/A。barrier 与轨迹 max fmax 仍在下降，因此保留该 NEB 任务继续运行。
      - 2026-05-30 02:41 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 41 个 climbing bands，barrier 约 0.262626 eV，轨迹 max fmax 约 0.294528 eV/A，FIRE 最新 step 40 fmax 约 0.087048 eV/A。继续等待下一步写回。
      - 2026-05-30 02:43 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 42 个 climbing bands，barrier 约 0.261518 eV，轨迹 max fmax 约 0.293604 eV/A，FIRE step 41 fmax 约 0.082387 eV/A。barrier 与 FIRE fmax 继续下降，保留任务运行。
      - 2026-05-30 02:46 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，最新仍为 42 个 climbing bands，barrier 约 0.261518 eV，轨迹 max fmax 约 0.293604 eV/A，FIRE 最新 step 41 fmax 约 0.082387 eV/A。继续等待下一步写回。
      - 2026-05-30 02:48 报告刷新：作业 `468233` 仍为 `RUNNING`；`neb.traj` 最新 mtime 仍为 02:42:53，暂无新增完整 band。继续等待下一步写回。
      - 2026-05-30 02:49 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 43 个 climbing bands，barrier 约 0.260408 eV，轨迹 max fmax 约 0.292950 eV/A。路径指标继续缓慢改善，但仍未达到 final 阈值。
      - 2026-05-30 02:51 复核：作业 `468233` 仍为 `RUNNING`；报告值仍为 43 个 climbing bands、barrier 约 0.260408 eV、轨迹 max fmax 约 0.292950 eV/A，日志显示 FIRE step 42 fmax 降至约 0.076235 eV/A。继续保留任务等待下一步写回。
      - 2026-05-30 02:53 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，`neb.traj` 最新 mtime 仍为 02:49:49，当前仍为 barrier 约 0.260408 eV、轨迹 max fmax 约 0.292950 eV/A。
      - 2026-05-30 02:54 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 43 个 climbing bands、barrier 约 0.260408 eV、轨迹 max fmax 约 0.292950 eV/A。
      - 2026-05-30 02:56 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 43 个 climbing bands、barrier 约 0.260408 eV、轨迹 max fmax 约 0.292950 eV/A，日志最新仍为 FIRE step 42 fmax 约 0.076235 eV/A。
      - 2026-05-30 02:58 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 44 个 climbing bands，barrier 约 0.259320 eV，轨迹 max fmax 约 0.292738 eV/A，日志 step 43 fmax 约 0.068932 eV/A。继续接近 0.05 eV/A final 阈值，但尚未达到。
      - 2026-05-30 02:59 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 44 个 climbing bands、barrier 约 0.259320 eV、轨迹 max fmax 约 0.292738 eV/A。
      - 2026-05-30 03:01 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 44 个 climbing bands、barrier 约 0.259320 eV、轨迹 max fmax 约 0.292738 eV/A。
      - 2026-05-30 03:03 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 44 个 climbing bands、barrier 约 0.259320 eV、轨迹 max fmax 约 0.292738 eV/A。
      - 2026-05-30 03:05 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 45 个 climbing bands，barrier 约 0.258224 eV，轨迹 max fmax 约 0.292000 eV/A，日志 step 44 fmax 约 0.061750 eV/A。继续接近 0.05 eV/A final 阈值，但尚未达到。
      - 2026-05-30 03:07 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 45 个 climbing bands、barrier 约 0.258224 eV、轨迹 max fmax 约 0.292000 eV/A，日志最新仍为 step 44 fmax 约 0.061750 eV/A。
      - 2026-05-30 03:11 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 46 个 climbing bands，barrier 约 0.257108 eV，轨迹 max fmax 约 0.290428 eV/A，日志 step 45 fmax 约 0.059947 eV/A。继续接近 0.05 eV/A final 阈值，但尚未达到。
      - 2026-05-30 03:09 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 45 个 climbing bands、barrier 约 0.258224 eV、轨迹 max fmax 约 0.292000 eV/A。
      - 2026-05-30 03:15 报告刷新：作业 `468233` 保持运行；报告仍为 46 个 climbing bands、barrier 约 0.257108 eV、轨迹 max fmax 约 0.290428 eV/A，日志最新仍为 step 45 fmax 约 0.059947 eV/A。该 NEB 任务不取消，继续等待自然收敛或下一步写回。
      - 2026-05-30 03:17 报告刷新：作业 `468233` 仍为 `RUNNING`；`neb.traj` 最新写回仍为 03:10:32，当前仍为 46 个 climbing bands、barrier 约 0.257108 eV、轨迹 max fmax 约 0.290428 eV/A。暂无新增完整 band，继续保留运行。
      - 2026-05-30 03:18 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 47 个 climbing bands，barrier 约 0.255986 eV，轨迹 max fmax 约 0.288344 eV/A，日志 step 46 fmax 约 0.058050 eV/A。仍未达到 0.05 eV/A final 阈值，但继续缓慢下降，保留运行。
      - 2026-05-30 03:20 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，`neb.traj` 最新写回仍为 03:17:24，当前仍为 47 个 climbing bands、barrier 约 0.255986 eV、轨迹 max fmax 约 0.288344 eV/A。
      - 2026-05-30 03:21 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 47 个 climbing bands、barrier 约 0.255986 eV、轨迹 max fmax 约 0.288344 eV/A，日志最新仍为 step 46 fmax 约 0.058050 eV/A。
      - 2026-05-30 03:23 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，`neb.traj` 最新写回仍为 03:17:24，当前仍为 47 个 climbing bands、barrier 约 0.255986 eV、轨迹 max fmax 约 0.288344 eV/A。
      - 2026-05-30 03:25 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 48 个 climbing bands，barrier 降至约 0.254873 eV，轨迹 max fmax 降至约 0.286392 eV/A，`neb.traj` 最新写回为 03:24:54。仍未达到 final 阈值，继续保留运行。
      - 2026-05-30 03:27 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 48 个 climbing bands、barrier 约 0.254873 eV、轨迹 max fmax 约 0.286392 eV/A；日志 step 47 fmax 约 0.056040 eV/A，继续接近 0.05 eV/A。
      - 2026-05-30 03:28 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 48 个 climbing bands、barrier 约 0.254873 eV、轨迹 max fmax 约 0.286392 eV/A，日志最新仍为 step 47 fmax 约 0.056040 eV/A。
      - 2026-05-30 03:30 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 48 个 climbing bands、barrier 约 0.254873 eV、轨迹 max fmax 约 0.286392 eV/A，日志最新仍为 step 47 fmax 约 0.056040 eV/A。
      - 2026-05-30 03:32 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 49 个 climbing bands，barrier 降至约 0.253773 eV，轨迹 max fmax 降至约 0.284897 eV/A，日志 step 48 fmax 约 0.054000 eV/A。仍未达到 final 阈值，但继续接近 0.05 eV/A。
      - 2026-05-30 03:33 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 49 个 climbing bands、barrier 约 0.253773 eV、轨迹 max fmax 约 0.284897 eV/A，日志最新仍为 step 48 fmax 约 0.054000 eV/A。
      - 2026-05-30 03:35 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 49 个 climbing bands、barrier 约 0.253773 eV、轨迹 max fmax 约 0.284897 eV/A，日志最新仍为 step 48 fmax 约 0.054000 eV/A。
      - 2026-05-30 03:37 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 49 个 climbing bands、barrier 约 0.253773 eV、轨迹 max fmax 约 0.284897 eV/A，日志最新仍为 step 48 fmax 约 0.054000 eV/A。
      - 2026-05-30 03:42 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 50 个 climbing bands，barrier 降至约 0.252727 eV，轨迹 max fmax 降至约 0.283598 eV/A，日志 step 49 fmax 约 0.051901 eV/A。该段已非常接近 0.05 eV/A final 阈值，但尚未自然完成，继续保留运行。
      - 2026-05-30 03:44 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，`neb.traj` 最新完整写回仍为 03:38:33，当前仍为 50 个 climbing bands、barrier 约 0.252727 eV、轨迹 max fmax 约 0.283598 eV/A，日志最新仍为 step 49 fmax 约 0.051901 eV/A。
      - 2026-05-30 03:46 报告刷新：作业 `468233` 仍为 `RUNNING`；已写出 51 个 climbing bands，barrier 降至约 0.251733 eV，轨迹 max fmax 降至约 0.282127 eV/A，日志 step 50 fmax 约 0.050695 eV/A。距离 0.05 eV/A 阈值仅约 0.0007 eV/A，继续等待自然完成。
      - 2026-05-30 03:47 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 51 个 climbing bands、barrier 约 0.251733 eV、轨迹 max fmax 约 0.282127 eV/A，日志最新仍为 step 50 fmax 约 0.050695 eV/A。
      - 2026-05-30 03:49 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，当前仍为 51 个 climbing bands、barrier 约 0.251733 eV、轨迹 max fmax 约 0.282127 eV/A，日志仍停在 step 50 fmax 约 0.050695 eV/A。
      - 2026-05-30 03:50 报告刷新：作业 `468233` 仍为 `RUNNING`；暂无新增完整 band，`neb.traj` 最新完整写回仍为 03:45:11，日志仍停在 step 50 fmax 约 0.050695 eV/A，继续等待低于 0.05 eV/A 后自然完成。
      - 2026-05-30 03:52 自然收敛完成，Slurm 状态 `COMPLETED`、ExitCode `0:0`；最终日志 step 51 fmax 约 0.049380 eV/A，并出现 `NEB calculation finished`。正式报告写出 52 个 climbing bands，barrier 约 0.250801 eV，max-energy image 为 image 6，轨迹 max fmax 约 0.280878 eV/A，max-force image 为 image 5。该段满足 climbing NEB 优化器 fmax 目标，但报告中的逐像轨迹 max fmax 仍高，后续最终报告需同时列出 optimizer fmax 与轨迹逐像 max fmax，避免混淆。
      - 2026-05-30 03:54 复核：Slurm `sacct` 仍确认 `468233` 为 `COMPLETED`、ExitCode `0:0`；报告最终值保持 barrier 约 0.250801 eV、52 个 climbing bands。
      - 配置为 image-level parallel climbing NEB，`climb: true`、`calculation: scf` + `nspin: 2`。
  - Segment A AutoNEB discover 已作为 direct NEB 卡点后的独立路线排队：
      - 配置 `configs/zn_nspin2_segA_autoneb_discover_parallel.yaml` 已通过 `atst config validate`；
      - sbatch 脚本 `jobs/submit_zn_nspin2_segA_autoneb_discover_parallel.sbatch` 已通过 `bash -n`；
      - Slurm job: `467473` (`zn2-segA-pautodisc`)；
      - 2026-05-29 19:34 随 Segment B climb 完成释放节点后启动，运行于 4 个 4V100 节点 `4v100n[04-07]`；
      - 日志确认：`Image-level AutoNEB parallelism active: world.size=4, n_simul=4`；
      - 2026-05-29 19:47 复核：initial endpoint single-point 已完成并进入 final endpoint single-point；尚未写出 AutoNEB 轨迹；
      - 2026-05-29 19:56 复核：final endpoint single-point 已完成，AutoNEB 开始 initial images evaluation，并创建 `segA_autoneb000.traj` 到 `segA_autoneb005.traj`；当前中间 images 仍为空文件，等待 ABACUS 图像评估写回。
      - 2026-05-29 20:02 复核：6 个 initial AutoNEB images 均已写回；当前 barrier 约 0.407514 eV，max-energy image 与 max-force image 均为 image 3，max fmax 约 1.684468 eV/A；这是第一轮未优化 band，继续运行观察是否下降。
      - 2026-05-29 20:13 复核：barrier 降至约 0.349308 eV，max fmax 约 1.218613 eV/A；max-energy image 为 image 3，max-force image 为 image 2，相邻，继续运行。
      - 2026-05-29 20:20 复核：barrier 继续降至约 0.330780 eV，max fmax 约 1.196605 eV/A；max-energy image 为 image 3，max-force image 为 image 2，仍相邻，继续运行。
      - 2026-05-29 20:30 复核：barrier 降至约 0.292082 eV，max fmax 降至约 0.806822 eV/A；max-energy image 为 image 3，max-force image 为 image 2，仍相邻，继续运行。
      - 2026-05-29 20:48 复核：barrier 降至约 0.259275 eV，max fmax 降至约 0.592114 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 20:55 复核：barrier 降至约 0.250431 eV，max fmax 降至约 0.566874 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 20:57 复核：barrier 降至约 0.240826 eV，max fmax 降至约 0.541036 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 21:07 复核：barrier 降至约 0.222580 eV，max fmax 降至约 0.492526 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 21:15 复核：barrier 降至约 0.214167 eV，max fmax 降至约 0.471685 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 21:16 复核：barrier 降至约 0.196923 eV，max fmax 降至约 0.434201 eV/A；max-energy image 与 max-force image 均为 image 3，继续运行。
      - 2026-05-29 21:58 复核：AutoNEB 已进入 iteration 3，当前 8 个 image 文件均非空；当前 barrier 约 0.172649 eV，max fmax 约 0.453977 eV/A，较前序继续下降，任务保留运行。
      - 2026-05-29 21:59 复核：iteration 3 中间 image 继续更新；当前 barrier 约 0.170611 eV，max fmax 约 0.392483 eV/A，max-energy image 为 image 5，max-force image 为 image 2，继续运行等待后续插点/优化。
      - 2026-05-29 22:06 复核：AutoNEB 已进入 iteration 4，并新增到 9 个 image 文件；`segA_autoneb001.traj` 到 `segA_autoneb004.traj` 正处于 0 字节重写瞬态，暂不刷新报告。iteration 3 FIRE 日志 fmax 从 0.489356 降至 0.323428，任务仍在正常收敛。
      - 2026-05-29 22:13 复核：AutoNEB 已进入 iteration 5，并新增到 11 个 image 文件；`segA_autoneb005.traj` 到 `segA_autoneb008.traj` 正处于 0 字节重写瞬态，暂不刷新报告。已可读 images 的临时 barrier 约 0.143404 eV，临时 max fmax 约 0.329509 eV/A，仅作为运行中检查，不作为正式报告值。
      - 2026-05-29 22:20 复核：AutoNEB 已进入 iteration 7，并新增到 12 个 image 文件；`segA_autoneb007.traj` 到 `segA_autoneb010.traj` 正处于 0 字节重写瞬态，暂不刷新报告。已可读 images 的临时 barrier 约 0.157716 eV，临时 max fmax 约 0.333587 eV/A，仅作为运行中检查，不作为正式报告值。
      - 2026-05-29 22:23 自然完成，Slurm 状态 `COMPLETED`、ExitCode `0:0`；12 个 image 文件均已写回。正式报告刷新后 barrier 约 0.167387 eV，max-energy image 为 image 7，max fmax 约 0.333587 eV/A，max-force image 为 image 6。该 discover 结果可作为 Segment A 后续 refine/final 的路径初猜，但尚未达到最终收敛阈值。
      - 配置为 image-level parallel AutoNEB，`calculation: scf` + `nspin: 2`。
  - Segment A AutoNEB final 已投递：
      - 配置 `configs/zn_nspin2_segA_autoneb_final_parallel.yaml` 已通过 `atst config validate`；
      - sbatch 脚本 `jobs/submit_zn_nspin2_segA_autoneb_final_parallel.sbatch` 已通过 `bash -n`；
      - Slurm job: `468378` (`zn2-segA-pautofin`)；
      - 2026-05-29 22:29 已启动，运行于 4 个 4V100 节点 `4v100n[04-07]`；
      - 2026-05-29 22:31 复核：日志确认 `Image-level AutoNEB parallelism active: world.size=4, n_simul=4`；当前正在 endpoint single-point 阶段，尚未写出 AutoNEB image 轨迹。
      - 2026-05-29 22:38 复核：任务仍在 endpoint single-point 阶段，尚未写出 AutoNEB image 轨迹；继续等待。
      - 2026-05-29 22:47 复核：任务已从 initial endpoint single-point 推进到 final endpoint single-point，但尚未写出 AutoNEB image 轨迹；继续等待。
      - 2026-05-29 22:56 复核：任务继续保留运行；日志确认已进入 initial images evaluation，当前处于 `Now starting iteration 1 on [0, 1, 2, 3, 4, 5]`，未观察到需要取消的错误。
      - 2026-05-29 23:01 报告刷新：6 个 initial images 均已写回；当前 barrier 约 0.407514 eV，max-energy image 与 max-force image 均为 image 3，max fmax 约 1.684468 eV/A。这是 final 阶段第一轮未优化 band，继续运行等待后续优化。
      - 2026-05-29 23:06 报告刷新：6 个 images 继续更新；当前 barrier 降至约 0.359673 eV，max fmax 约 1.200483 eV/A，max-energy image 为 image 3，max-force image 为 image 2。仍处于早期优化但方向正常，继续运行。
      - 2026-05-29 23:11 报告刷新：当前 barrier 降至约 0.349308 eV，max fmax 约 1.218613 eV/A，max-energy image 为 image 3，max-force image 为 image 2。barrier 继续下降但力尚高，保留任务继续优化。
      - 2026-05-29 23:16 报告刷新：当前 barrier 降至约 0.330780 eV，max fmax 约 1.196605 eV/A，max-energy image 为 image 3，max-force image 为 image 2。仍未收敛但整体继续改善，保留任务继续运行。
      - 2026-05-29 23:21 报告刷新：当前 barrier 降至约 0.313220 eV，max fmax 约 1.111443 eV/A，max-energy image 为 image 3，max-force image 为 image 2。力仍高但继续改善，保留任务继续运行。
      - 2026-05-29 23:26 报告刷新：当前 barrier 降至约 0.301479 eV，max fmax 约 0.969177 eV/A，max-energy image 为 image 3，max-force image 为 image 2。力仍高但下降趋势明确，保留任务继续运行。
      - 2026-05-29 23:31 报告刷新：当前 barrier 降至约 0.292082 eV，max fmax 约 0.806822 eV/A，max-energy image 为 image 3，max-force image 为 image 2。仍未收敛但改善明显，保留任务继续运行。
      - 2026-05-29 23:36 报告刷新：当前 barrier 降至约 0.281142 eV，max fmax 约 0.669887 eV/A，max-energy image 为 image 3，max-force image 为 image 2。仍未收敛但继续稳定改善，保留任务继续运行。
      - 2026-05-29 23:42 报告刷新：当前 barrier 降至约 0.269383 eV，max fmax 约 0.617079 eV/A，max-energy image 与 max-force image 均为 image 3。继续改善，保留任务继续运行。
      - 2026-05-29 23:47 报告刷新：当前 barrier 降至约 0.259275 eV，max fmax 约 0.592114 eV/A，max-energy image 与 max-force image 均为 image 3。继续改善，保留任务继续运行。
      - 2026-05-29 23:52 报告刷新：当前 barrier 降至约 0.250431 eV，max fmax 约 0.566874 eV/A，max-energy image 与 max-force image 均为 image 3。仍未达到 final 收敛阈值，保留任务继续运行。
      - 2026-05-29 23:57 报告刷新：当前 barrier 降至约 0.240826 eV，max fmax 约 0.541036 eV/A，max-energy image 与 max-force image 均为 image 3。仍未达到 final 收敛阈值，保留任务继续运行。
      - 2026-05-30 00:02 报告刷新：当前 barrier 降至约 0.231134 eV，max fmax 约 0.515791 eV/A，max-energy image 与 max-force image 均为 image 3。仍未达到 final 收敛阈值，保留任务继续运行。
      - 2026-05-30 00:19 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 降至约 0.196923 eV，max fmax 降至约 0.434201 eV/A，max-energy image 与 max-force image 均为 image 3。仍未达到 final 收敛阈值，但趋势正常，继续保留任务运行。
      - 2026-05-30 00:25 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.189681 eV，max fmax 约 0.414440 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，继续保留任务运行。
      - 2026-05-30 00:28 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.184062 eV，max fmax 约 0.393392 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，但 barrier 和 max fmax 均继续下降。
      - 2026-05-30 00:32 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.178820 eV，max fmax 约 0.372184 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，但继续稳定改善。
      - 2026-05-30 00:37 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.173883 eV，max fmax 约 0.352370 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，但继续下降。
      - 2026-05-30 00:41 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.169003 eV，max fmax 约 0.334984 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，但继续改善。
      - 2026-05-30 00:45 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.164434 eV，max fmax 约 0.319235 eV/A，max-energy image 为 image 4，max-force image 为 image 3。仍未达到 final 收敛阈值，但继续改善。
      - 2026-05-30 00:49 报告刷新：作业 `468378` 仍为 `RUNNING`；当前报告值仍为 barrier 约 0.164434 eV、max fmax 约 0.319235 eV/A，尚未新增完整可读更新。继续等待 AutoNEB final 后续写回。
      - 2026-05-30 00:50 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.160144 eV，max fmax 约 0.303969 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 00:54 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.160144 eV，max fmax 约 0.303969 eV/A，暂无进一步完整写回，继续等待。
      - 2026-05-30 00:55 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.155925 eV，max fmax 约 0.288267 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 00:59 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.152019 eV，max fmax 约 0.272266 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 01:03 报告刷新：作业 `468378` 仍为 `RUNNING`；当前报告值仍为 barrier 约 0.152019 eV、max fmax 约 0.272266 eV/A，暂无进一步完整写回。
      - 2026-05-30 01:04 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.148316 eV，max fmax 约 0.256938 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 01:08 报告刷新：作业 `468378` 仍为 `RUNNING`；当前报告值仍为 barrier 约 0.148316 eV、max fmax 约 0.256938 eV/A，暂无进一步完整写回。
      - 2026-05-30 01:09 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.144764 eV，max fmax 约 0.242580 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 01:13 报告刷新：作业 `468378` 仍为 `RUNNING`；当前报告值仍为 barrier 约 0.144764 eV、max fmax 约 0.242580 eV/A，暂无进一步完整写回。
      - 2026-05-30 01:14 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.141484 eV，max fmax 约 0.228832 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 01:18 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.138313 eV，max fmax 约 0.215103 eV/A，继续改善但仍未达到 final 收敛阈值。
      - 2026-05-30 01:36 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB 已扩展到 8 个 image，当前 barrier 约 0.135403 eV，max fmax 约 0.233937 eV/A。进入插图/重优化阶段后 max fmax 较 01:18 小幅回升，但 barrier 继续下降，保留任务运行。
      - 2026-05-30 01:59 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB 正在插图/重写阶段，已有 10 个 image 文件，其中 `segA_autoneb005.traj` 到 `segA_autoneb008.traj` 暂为 0 字节。报告脚本已标记 `incomplete_autoneb_write` 并跳过临时数值，等待全部 image 可读后再更新 barrier/fmax。
      - 2026-05-30 02:02 复核：作业 `468378` 仍为 `RUNNING`；AutoNEB 日志已进入 `Now starting iteration 6 on [4, 5, 6, 7, 8, 9]`，当前已有 `segA_autoneb000.traj` 到 `segA_autoneb010.traj` 共 11 个 image 文件，其中 `segA_autoneb005.traj` 到 `segA_autoneb008.traj` 仍为空文件。继续等待插图阶段写回完整 image 后再判定收敛趋势。
      - 2026-05-30 02:07 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB 已有 12 个 image 文件，其中 8 个可读，`segA_autoneb007.traj` 到 `segA_autoneb010.traj` 暂为空文件。报告继续标记 `incomplete_autoneb_write`，不使用插图重写中的临时 barrier/fmax。
      - 2026-05-30 02:15 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB 日志已进入 iteration 8，当前已有 13 个 image 文件，其中 9 个可读，`segA_autoneb007.traj` 到 `segA_autoneb010.traj` 暂为空文件。继续等待插图阶段完成后再使用正式 barrier/fmax。
      - 2026-05-30 02:19 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB 已达到 `n_max: 14` 的 14 个 image 文件数量，其中 10 个可读，`segA_autoneb004.traj` 到 `segA_autoneb007.traj` 暂为空文件。仍处于重写瞬态，正式 barrier/fmax 等全部 image 可读后再采信。
      - 2026-05-30 02:24 复核：作业 `468378` 仍为 `RUNNING`；日志显示 `n_max images has been reached`，并已进入 `CI-NEB calculation` 的 iteration 10。报告中 14 个 image 文件已有 10 个可读，`segA_autoneb008.traj` 到 `segA_autoneb011.traj` 暂为空文件，说明 CI-NEB 阶段仍在重写中。
      - 2026-05-30 02:28 报告刷新：作业 `468378` 仍为 `RUNNING`；14 个 AutoNEB image 已全部可读。当前 barrier 约 0.136983 eV，max-energy image 为 image 10，max fmax 约 0.216784 eV/A，max-force image 为 image 3。CI-NEB 已有正式 band，但距离 final 目标 0.05 eV/A 仍较远，继续保留运行。
      - 2026-05-30 02:32 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.136699 eV，max fmax 仍约 0.216784 eV/A。CI-NEB barrier 小幅下降，但力尚未改善到 final 阈值。
      - 2026-05-30 02:38 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.136121 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 仍小幅下降，但力尚未达到 final 阈值，继续保留运行。
      - 2026-05-30 02:40 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.135285 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但 force 收敛仍未进入目标区间。
      - 2026-05-30 02:41 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.135285 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:43 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.135285 eV、max fmax 约 0.216784 eV/A，最新 image mtime 仍为 02:40:01。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:45 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.134214 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 02:46 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.134214 eV、max fmax 约 0.216784 eV/A，最新 image mtime 仍为 02:44:48。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:48 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.134214 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:49 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 约 0.132941 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 02:51 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.132941 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:53 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.132941 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:54 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 降至约 0.131506 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 02:56 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.131506 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:58 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.131506 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 02:59 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 降至约 0.129957 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 03:01 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.129957 eV、max fmax 约 0.216784 eV/A。继续保留任务等待 CI-NEB 后续写回。
      - 2026-05-30 03:03 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.129957 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:05 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 降至约 0.128153 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 03:07 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.128153 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:09 报告刷新：作业 `468378` 仍为 `RUNNING`；当前 barrier 降至约 0.126398 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 03:11 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.126398 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:15 报告刷新：作业 `468378` 保持运行；当前 barrier 降至约 0.124806 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 仍在下降，但最大力暂未改善到 0.05 eV/A final 阈值，继续保留任务。
      - 2026-05-30 03:17 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回仍为 03:13:10，当前 barrier 约 0.124806 eV、max fmax 约 0.216784 eV/A。暂无新增完整 image 更新，继续等待 CI-NEB 后续写回。
      - 2026-05-30 03:18 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:17:49，当前 barrier 降至约 0.123325 eV，max fmax 仍约 0.216784 eV/A，max-energy image 为 image 10、max-force image 为 image 3。CI-NEB barrier 继续下降，但最大力仍未改善到 final 阈值。
      - 2026-05-30 03:20 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，AutoNEB image 最新写回仍为 03:17:49，当前仍为 barrier 约 0.123325 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:21 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.123325 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:17:49。
      - 2026-05-30 03:23 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:22:28，barrier 降至约 0.122120 eV，max-energy image 移至 image 11，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。CI-NEB barrier 继续下降，但力仍未达到 final 阈值。
      - 2026-05-30 03:25 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.122120 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:22:28。
      - 2026-05-30 03:27 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:27:08，barrier 降至约 0.121501 eV，max-energy image 移至 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。CI-NEB barrier 继续下降，但力仍未达到 final 阈值。
      - 2026-05-30 03:28 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:27:08。
      - 2026-05-30 03:30 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:27:08。
      - 2026-05-30 03:32 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:31:49，barrier 仍约 0.121501 eV，max-energy image 为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。CI-NEB 高能区 image 8-11 的力继续下降，但全局最大力尚未改善到 final 阈值。
      - 2026-05-30 03:33 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:31:49。
      - 2026-05-30 03:35 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 更新，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，AutoNEB image 最新写回仍为 03:31:49。
      - 2026-05-30 03:37 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:36:30，barrier 仍约 0.121501 eV，max-energy image 为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。CI-NEB 高能区 image 8-11 的力继续下降，但全局最大力尚未改善到 final 阈值。
      - 2026-05-30 03:40 按要求保留该 NEB/AutoNEB 任务：作业 `468378` 仍为 `RUNNING`；报告刷新未见新的完整 image 写回，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，等待后续 CI-NEB 写回。
      - 2026-05-30 03:42 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:41:17，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。CI-NEB 高能区 image 8-11 的力继续下降，其中 image 10/11 已低于或接近 0.05 eV/A，但全局最大力仍由低能侧 image 3 控制。
      - 2026-05-30 03:44 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:41:17，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:46 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，max-force image 仍为 image 3。
      - 2026-05-30 03:47 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:45:58，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-11 的力继续下降，其中 image 10/11 已低于 0.04 eV/A，但低能侧 image 3 仍未改善。
      - 2026-05-30 03:49 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:45:58，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:50 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:45:58，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:52 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:50:41，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-11 的力继续改善，但低能侧 image 3 尚未下降。
      - 2026-05-30 03:54 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:50:41，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，继续等待 CI-NEB 后续写回。
      - 2026-05-30 03:56 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 03:55:22，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-11 的力相对 03:52 有局部回升，继续运行观察是否只是 CI-NEB 重优化波动。
      - 2026-05-30 03:57 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:55:22，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 03:59 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 03:55:22，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 04:00 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:00:04，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-11 的力继续局部回升，需继续观察 CI-NEB 后续是否重新压低该区域。
      - 2026-05-30 04:02 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 04:00:04，当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A。
      - 2026-05-30 04:05 按要求保留该 NEB/AutoNEB 任务：`squeue` 确认 job `468378` 仍为 `RUNNING`，运行于 4 个 4V100 节点 `4v100n[04-07]`；日志仍处于 final CI-NEB iteration 10，暂未出现完成行。
      - 2026-05-30 04:08 报告刷新：作业 `468378` 仍为 `RUNNING`，`sacct` 显示 batch/extern/prted 均为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:04:51，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-11 的 fmax 分别约 0.148171、0.090173、0.122351、0.169206 eV/A，较 04:00 出现回升；暂继续保留任务，等待下一轮 CI-NEB 是否重新压低该区域或自然结束。
      - 2026-05-30 04:10 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:09:34，barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，max fmax 仍约 0.216784 eV/A 且 max-force image 仍为 image 3。高能区 image 8-10 的 fmax 略降至约 0.144672、0.088918、0.120793 eV/A，但 image 11 升至约 0.174056 eV/A；继续观察后续 CI-NEB 是否压低高能区和低能侧 image 3。
      - 2026-05-30 04:11 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 04:09:34。当前仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，max-force image 仍为 image 3，尚未达到 final 阈值。
      - 2026-05-30 04:13 报告刷新：作业 `468378` 仍为 `RUNNING`；暂无新增完整 image 写回，AutoNEB image 最新完整写回仍为 04:09:34。当前指标维持 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A，max-force image 仍为 image 3；继续等待 CI-NEB iteration 10 的后续写回或自然结束。
      - 2026-05-30 04:14 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:14:17。barrier 仍约 0.121501 eV，max-energy image 仍为 image 12，但 max fmax 升至约 0.219018 eV/A 且 max-force image 转为 image 11；高能区 fmax 继续回升，尚未达到 final 阈值，需要继续观察是否形成平台或后续回落。
      - 2026-05-30 04:17 按要求保留该 NEB/AutoNEB 任务：`squeue` 确认 job `468378` 仍为 `RUNNING`，运行于 4 个 4V100 节点 `4v100n[04-07]`；当前用户队列中没有其他 D2S/CCQN 作业。报告刷新时间为 04:17:03，AutoNEB 最新完整写回仍为 04:14:17，当前指标维持 barrier 约 0.121501 eV、max fmax 约 0.219018 eV/A、max-energy image 12、max-force image 11，尚未达到 final 阈值。
      - 2026-05-30 04:19 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:19:04。当前 barrier 回升至约 0.128940 eV，max-energy image 转为 image 11，max fmax 显著升至约 1.505911 eV/A，max-force image 同为 image 11。`segA_autoneb_log_iter010.log` 中 FIRE step 24 的 optimizer fmax 为约 1.503958 eV/A，说明 final CI-NEB 出现明显回跳/失稳，尚不能作为收敛 TS 使用；按用户要求暂保留任务继续观察下一步是否回落或自然失败。
      - 2026-05-30 04:20 报告刷新：作业 `468378` 仍为 `RUNNING`，`sacct` 显示 batch/extern/prted 均为 `RUNNING`；暂无 04:19:04 之后的新完整 trajectory 写回。当前指标维持 barrier 约 0.128940 eV、max fmax 约 1.505911 eV/A，FIRE step 24 optimizer fmax 约 1.503958 eV/A；Segment A final CI-NEB 仍处于未收敛且失稳后的观察状态，不能用于最终 TS/全路径 barrier 定稿。
      - 2026-05-30 04:22 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 5:52:34；`sacct` 仍显示 batch/extern/prted 均为 `RUNNING`。暂无 04:19:04 之后的新完整 trajectory 写回，JSON 报告时间为 04:22:21，Segment A 指标仍为 barrier 约 0.128940 eV、max fmax 约 1.505911 eV/A、max-energy/max-force image 11；FIRE 日志仍停在 step 24、fmax 约 1.503958 eV/A。继续保留任务，但该状态仍不能满足最终报告 acceptance criteria。
      - 2026-05-30 04:23 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:23:45。相较 04:19 的明显回跳，本步部分恢复：barrier 回到约 0.121501 eV，max-energy image 回到 image 12，max fmax 降至约 0.593096 eV/A，max-force image 仍为 image 11；`segA_autoneb_log_iter010.log` 中 FIRE step 25 optimizer fmax 为约 0.593023 eV/A。该值仍远高于 final 阈值 0.05 eV/A，不能用于最终 TS/全路径 barrier 定稿，继续保留任务观察后续是否进一步回落。
      - 2026-05-30 04:25 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 5:55:44；暂无 04:23:45 之后的新完整 trajectory 写回。JSON 报告时间为 04:25:33，Segment A 指标维持 barrier 约 0.121501 eV、max fmax 约 0.593096 eV/A、max-energy image 12、max-force image 11；FIRE 日志仍停在 step 25、optimizer fmax 约 0.593023 eV/A。该段仍未达到 final 阈值，继续等待后续写回或自然结束。
      - 2026-05-30 04:27 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 5:57:23；暂无 04:23:45 之后的新完整 trajectory 写回。JSON 报告时间为 04:27:10，Segment A 指标仍为 barrier 约 0.121501 eV、max fmax 约 0.593096 eV/A、max-energy image 12、max-force image 11；FIRE 日志仍停在 step 25、optimizer fmax 约 0.593023 eV/A。继续保留任务，但尚不能进入最终 HTML 总结报告定稿。
      - 2026-05-30 04:28 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:28:26。Segment A 继续从 04:19 回跳中恢复：barrier 仍约 0.121501 eV、max-energy image 仍为 image 12，max fmax 降至约 0.324613 eV/A、max-force image 仍为 image 11；`segA_autoneb_log_iter010.log` 中 FIRE step 26 optimizer fmax 为约 0.324117 eV/A。该值仍高于 final 阈值 0.05 eV/A，继续保留任务等待后续写回。
      - 2026-05-30 04:30 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 6:00:48；暂无 04:28:26 之后的新完整 trajectory 写回。JSON 报告时间为 04:30:39，Segment A 指标仍为 barrier 约 0.121501 eV、max fmax 约 0.324613 eV/A、max-energy image 12、max-force image 11；FIRE 日志仍停在 step 26、optimizer fmax 约 0.324117 eV/A。继续保留任务等待后续写回或自然结束。
      - 2026-05-30 04:32 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 6:02:37；暂无 04:28:26 之后的新完整 trajectory 写回。JSON 报告时间为 04:32:25，Segment A 指标维持 barrier 约 0.121501 eV、max fmax 约 0.324613 eV/A、max-energy image 12、max-force image 11；FIRE 日志仍停在 step 26、optimizer fmax 约 0.324117 eV/A。继续保留任务，等待下一步是否进一步下降。
      - 2026-05-30 04:34 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:33:07。FIRE step 27 optimizer fmax 降至约 0.104248 eV/A，说明 04:19 回跳后已显著恢复；JSON 逐像统计中 barrier 仍约 0.121501 eV、max-energy image 仍为 image 12，高能区 image 8-11 的 fmax 已降至约 0.081888、0.051866、0.069232、0.103448 eV/A。但全局逐像 max fmax 仍为约 0.216784 eV/A，max-force image 回到 image 3，尚未达到 final 阈值 0.05 eV/A，继续保留任务。
      - 2026-05-30 04:35 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 6:06:04；暂无 04:33:07 之后的新完整 trajectory 写回。JSON 报告时间为 04:35:54，Segment A 指标仍为 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A、max-energy image 12、max-force image 3；FIRE 日志仍停在 step 27、optimizer fmax 约 0.104248 eV/A。继续等待下一步写回或自然结束。
      - 2026-05-30 04:38 报告刷新：作业 `468378` 仍为 `RUNNING`；AutoNEB image 最新完整写回更新至 04:37:48。FIRE step 28 optimizer fmax 降至约 0.091619 eV/A，高能区 image 8-11 的 fmax 继续降至约 0.072710、0.046371、0.061549、0.090834 eV/A，barrier 仍约 0.121501 eV、max-energy image 仍为 image 12。但全局逐像 max fmax 仍为约 0.216784 eV/A，max-force image 仍为 image 3；尚未达到 final 阈值 0.05 eV/A，继续保留任务等待后续写回。
      - 2026-05-30 04:39 报告刷新：作业 `468378` 仍为 `RUNNING`，运行约 6:10:05；暂无 04:37:48 之后的新完整 trajectory 写回。JSON 报告时间为 04:39:54，Segment A 指标维持 barrier 约 0.121501 eV、max fmax 约 0.216784 eV/A、max-energy image 12、max-force image 3；FIRE 日志仍停在 step 28、optimizer fmax 约 0.091619 eV/A。继续保留任务等待后续写回。
      - 2026-05-30 04:44 按要求保持该 NEB/AutoNEB 任务：`squeue` 确认 job `468378` 仍为 `RUNNING`，运行于 4 个 4V100 节点 `4v100n[04-07]`；当前用户队列中没有其他 D2S/CCQN 作业。AutoNEB image 最新完整写回更新至 04:42:29，FIRE step 29 optimizer fmax 降至约 0.067942 eV/A，说明 04:19 的回跳后仍在恢复并非完全卡死。JSON 报告时间为 04:43:54，Segment A barrier 仍约 0.121501 eV、max-energy image 12；高能区 image 8-11 的 fmax 已降至约 0.055580、0.036162、0.047219、0.067199 eV/A，但全局逐像 max fmax 仍为约 0.216784 eV/A、max-force image 仍为 image 3，因此尚未达到 final 阈值 0.05 eV/A，继续保留任务等待自然收敛或后续明确失稳。
      - 2026-05-30 04:46 报告刷新：作业 `468378` 仍为 `RUNNING`，`sacct` 显示 batch/extern/prted 均为 `RUNNING`；暂无 04:42:29 之后的新完整 trajectory 写回。JSON/HTML 报告已刷新至 04:45:57，Segment A 指标仍为 barrier 约 0.121501 eV、max-energy image 12、max fmax 约 0.216784 eV/A、max-force image 3；FIRE 日志最后仍为 step 29、optimizer fmax 约 0.067942 eV/A。该任务尚未满足 `fmax: 0.05` final 收敛阈值，不能进入最终拼接路径和三路线 barrier 定稿。
      - 2026-05-30 04:53 最终复核：job `468378` 已 `COMPLETED`，ExitCode `0:0`，结束于 04:47:13。AutoNEB final 的 FIRE step 30 optimizer fmax 为 0.041982 eV/A，低于 final 阈值 0.05 eV/A；Segment A AutoNEB final barrier 约 0.121501 eV，max-energy image 12。已刷新最终 HTML/JSON 报告：`temp_practices/zn_neb_atst_validation/ZN_NEB_SEGMENTED_NSPIN2_REPORT.html` 与 `.json`。当前最佳拼接主路径为 `segA AutoNEB final + segB climbing NEB + segC climbing NEB`，全路径能垒约 0.223399 eV（相对 Segment A IS），全局最高点为 Segment C climbing NEB image 6；三段 optimizer final fmax 分别为 0.041982、0.046674、0.049380 eV/A。注意：direct NEB 仅有 segB/segC final，segA 使用 AutoNEB final；D2S+CCQN 未给出收敛分段路径，只作为辅助证据，不能声明三路线独立一致。
      - 配置为 image-level parallel AutoNEB，`n_max: 14`、`climb: true`、`fmax: [0.2, 0.05]`、`calculation: scf` + `nspin: 2`。
  - 此前 fmax 约 0.10 eV/A 的 CCQN 候选已用 nspin=2、4 卡单 ABACUS 作保守续跑测试：
      - 起始 fmax 约 0.110586 eV/A；
      - 续跑至 step 5 后 fmax 升至约 0.229928 eV/A；
      - 续跑诊断显示 6 个 steps 全部处于 `uphill` 模式，最小 Hessian 特征值仍为正，未进入 PRFO 鞍点精修；
      - 最佳点仍是起始结构，已取消续跑任务，仅保留 best frame 作为候选 TS 证据，不作为主路线继续占用 GPU；
      - 2026-05-29 16:51 复核结论：不建议直接用该候选继续 4 卡 CCQN 续跑来获取 TS；若要再次使用单端 TS 精修，应等待 B/C/A 分段 NEB 给出力和能量一致的最高点后重新定义反应方向，而不是从该旧 CCQN best frame 盲目续跑。
      - 2026-05-29 18:59 复核确认：当前没有 D2S rough-NEB -> CCQN 作业在跑；该旧 CCQN 候选不值得此时用 4 卡单 ABACUS 继续续跑。
      - 2026-05-29 21:58 复核确认：旧 CCQN 原始轨迹 best step 为 step 20、fmax 约 0.130715 eV/A，随后发散至 0.751398 eV/A；conservative restart best step 为 step 13、fmax 约 0.110532 eV/A，随后升至 0.457083 eV/A；nspin=2 续跑 best 仍为 step 0、fmax 约 0.110586 eV/A，step 5 升至 0.229928 eV/A。结论维持：不提交 4 卡单 ABACUS CCQN 续跑，等待分段 NEB/AutoNEB 产生新的 TS 初猜。
      - 2026-05-29 22:56 复核确认：当前仅有 `468378` segA AutoNEB final 与 `468233` segC climbing NEB 在跑，没有 D2S/CCQN 作业在跑；旧 CCQN nspin=2 续跑的 6 帧 fmax 为 0.110586 -> 0.115903 -> 0.133067 -> 0.159623 -> 0.193214 -> 0.229928，最佳点仍是 step 0。因此不值得现在用 4 卡单 ABACUS 从该旧候选继续续跑以直接获取 TS 信息，只保留该 best frame 作为辅助候选。
      - 2026-05-30 00:19 复核确认：旧 CCQN 的 4 卡单 ABACUS nspin=2 配置已满足 `calculation scf`、`nspin 2`、`ks_solver cusolver`，但从 fmax 约 0.110586 eV/A 的 best frame 重启后连续升至 0.229928 eV/A；原始 nspin=1 轨迹和 conservative restart 也都在 best frame 后发散。因此暂不重投 4 卡 CCQN，避免占用单节点资源产生不可验证 TS；等待当前 NEB/AutoNEB 收敛后，从分段路径最高点重新生成 CCQN/Sella 精修初猜。
      - 2026-05-30 01:38 根据最新要求，在保留现有 NEB/AutoNEB 的前提下，提交一次极小步长 4 卡单 ABACUS CCQN 短程校验：配置 `configs/ccqn_from_retry_best_nspin2_tiny_step.yaml` 已通过 `atst config validate`，脚本 `jobs/submit_ccqn_from_retry_best_nspin2_tiny_step.sbatch` 已通过 `bash -n`，Slurm job 为 `468960` (`zn-ccqn-rbest-tiny`)。该任务仅用于确认 fmax 约 0.110586 eV/A 的 best frame 是否可在 `trust_radius_uphill: 0.005 A`、`trust_radius_saddle_initial: 0.002 A` 下继续靠近 0.05 eV/A；若 fmax 再次单调升高，应取消并不再从旧 CCQN best frame 续跑。
      - 2026-05-30 01:58 已取消 tiny-step CCQN job `468960`，Slurm 状态 `CANCELLED`。该短程校验写出 4 帧，fmax 为 0.110586 -> 0.111398 -> 0.112354 -> 0.113784 eV/A，连续升高；结论：此前 fmax 约 0.10 eV/A 的旧 CCQN best frame 不值得继续用 4 卡 ABACUS 续跑来直接获取 TS，只保留为辅助候选结构。
      - 2026-05-30 02:38 复核确认：`sacct` 显示 job `468960` 为 `CANCELLED`，运行约 00:19:40；短程日志再次确认 fmax 连续升高，没有出现朝 0.05 eV/A 收敛的迹象。因此不再从该旧 CCQN best frame 投 4 卡单 ABACUS 续跑，后续若需 CCQN/Sella，应从当前分段 NEB/AutoNEB 的收敛最高点重新取 TS 初猜。
      - 2026-05-30 03:15 复核确认：旧 CCQN best frame 后的三组证据一致不支持续跑：原 conservative restart 轨迹 27 帧的 best 为 step 13、fmax 约 0.110532 eV/A，最终升至约 0.457083 eV/A；nspin=2 普通步长续跑 6 帧从 0.110586 升至 0.229928 eV/A；nspin=2 tiny-step 续跑 4 帧从 0.110586 升至 0.113784 eV/A。因此不提交新的 4 卡单 ABACUS CCQN 续跑，保留当前 NEB/AutoNEB 作为主路线。
      - 2026-05-30 03:40 按要求再次复核：4 卡单 ABACUS nspin=2 普通续跑使用 `mpi: 16`、`calculation: scf`、`nspin: 2`、`ks_solver: cusolver`，但 6 帧全部为 `uphill` 模式且 fmax 从 0.110586 连续升至 0.229928 eV/A；tiny-step 续跑 job `468960` 已取消，4 帧 fmax 从 0.110586 连续升至 0.113784 eV/A。结论维持：该约 0.10 eV/A 的旧 CCQN best frame 不值得拿出来继续 4 卡续跑以直接获取过渡态信息；若后续要做 4 卡单 ABACUS CCQN/Sella 精修，应从当前分段 NEB/AutoNEB 收敛后的最高能 image 重新生成初猜。
      - 2026-05-30 04:07 重新读取 CCQN 轨迹与结构确认：`ccqn_from_retry_best_nspin2` 的 best 为 step 0，fmax 约 0.110586 eV/A，step 5 升至约 0.229928 eV/A；`ccqn_from_retry_best_nspin2_tiny_step` 的 best 仍为 step 0，fmax 约 0.110586 eV/A，step 3 升至约 0.113784 eV/A。该 best frame 与 M2 的 RMSD 约 0.022 A、Zn 位移约 0.237 A，更像靠近 Segment C 起点的辅助候选，而不是已验证的鞍点；不再提交 4 卡单 ABACUS CCQN 续跑。
      - 2026-05-30 04:18 fresh 复核确认：`sacct` 显示普通步长 job `465571` 与 tiny-step job `468960` 均已 `CANCELLED`；两者配置均为 4 卡单 ABACUS（`mpi: 16`、`calculation: scf`、`nspin: 2`、`ks_solver: cusolver`）。ASE 重新读取轨迹得到普通步长 fmax 为 0.110586 -> 0.115903 -> 0.133067 -> 0.159623 -> 0.193214 -> 0.229928 eV/A，tiny-step fmax 为 0.110586 -> 0.111398 -> 0.112354 -> 0.113784 eV/A；两条轨迹的 best step 均为 0，续跑未朝 0.05 eV/A 收敛。因此旧 CCQN best frame 不值得现在拿出来继续 4 卡续跑直接获取 TS 信息。
      - 2026-05-30 04:44 再次按当前要求确认：保留 NEB/AutoNEB 主任务，不从旧 CCQN best frame 另投 4 卡单 ABACUS 续跑。fresh `sacct` 显示普通步长 CCQN job `465571` 与 tiny-step CCQN job `468960` 均已取消；两次续跑都是从约 0.110586 eV/A 出发，但普通步长升至约 0.229928 eV/A，tiny-step 也升至约 0.113784 eV/A。该行为说明旧候选在当前反应方向和 Hessian/模式设置下没有继续收敛趋势，直接续跑更可能消耗单节点资源而不是产出可信 TS；若需要单端 TS 精修，应等待当前分段 NEB/AutoNEB 收敛后，从新的最高能 image 或力/能量一致的鞍点候选重新启动 CCQN/Sella。
  - 当前已形成一条完整 IS -> M1 -> M2 -> FS 的 ABACUS nspin=2 主路径和 HTML 报告；该主路径由 segA AutoNEB final 与 segB/segC direct climbing NEB 拼接。三路线对比的结论是：direct NEB 未覆盖 segA final，D2S+CCQN 未给出收敛分段路线，因此当前结果是最佳混合路线证据，而非 direct NEB / AutoNEB / D2S+CCQN 三路线一致性证明。

  ## Acceptance Criteria

  - 三条路线都必须使用 ABACUS calculation scf + nspin 2。
  - 不复用旧 nspin=1 endpoint energies/forces。
  - 至少一条路线给出完整 IS -> M1 -> M2 -> FS 拼接路径。
  - 最终报告必须列出：
      - 每段 barrier；
      - 全路径 barrier；
      - 每段最高能 image；
      - 每段 max fmax；
      - Zn 最近邻变化；
      - direct NEB / AutoNEB / D2S+CCQN 三条路线之间的 barrier 差异。
  - 若三条路线 barrier 差异 <=0.10-0.15 eV 且 TS 区域 Zn 配位一致，则认为 Zn 迁移能垒可信。
  - 若 D2S+CCQN 的 TS 与 NEB 最高点不一致，则以分段 NEB/AutoNEB 的连续路径为主，CCQN 结果只作为候选 TS，需要额外
    IRC/短 NEB 验证。
