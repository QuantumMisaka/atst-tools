 # Zn 迁移轨迹与能垒稳健计算方案

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